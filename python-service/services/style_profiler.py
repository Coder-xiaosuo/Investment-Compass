"""Style Profiler v2.0 — 投资风格画像引擎（冷启动 + HITL 反馈自进化）

设计：
1. 冷启动：新用户首次进入系统，前端弹 12 道问卷题，一次性得到基线画像
2. 自进化：用户与 Agent 对话时，每次 HITL 中断后的反馈（approve/reject/respond）
   会触发 LLM 推断器，结合「Agent 建议 + 用户反馈」自动调整 6 维度 score
3. 稳定判定：6 维度中至少 4 个 evidence_count >= 1 时 stable=True

关键组件：
- cold_start_init(answers)            冷启动问卷初始化画像
- observe_feedback(advice, feedback) HITL 反馈时 LLM 推断 + 更新画像
- infer_feedback_scores(advice, feedback) LLM 推断器
- get_radar_profile()                读取雷达图数据
- render_ascii_radar()               ASCII 雷达图（演示用）

异常处理：所有异常吞掉，绝不影响主对话流。
"""
from __future__ import annotations

import json
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from models.style_profile import (
    DIMENSIONS,
    DimensionScore,
    RadarPoint,
    RadarProfile,
    StyleProfile,
)
from shared.config import settings

logger = logging.getLogger(__name__)

# ── 静态资源 ────────────────────────────────────────────────────────────
_STYLES_PATH = Path(__file__).resolve().parent.parent / "data" / "investment_styles.json"
_styles_cache: Optional[dict] = None


def _load_styles() -> dict:
    global _styles_cache
    if _styles_cache is None:
        _styles_cache = json.loads(_STYLES_PATH.read_text(encoding="utf-8"))
    return _styles_cache


# ── DB engine ──────────────────────────────────────────────────────────
_engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_recycle=settings.DATABASE_POOL_RECYCLE,
    pool_timeout=30,
)


def _session() -> Session:
    return Session(_engine)


# ── LLM 单例（懒加载）────────────────────────────────────────────────
_inference_llm: Optional[object] = None


def _get_inference_llm():
    """获取用于推断 HITL 反馈的 LLM。"""
    global _inference_llm
    if _inference_llm is not None:
        return _inference_llm
    from langchain_openai import ChatOpenAI

    _inference_llm = ChatOpenAI(
        model=settings.DEEPSEEK_MODEL,
        api_key=settings.DEEPSEEK_API_KEY or "",
        base_url="https://api.deepseek.com/v1",
        temperature=0.0,
        max_tokens=256,
    )
    return _inference_llm


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冷启动：12 题问卷初始化画像
# ═══════════════════════════════════════════════════════════════════════════


