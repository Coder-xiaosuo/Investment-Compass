"""经验写回路运行时自动化公共服务。

将 scripts/review_decisions.py（复盘回填 review_outcome）与
scripts/promote_experiences.py（提升已复盘决策进 Chroma 经验库）的核心逻辑
抽取为可被运行时直接调用的公共函数，供定时任务 / 后台线程等调用，
不依赖 scripts/ 下的 argparse 与日志重配置。

Usage::

    from services.experience_loop_service import run_experience_loop

    result = run_experience_loop()
    # => {"reviewed": n, "promoted_hit": h, "promoted_miss": m}
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.config import _engine
from models.experience_entry import ExperienceEntry
from services.experience_library import get_experience_library

logger = logging.getLogger(__name__)

# 复盘窗口：决策日之后取 10 根已收盘日线
REVIEW_HORIZON_DAYS = 10


# ──────────────────────────────────────────────────────────────────────────────
# 复盘：review_pending_decisions
# ──────────────────────────────────────────────────────────────────────────────


def _fetch_pending_review_decisions(session: Session, limit: int = 0) -> list[dict]:
    """查询待复盘的决策卡（review_outcome 为空 且 action 为 BUY/SELL 且有成交价）。

    limit > 0 时最多返回前 limit 条（按 id 升序）。
    """
    sql = """
        SELECT id, symbol, action, current_price, created_at
        FROM decision_cards
        WHERE review_outcome IS NULL
          AND action IN ('BUY','SELL')
          AND current_price IS NOT NULL
        ORDER BY id
    """
    if limit > 0:
        sql += f" LIMIT {int(limit)}"
    rows = session.execute(text(sql)).fetchall()
    return [r._asdict() for r in rows]


def _fetch_next_bars(session: Session, symbol: str, decision_date) -> list[dict]:
    """获取决策日之后的日线行情（按时间升序，最多 10 根，closed 才计入）。

    决策日当天之后的交易日才开始数（trade_date > decision_date）。
    """
    rows = session.execute(
        text("""
            SELECT trade_date, open, high, low, close
            FROM market_data
            WHERE symbol = :sym
              AND timeframe = '1d'
              AND closed = TRUE
              AND trade_date > :decision_date
            ORDER BY trade_date ASC
            LIMIT 10
        """),
        {"sym": symbol, "decision_date": decision_date},
    ).fetchall()
    return [r._asdict() for r in rows]


def _compute_review(row: dict, bars: list[dict]) -> dict:
    """根据决策卡与后续 10 根行情计算复盘结果（口径与 scripts/review_decisions.py 完全一致）。"""
    action = row["action"]
    current_price = float(row["current_price"])
    close_10 = float(bars[-1]["close"])  # 第 10 根（最后一根）收盘价
    high_max = max(float(b["high"]) for b in bars)  # 区间内最高价
    low_min = min(float(b["low"]) for b in bars)  # 区间内最低价

    # 统一口径：市场涨跌幅 = 相对决策时点价格的变动比例
    profit_ratio = round(close_10 / current_price - 1, 4)
    high_ratio = round(high_max / current_price - 1, 4)
    low_ratio = round(low_min / current_price - 1, 4)

    # 判断方向是否兑现：BUY 需 10 日后收盘价上涨，SELL 需下跌
    if action == "BUY":
        verdict = "HIT" if close_10 > current_price else "MISS"
    else:  # SELL
        verdict = "HIT" if close_10 < current_price else "MISS"

    # 区间实际走势分类
    if abs(profit_ratio) < 0.01:
        actual_trend = "震荡"
    elif profit_ratio > 0:
        actual_trend = "上涨"
    else:
        actual_trend = "下跌"

    return {
        "verdict": verdict,
        "actual_trend": actual_trend,
        "profit_ratio": profit_ratio,
        "high_ratio": high_ratio,
        "low_ratio": low_ratio,
        "review_horizon_days": REVIEW_HORIZON_DAYS,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }


def review_pending_decisions(limit: int = 0) -> int:
    """复盘待处理决策卡并回填 review_outcome，返回本次成功回填的卡数。

    - 处理范围：review_outcome 为空、action 为 BUY/SELL 且 current_price 非空
    - 取决策日后 10 根 closed=TRUE 的 1d 日线，不足 10 根跳过（不标记）
    - 幂等：review_outcome 已非空的决策卡不会被选中
    - 单卡异常仅记录 warning，不中断整体流程
    """
    session = Session(_engine)
    reviewed = 0
    try:
        pending = _fetch_pending_review_decisions(session, limit)
        for row in pending:
            try:
                decision_date = row["created_at"].date()
                bars = _fetch_next_bars(session, row["symbol"], decision_date)
                if len(bars) < REVIEW_HORIZON_DAYS:
                    # 后续行情不足 10 根，跳过且不写回任何标记
                    continue

                outcome = _compute_review(row, bars)
                session.execute(
                    text(
                        "UPDATE decision_cards "
                        "SET review_outcome = CAST(:ro AS JSON) WHERE id = :id"
                    ),
                    {"ro": json.dumps(outcome, ensure_ascii=False), "id": row["id"]},
                )
                session.commit()
                reviewed += 1
                logger.info(
                    "复盘决策 #%s (%s %s): verdict=%s trend=%s profit=%.4f high=%.4f low=%.4f",
                    row["id"], row["symbol"], row["action"],
                    outcome["verdict"], outcome["actual_trend"],
                    outcome["profit_ratio"], outcome["high_ratio"], outcome["low_ratio"],
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("复盘决策 #%s 失败: %s", row.get("id"), e)
    finally:
        session.close()

    logger.info("复盘完成：已复盘 %d 条", reviewed)
    return reviewed


# ──────────────────────────────────────────────────────────────────────────────
# 提升：promote_pending_experiences
# ──────────────────────────────────────────────────────────────────────────────


def _load_json(value: Any, default: Any) -> Any:
    """容错解析 JSON 字段（MySQL JSON 列经驱动读回可能是 str，也可能已解析为 dict/list）。"""
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def build_entry(card: dict) -> ExperienceEntry:
    """根据决策卡组装 ExperienceEntry（id = dc_{card_id}，幂等 upsert 键）。"""
    # 复盘结论（容错解析；非 dict 时兜底为空 dict）
    outcome = _load_json(card.get("review_outcome"), {})
    if not isinstance(outcome, dict):
        outcome = {}

    # 数据源解析：提取 valuation / technical 的 summary 汇总进 analysis_summary
    ds = _load_json(card.get("data_sources"), {})
    if not isinstance(ds, dict):
        ds = {}

    valuation = ds.get("valuation", {})
    valuation_summary = ""
    if isinstance(valuation, dict):
        valuation_summary = valuation.get("summary", "") or ""

    technical = ds.get("technical", {})
    pa_conclusion = ""
    if isinstance(technical, dict):
        pa_conclusion = technical.get("summary", "") or ""

    # confidence 可能为 None，此时 final_decision 置空串
    confidence = card.get("confidence")
    if confidence is not None:
        final_decision = f"{card.get('action', '')} (confidence={confidence})"
    else:
        final_decision = ""

    # 时间戳：naive datetime 补 UTC 时区（与 experience_library._time_decay_weight 的 tz 处理一致）
    ts = card.get("created_at")
    if ts is not None and ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    # 标签：reviewed + verdict（verdict 从 outcome 取，缺失时兜底 "unknown"）
    verdict = outcome.get("verdict") or "unknown"
    tags = ["reviewed", str(verdict).lower()]

    return ExperienceEntry(
        id=f"dc_{card['id']}",
        timestamp=ts,
        stock_code=card.get("symbol", "") or "",
        stock_name=card.get("stock_name", "") or "",
        market_cycle=card.get("market_cycle", "") or "",
        sector=card.get("sector", "") or "",
        pattern=card.get("pattern", "") or "",
        analysis_summary={
            "valuation": valuation_summary,
            "pa_conclusion": pa_conclusion,
            "final_decision": final_decision,
        },
        outcome=outcome,
        tags=tags,
    )


def _fetch_pending_promote_decisions(session: Session, limit: int = 0) -> list[dict]:
    """查询待提升的决策卡（review_outcome 非空），按 id 升序。

    limit > 0 时最多返回前 limit 条。
    """
    sql = """
        SELECT id, trace_id, symbol, stock_name, action, confidence, current_price,
               market_cycle, sector, pattern, reasoning, data_sources, review_outcome, created_at
        FROM decision_cards
        WHERE review_outcome IS NOT NULL
        ORDER BY id
    """
    if limit > 0:
        sql += f" LIMIT {int(limit)}"
    rows = session.execute(text(sql)).fetchall()
    return [r._asdict() for r in rows]


def promote_pending_experiences(limit: int = 0) -> tuple[int, int]:
    """将已复盘决策卡提升进 Chroma 经验库，返回 (HIT 数, MISS 数)。

    - 处理范围：review_outcome 非空的决策卡，id = dc_{card_id}
    - Chroma upsert 覆盖，天然幂等
    - 单卡异常仅记录 warning，不中断整体流程
    """
    session = Session(_engine)
    lib = get_experience_library()  # 模块级单例，一次获取复用
    hit_count = 0
    miss_count = 0
    try:
        pending = _fetch_pending_promote_decisions(session, limit)
        for card in pending:
            try:
                entry = build_entry(card)
                lib.save(entry)
                verdict = str(entry.outcome.get("verdict", "")).upper()
                if verdict == "HIT":
                    hit_count += 1
                elif verdict == "MISS":
                    miss_count += 1
                logger.info(
                    "提升决策 #%s (%s %s): verdict=%s -> %s",
                    card["id"], card["symbol"], card["action"],
                    verdict or "N/A", entry.id,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("提升决策 #%s 失败: %s", card.get("id"), e)
    finally:
        session.close()

    logger.info("提升完成：HIT %d 条 / MISS %d 条", hit_count, miss_count)
    return hit_count, miss_count


# ──────────────────────────────────────────────────────────────────────────────
# 组合运行：run_experience_loop
# ──────────────────────────────────────────────────────────────────────────────


def run_experience_loop() -> dict:
    """先复盘再提升，返回 {"reviewed": n, "promoted_hit": h, "promoted_miss": m}。

    内部每步 try/except：任何异常仅 logger.warning，绝不向上抛，保证
    运行时调度方（定时任务 / 后台线程）不被单次失败影响。
    """
    result = {"reviewed": 0, "promoted_hit": 0, "promoted_miss": 0}

    try:
        result["reviewed"] = review_pending_decisions()
    except Exception as e:  # noqa: BLE001
        logger.warning("经验写回路：复盘步骤异常，跳过: %s", e)

    try:
        hit, miss = promote_pending_experiences()
        result["promoted_hit"] = hit
        result["promoted_miss"] = miss
    except Exception as e:  # noqa: BLE001
        logger.warning("经验写回路：提升步骤异常，跳过: %s", e)

    logger.info("经验写回路执行完成：%s", result)
    return result