def cold_start_init(user_id: str, answers: list[dict]) -> dict:
    """新用户冷启动问卷初始化画像矩阵。

    Args:
        user_id: 用户ID。
        answers: 12 题作答，形如 [{"question_id":"q01","selected_label":"A"}, ...]

    Returns:
        {"dimensions": {...}, "stable": bool}
    """
    styles = _load_styles()
    question_map = {q["id"]: q for q in styles["cold_start_questions"]}

    # 累加每维度得分
    dim_scores: dict[str, float] = {dim: 0.0 for dim in DIMENSIONS}
    dim_evidence: dict[str, int] = {dim: 0 for dim in DIMENSIONS}

    for ans in answers:
        qid = ans.get("question_id")
        sel = ans.get("selected_label")
        q = question_map.get(qid)
        if not q or not sel:
            continue
        opt = next((o for o in q["options"] if o["label"] == sel), None)
        if not opt:
            continue
        for dim, delta in opt["scores"].items():
            if dim in dim_scores:
                dim_scores[dim] += delta
                dim_evidence[dim] += 1

    # 写入 style_profiles（每维度一行）
    session = _session()
    try:
        # 清空旧数据（支持重跑冷启动）
        session.execute(
            text("DELETE FROM style_profiles WHERE user_id = :uid"),
            {"uid": user_id},
        )

        for dim in DIMENSIONS:
            score = max(-1.0, min(1.0, dim_scores[dim]))
            ev = dim_evidence[dim]
            matched = _match_style(dim, score)
            session.execute(
                text("""
                    INSERT INTO style_profiles
                        (user_id, dimension, score, evidence_count,
                         matched_style_id, matched_style_label, stable, updated_at)
                    VALUES
                        (:uid, :dim, :score, :ev, :sid, :slabel, 0, NOW())
                """),
                {
                    "uid": user_id, "dim": dim, "score": score, "ev": ev,
                    "sid": matched["id"], "slabel": matched["label"],
                },
            )

        # 冷启动后默认 stable=0（还需 HITL 反馈进一步演化）
        # 但若 6 维度都已有 evidence，可视为 stable
        stable = sum(1 for v in dim_evidence.values() if v > 0) >= 4
        if stable:
            session.execute(
                text("UPDATE style_profiles SET stable = 1 WHERE user_id = :uid"),
                {"uid": user_id},
            )

        session.commit()
        logger.info(
            "cold_start_init: user=%s stable=%s dims=%s",
            user_id, stable,
            {d: round(dim_scores[d], 2) for d in DIMENSIONS},
        )

        # 同步到 preferences.md
        try:
            radar = get_radar_profile(user_id)
            _sync_to_preferences_md(radar)
        except Exception:
            logger.warning("cold_start_init: 同步偏好文件失败", exc_info=True)

        return {"dimensions": dim_scores, "stable": stable}
    except Exception as exc:
        session.rollback()
        logger.warning("cold_start_init 失败: %s", exc)
        return {"dimensions": {}, "stable": False}
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════════
# 2. LLM 推断器：从 HITL 反馈推断 6 维度 score 调整
# ═══════════════════════════════════════════════════════════════════════════

_INFER_PROMPT = """你是投资风格推断器。根据用户对 Agent 建议的反馈，推断 6 维度偏好调整。

维度定义（每维取值范围 [-0.3, +0.3]）：
- risk_appetite    风险偏好: 保守/嫌恶风险=-1, 激进/追逐风险=+1
- time_horizon     时间周期: 偏好短线=-1, 偏好长线=+1
- decision_basis   决策依据: 技术面(K线/量能/图表)=-1, 基本面(财报/PE/估值)=+1
- trading_style    交易风格: 左侧(抄底/等回调/摊薄)=-1, 右侧(追涨/突破买)=+1
- concentration    仓位集中度: 分散多只=-1, 集中重仓=+1
- emotion_pref     情绪偏好: 防御(红利/公用/低波动)=-1, 题材(概念/打板/热门)=+1

【Agent 建议】
{advice}

【用户反馈】
动作: {action}
内容: {response}

── 关键词 → 维度映射规则（优先级从高到低）────────────────────────────

1. 风险偏好 risk_appetite:
   - "风险太大/太高了/不敢/保守/稳健" → -0.2~-0.3
   - "没问题/可以承受/搏一把"       → +0.2~+0.3

2. 决策依据 decision_basis:
   - 提 PE/估值/财报/基本面/年报/ROE    → +0.2~+0.3 (基本面派)
   - 提 K线/量能/均线/技术面/MACD/图表  → -0.2~-0.3 (技术面派)
   - 提 PE 估值同时拒接 → 说明在意估值，decision_basis +0.2~+0.3

3. 交易风格 trading_style:
   - "等回调/等跌/抄底/摊薄/低了再买" → -0.2~-0.3 (左侧)
   - "突破/追涨/打板/追进去"         → +0.2~+0.3 (右侧)
   - 拒绝"打板/追涨"建议 → -0.2~-0.3

4. 时间周期 time_horizon:
   - "短线/快进快出/打板/几天"          → -0.2~-0.3 (短线)
   - "长线/长期持有/3年/分红/不着急卖"  → +0.2~+0.3 (长线)
   - **重要**："排斥/拒绝短线" ≠ "偏好长线"！若用户仅表达拒绝短线但未表达长线意愿，time_horizon 填 0

5. 仓位集中度 concentration:
   - "分散/多只/5只以上/降低仓位" → -0.2~-0.3
   - "集中/重仓/2-3只/all in"    → +0.2~+0.3

6. 情绪偏好 emotion_pref:
   - "防御/红利/公用/低波动/分红/吃股息" → -0.2~-0.3
   - "题材/概念/打板/热门/炒作"           → +0.2~+0.3
   - 拒绝"题材/打板"建议 → -0.2~-0.3 (防御倾向)

── 通用规则 ──────────────────────────────────────────────────────────
- 仅输出有明确依据的维度，无依据的填 0
- approve：接受建议 → 与建议内容同向微调（±0.1），若反馈文本有额外表达可加大
- reject：拒绝建议 → 与建议内容反向调整（±0.2~0.3），结合文本语义
- respond：主动表达 → 纯按文本语义调整（±0.2~0.3）
- 多个关键词命中时叠加但单维不超过 0.3

严格输出 JSON（不输出解释）：
{{"risk_appetite": 0.0, "time_horizon": 0.0, "decision_basis": 0.0, "trading_style": 0.0, "concentration": 0.0, "emotion_pref": 0.0}}"""


def infer_feedback_scores(
    advice: str,
    action: str,
    response: str = "",
) -> dict[str, float]:
    """LLM 推断器：基于 Agent 建议 + 用户反馈，输出 6 维度 score 调整。

    Args:
        advice: Agent 建议摘要（如"估值分85，PE=50，建议进入技术分析"）
        action: approve / reject / respond
        response: respond 时的用户文本；其他动作留空

    Returns:
        6 维度的 score 调整 dict，所有值在 [-0.3, +0.3]。LLM 不可用时返回全 0。
    """
    zero = {dim: 0.0 for dim in DIMENSIONS}
    try:
        llm = _get_inference_llm()
        if llm is None:
            return zero
        prompt = _INFER_PROMPT.format(
            advice=advice or "(无)",
            action=action,
            response=response or "(无文本反馈)",
        )
        resp = llm.invoke([
            SystemMessage(content="你是投资风格推断器，仅输出 JSON。"),
            HumanMessage(content=prompt),
        ])
        content = resp.content.strip() if hasattr(resp, "content") else ""
        # 提取 JSON
        m = re.search(r"\{[^{}]*\}", content, re.DOTALL)
        if not m:
            return zero
        parsed = json.loads(m.group(0))
        # 校验 + 限幅
        result = {}
        for dim in DIMENSIONS:
            v = float(parsed.get(dim, 0.0))
            v = max(-0.3, min(0.3, v))
            result[dim] = v
        return result
    except Exception as exc:
        logger.warning("infer_feedback_scores 失败（返回全 0）: %s", exc)
        return zero


# ═══════════════════════════════════════════════════════════════════════════
# 3. HITL 反馈观察：推断 + 写信号 + 应用到画像矩阵
# ═══════════════════════════════════════════════════════════════════════════

_PREFERENCES_PATH = Path(__file__).resolve().parent.parent / "memories" / "preferences.md"


def _sync_to_preferences_md(radar: RadarProfile) -> None:
    """将当前雷达画像概要写入 preferences.md 的「投资风格画像」分区。

    写入分区为 ``## 投资风格画像（自进化）``，位于文件末尾；其他分区
    不受影响。写前自动备份 .bak，异常时吞掉（绝不影响主对话流）。
    """
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        # 组装分区内容
        lines = [f"## 投资风格画像（自进化）", ""]
        for p in radar.points:
            lines.append(
                f"- {p.label}（{p.axis_label}）: {p.matched_style} "
                f"(score={p.score:+.2f}, evidence={p.evidence_count})"
            )
        lines.append(f"- 画像概要: {radar.summary}")

        new_section = "\n".join(lines)
        new_section_line = f"<!-- 自进化 {now} -->\n{new_section}\n"

        # 读取现有文件；不存在则创建
        if _PREFERENCES_PATH.exists():
            # 备份
            backup = _PREFERENCES_PATH.with_suffix(".md.bak")
            shutil.copy2(_PREFERENCES_PATH, backup)
            content = _PREFERENCES_PATH.read_text(encoding="utf-8")
        else:
            content = ""

        # 替换或追加「投资风格画像」分区
        section_header = "## 投资风格画像（自进化）"
        section_pattern = re.compile(
            rf"^<!-- 自进化 .*? -->\n{re.escape(section_header)}.*?(?=^## |\Z)",
            re.DOTALL | re.MULTILINE,
        )

        if section_pattern.search(content):
            # 已有该分区 → 原地替换
            new_content = section_pattern.sub(
                lambda m: new_section_line, content
            )
        else:
            # 无该分区 → 追加到文件末尾
            if content and not content.endswith("\n"):
                content += "\n"
            new_content = content.rstrip("\n") + "\n\n" + new_section_line

        _PREFERENCES_PATH.write_text(new_content, encoding="utf-8")
        logger.info("_sync_to_preferences_md: 已写入画像概要 stable=%s", radar.stable)
    except Exception:
        logger.warning("_sync_to_preferences_md: 写入失败（不影响主流程）", exc_info=True)


def observe_feedback(
    user_id: str,
    thread_id: str,
    advice_summary: str,
    advice_data: dict,
    user_action: str,
    user_response: str = "",
) -> dict:
    """HITL 反馈观察入口（在 main_agent resume 分支调用）。

    流程：
    1. 调 LLM 推断器得到 6 维度 score 调整
    2. 写入 feedback_signals 表（信号 + 推断结果）
    3. 累加到 style_profiles 矩阵，重新匹配标签
    4. 更新 stable 状态

    Args:
        user_id: 用户ID。
        thread_id: langgraph 线程ID。
        advice_summary: Agent 建议摘要（人读）。
        advice_data: Agent 建议结构化数据（如估值分/PE/建议动作）。
        user_action: approve / reject / respond。
        user_response: respond 文本；其他动作留空。

    Returns:
        {"inferred": {...}, "applied_dims": [...], "stable": bool}
    """
    if user_action not in ("approve", "reject", "respond"):
        return {"inferred": {}, "applied_dims": [], "stable": False}

    # 1. LLM 推断
    inferred = infer_feedback_scores(advice_summary, user_action, user_response)

    # 2. 写信号表
    session = _session()
    try:
        result = session.execute(
            text("""
                INSERT INTO feedback_signals
                    (user_id, thread_id, advice_summary, advice_data,
                     user_action, user_response, inferred_scores, applied, created_at)
                VALUES
                    (:uid, :tid, :asummary, :adata,
                     :action, :uresp, :inf, 0, NOW())
            """),
            {
                "uid": user_id,
                "tid": thread_id,
                "asummary": advice_summary,
                "adata": json.dumps(advice_data or {}, ensure_ascii=False),
                "action": user_action,
                "uresp": user_response or "",
                "inf": json.dumps(inferred, ensure_ascii=False),
            },
        )
        signal_id = result.lastrowid
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.warning("observe_feedback: 写信号失败: %s", exc)
        session.close()
        return {"inferred": inferred, "applied_dims": [], "stable": False}
    finally:
        session.close()

    # 3. 应用到 style_profiles 矩阵
    applied_dims = _apply_to_profile(user_id, inferred)

    # 4. 标记信号已应用
    if applied_dims:
        session = _session()
        try:
            session.execute(
                text("UPDATE feedback_signals SET applied = 1, applied_at = NOW() WHERE id = :sid"),
                {"sid": signal_id},
            )
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.warning("observe_feedback: 标记已应用失败: %s", exc)
        finally:
            session.close()

    # 5. 重新评估 stable
    stable = _recompute_stable(user_id)

    # 6. 同步画像到 preferences.md（自动注入 Agent system prompt）
    if applied_dims:
        try:
            radar = get_radar_profile(user_id)
            _sync_to_preferences_md(radar)
        except Exception:
            logger.warning("observe_feedback: 同步偏好文件失败", exc_info=True)

    logger.info(
        "observe_feedback: user=%s action=%s applied_dims=%s stable=%s",
        user_id, user_action, applied_dims, stable,
    )
    return {
        "inferred": inferred,
        "applied_dims": applied_dims,
        "stable": stable,
        "signal_id": signal_id,
    }


def _apply_to_profile(user_id: str, inferred: dict[str, float]) -> list[str]:
    """把 LLM 推断的 score 调整累加到 style_profiles 矩阵。"""
    applied = []
    session = _session()
    try:
        for dim, delta in inferred.items():
            if dim not in DIMENSIONS or delta == 0.0:
                continue
            row = session.execute(
                text("""
                    SELECT score, evidence_count FROM style_profiles
                    WHERE user_id = :uid AND dimension = :dim
                """),
                {"uid": user_id, "dim": dim},
            ).fetchone()

            if row:
                old_score, ev = row
                new_score = max(-1.0, min(1.0, float(old_score) + delta))
                new_ev = int(ev) + 1
                matched = _match_style(dim, new_score)
                session.execute(
                    text("""
                        UPDATE style_profiles
                        SET score = :score, evidence_count = :ev,
                            matched_style_id = :sid, matched_style_label = :slabel,
                            updated_at = NOW()
                        WHERE user_id = :uid AND dimension = :dim
                    """),
                    {
                        "score": new_score, "ev": new_ev,
                        "sid": matched["id"], "slabel": matched["label"],
                        "uid": user_id, "dim": dim,
                    },
                )
                applied.append(dim)
            else:
                # 该维度还没有画像行（用户未冷启动或冷启动时该维度为 0）
                new_score = max(-1.0, min(1.0, delta))
                matched = _match_style(dim, new_score)
                session.execute(
                    text("""
                        INSERT INTO style_profiles
                            (user_id, dimension, score, evidence_count,
                             matched_style_id, matched_style_label, stable, updated_at)
                        VALUES
                            (:uid, :dim, :score, 1, :sid, :slabel, 0, NOW())
                    """),
                    {
                        "uid": user_id, "dim": dim, "score": new_score,
                        "sid": matched["id"], "slabel": matched["label"],
                    },
                )
                applied.append(dim)
        session.commit()
        return applied
    except Exception as exc:
        session.rollback()
        logger.warning("_apply_to_profile 失败: %s", exc)
        return []
    finally:
        session.close()


def _recompute_stable(user_id: str) -> bool:
    """重新评估 stable 状态：6 维度中至少 4 个 evidence_count >= 1 → stable=1。"""
    session = _session()
    try:
        row = session.execute(
            text("""
                SELECT COUNT(*) FROM style_profiles
                WHERE user_id = :uid AND evidence_count >= 1
            """),
            {"uid": user_id},
        ).fetchone()
        non_zero_count = int(row[0]) if row else 0
        stable = non_zero_count >= 4
        session.execute(
            text("UPDATE style_profiles SET stable = :stable WHERE user_id = :uid"),
            {"uid": user_id, "stable": 1 if stable else 0},
        )
        session.commit()
        return stable
    except Exception as exc:
        session.rollback()
        logger.warning("_recompute_stable 失败: %s", exc)
        return False
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════════
# 4. 标签匹配 + 读取画像 + 雷达图
# ═══════════════════════════════════════════════════════════════════════════


def _match_style(dimension: str, score: float) -> dict:
    """根据 score 匹配该维度的 5 个风格标签之一。"""
    styles = _load_styles()
    candidates = styles["styles"].get(dimension, [])
    if not candidates:
        return {"id": "", "label": "未知"}

    if score <= -0.6:
        idx = 0
    elif score <= -0.2:
        idx = 1
    elif score < 0.2:
        idx = 2
    elif score < 0.6:
        idx = 3
    else:
        idx = 4
    return candidates[idx]


def get_profile(user_id: str = "default") -> StyleProfile:
    """读取用户当前画像矩阵。"""
    session = _session()
    try:
        rows = session.execute(
            text("""
                SELECT dimension, score, evidence_count,
                       matched_style_id, matched_style_label, updated_at, stable
                FROM style_profiles WHERE user_id = :uid
            """),
            {"uid": user_id},
        ).fetchall()

        dims = {
            r[0]: DimensionScore(
                dimension=r[0], score=float(r[1]), evidence_count=int(r[2]),
                matched_style_id=r[3], matched_style_label=r[4],
                updated_at=r[5],
            )
            for r in rows
        }
        # stable 全局值：取任意行的 stable（所有行相同）
        stable = bool(rows[0][6]) if rows else False

        return StyleProfile(
            user_id=user_id, dimensions=dims, stable=stable,
            quiz_completed_count=0,  # v2.0 不再有"问卷次数"概念
            conversation_count=0,
        )
    except Exception as exc:
        logger.warning("get_profile 失败: %s", exc)
        return StyleProfile(user_id=user_id)
    finally:
        session.close()


def get_radar_profile(user_id: str = "default") -> RadarProfile:
    """生成雷达图数据（前端可直接渲染）。"""
    styles = _load_styles()
    profile = get_profile(user_id)

    points: list[RadarPoint] = []
    summary_labels: list[str] = []
    for dim in DIMENSIONS:
        ds = profile.dimensions.get(dim)
        score = ds.score if ds else 0.0
        matched = ds.matched_style_label if ds and ds.matched_style_label else "未知"
        if not matched or matched == "未知":
            matched = _match_style(dim, score)["label"]

        dim_meta = styles["dimensions"][dim]
        points.append(RadarPoint(
            dimension=dim,
            label=dim_meta["label"],
            axis_label=dim_meta["axis_label"],
            score=round(score, 3),
            score_0_100=int((score + 1.0) * 50),
            matched_style=matched,
            evidence_count=ds.evidence_count if ds else 0,
        ))
        summary_labels.append(matched)

    summary = "/".join(summary_labels)
    # 是否已完成过冷启动：任一维度存在证据（evidence_count>0）即视为已测试
    quiz_completed = 1 if any(ds.evidence_count > 0 for ds in profile.dimensions.values()) else 0
    return RadarProfile(
        user_id=user_id, stable=profile.stable,
        quiz_completed_count=quiz_completed,
        conversation_count=0,
        points=points, summary=summary,
    )


def render_ascii_radar(user_id: str = "default") -> str:
    """ASCII 雷达图（终端演示用）。"""
    rp = get_radar_profile(user_id)
    lines = []
    lines.append("=" * 60)
    lines.append(f"  投资风格雷达图 — {user_id}")
    lines.append("=" * 60)
    lines.append(f"  状态: {'稳定' if rp.stable else '成长中'}")
    lines.append("")
    lines.append("  维度                分数      标签         [0%──50%──100%]")
    lines.append("  " + "─" * 56)
    for p in rp.points:
        bar_len = 30
        pos = int(p.score_0_100 / 100 * bar_len)
        bar = " " * pos + "■" + " " * (bar_len - pos - 1)
        score_str = f"{p.score:+.2f}"
        lines.append(
            f"  {p.label:<8}{p.axis_label:<14} {score_str}   "
            f"{p.matched_style:<10} [{bar}]"
        )
    lines.append("")
    lines.append(f"  画像概要: {rp.summary}")
    lines.append("=" * 60)
    return "\n".join(lines)
