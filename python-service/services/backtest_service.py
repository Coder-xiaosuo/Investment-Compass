"""Backtest service — LLM 模式历史回测引擎（真实 VA + TA 子 Agent）。

对任意历史时点执行「真实 value_assessment（LLM 定性）+ technical_analysis
（LLM 技术分析）」的决策回放，并复用复盘口径（scripts/review_decisions.py）
统计 horizon 日 HIT 率，作为分析引擎决策质量的客观度量。

与生产引擎的关系：
- 走真实 VA / TA 子 Agent，与生产同源（LLM 定性分析 + 技术面 LLM 分析）。
- 回测差异：VA 工具调用由回测引擎预执行并注入 as_of（保证防未来函数）；
  TA graph 以 backtest_mode=True 运行（禁用经验注入 / 决策落库 / 飞书推送）。

关键特性：
- 财务/估值/行业接口均以 as_of 回溯，防止未来函数。
- market_data 查询兼容 6 位 code 与带后缀（如 600519.SH）两种存储格式。
- 验证口径与 review_decisions.py 一致。
- 已知限制：LLM 通用知识存在时点泄漏，回测结果仅代表引擎行为近似。
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.config import _engine

logger = logging.getLogger(__name__)

# 单点分析所需的最少历史日线根数（指标预热充分）
MIN_HISTORY_BARS = 30


def _normalize_symbol(symbol: str) -> str:
    """提取纯 6 位数字代码（兼容 600519 / 600519.SH），异常时原样返回。"""
    try:
        digits = re.sub(r"\D", "", str(symbol))
        return digits[-6:] if len(digits) >= 6 else digits
    except Exception:
        return str(symbol)


def _coerce_date(as_of: Any) -> date:
    """将 date 或 'YYYY-MM-DD' 字符串统一为 date。"""
    if isinstance(as_of, date):
        return as_of
    return date.fromisoformat(str(as_of))


def _fetch_bars_asof(symbol: str, as_of, count: int = 150) -> list[dict]:
    """获取截至 as_of 的已收盘日线（含当日），按时间 ASC 返回 dict 列表。

    symbol 兼容 6 位 code 与带后缀两种存储格式。
    返回字段：trade_date / ts_open / open / high / low / close / volume / amount / pct_chg。
    """
    code = _normalize_symbol(symbol)
    as_of_date = _coerce_date(as_of)
    session = Session(_engine)
    try:
        rows = session.execute(
            text("""
                SELECT trade_date, ts_open, open, high, low, close,
                       volume, amount, pct_chg
                FROM market_data
                WHERE (symbol = :code OR symbol LIKE :prefix)
                  AND timeframe = '1d'
                  AND closed = TRUE
                  AND trade_date <= :as_of
                ORDER BY trade_date DESC
                LIMIT :count
            """),
            {"code": code, "prefix": code + ".%", "as_of": as_of_date, "count": int(count)},
        ).fetchall()
        # 查询为 DESC（最新在前），反转为 ASC（最旧在前）
        return [dict(r._mapping) for r in reversed(rows)]
    finally:
        session.close()


def _fetch_future_bars(symbol: str, as_of, horizon: int = 10) -> list[dict]:
    """获取 as_of 之后的已收盘日线（trade_date > as_of），按时间 ASC 返回。

    LIMIT horizon 根，用于决策验证。
    """
    code = _normalize_symbol(symbol)
    as_of_date = _coerce_date(as_of)
    session = Session(_engine)
    try:
        rows = session.execute(
            text("""
                SELECT trade_date, open, high, low, close
                FROM market_data
                WHERE (symbol = :code OR symbol LIKE :prefix)
                  AND timeframe = '1d'
                  AND closed = TRUE
                  AND trade_date > :as_of
                ORDER BY trade_date ASC
                LIMIT :horizon
            """),
            {"code": code, "prefix": code + ".%", "as_of": as_of_date, "horizon": int(horizon)},
        ).fetchall()
        return [dict(r._mapping) for r in rows]
    finally:
        session.close()


def _list_trade_dates(code: str, start_date: date, end_date: date) -> list[date]:
    """区间内的实际交易日序列（ASC），供回测采样。"""
    session = Session(_engine)
    try:
        rows = session.execute(
            text("""
                SELECT DISTINCT trade_date
                FROM market_data
                WHERE (symbol = :code OR symbol LIKE :prefix)
                  AND timeframe = '1d'
                  AND closed = TRUE
                  AND trade_date BETWEEN :start AND :end
                ORDER BY trade_date
            """),
            {"code": code, "prefix": code + ".%", "start": start_date, "end": end_date},
        ).fetchall()
        return [r.trade_date for r in rows]
    finally:
        session.close()


def _evaluate(action: str, current_price: float, future_bars: list[dict], horizon: int) -> dict:
    """决策验证，口径与 scripts/review_decisions.py 完全一致。

    - 后续行情不足 horizon 根 → evaluated=False。
    - close_10 取最后一根（第 horizon 根）收盘价；high/low 取区间极值。
    - BUY 需 10 日后收盘上涨为 HIT，SELL 需下跌为 HIT。
    - actual_trend：|profit_ratio| < 1% → 震荡；>0 → 上涨；否则下跌。
    """
    if len(future_bars) < horizon:
        return {"evaluated": False, "reason": "后续行情不足"}

    close_10 = float(future_bars[-1]["close"])
    high_max = max(float(b["high"]) for b in future_bars)
    low_min = min(float(b["low"]) for b in future_bars)

    profit_ratio = round(close_10 / current_price - 1, 4)
    high_ratio = round(high_max / current_price - 1, 4)
    low_ratio = round(low_min / current_price - 1, 4)

    if action == "BUY":
        verdict = "HIT" if close_10 > current_price else "MISS"
    else:  # SELL
        verdict = "HIT" if close_10 < current_price else "MISS"

    if abs(profit_ratio) < 0.01:
        actual_trend = "震荡"
    elif profit_ratio > 0:
        actual_trend = "上涨"
    else:
        actual_trend = "下跌"

    return {
        "evaluated": True,
        "verdict": verdict,
        "profit_ratio": profit_ratio,
        "high_ratio": high_ratio,
        "low_ratio": low_ratio,
        "actual_trend": actual_trend,
        "close_10": close_10,
    }


def _build_summary(decisions: list[dict], dates: list[date], sampled: list[date]) -> dict:
    """从 decisions 汇总统计。

    decisions 条目统一结构（含 skipped / valuation_missing / evaluated /
    verdict / profit_ratio / high_ratio / low_ratio）。
    """
    total_analyzed = sum(1 for d in decisions if not d.get("skipped"))
    skipped_history = sum(1 for d in decisions if d.get("skipped"))
    valuation_missing_points = sum(1 for d in decisions if d.get("valuation_missing"))

    action_dist = {"BUY": 0, "SELL": 0, "HOLD": 0}
    for dec in decisions:
        if dec["action"] in action_dist:
            action_dist[dec["action"]] += 1

    evaluated_entries = [dec for dec in decisions if dec.get("evaluated")]
    evaluated_count = len(evaluated_entries)
    hit_count = sum(1 for dec in evaluated_entries if dec.get("verdict") == "HIT")

    def _avg(entries: list[dict], key: str) -> float | None:
        vals = [dec.get(key) for dec in entries if dec.get(key) is not None]
        if not vals:
            return None
        return round(sum(vals) / len(vals), 4)

    per_action_stats: dict[str, dict] = {}
    for act in ("BUY", "SELL", "HOLD"):
        group = [dec for dec in decisions if dec.get("action") == act]
        ev_group = [dec for dec in group if dec.get("evaluated")]
        per_action_stats[act] = {
            "count": len(group),
            "hit_rate": (
                round(sum(1 for dec in ev_group if dec.get("verdict") == "HIT") / len(ev_group), 4)
                if ev_group else None
            ),
            "avg_profit_ratio": _avg(ev_group, "profit_ratio"),
        }

    highs = [dec.get("high_ratio") for dec in evaluated_entries if dec.get("high_ratio") is not None]
    lows = [dec.get("low_ratio") for dec in evaluated_entries if dec.get("low_ratio") is not None]

    return {
        "total_analyzed": total_analyzed,
        "skipped_history": skipped_history,
        "total_trading_days": len(dates),
        "sample_count": len(sampled),
        "action_dist": action_dist,
        "evaluated_count": evaluated_count,
        "hit_count": hit_count,
        "hit_rate": round(hit_count / evaluated_count, 4) if evaluated_count else None,
        "avg_profit_ratio": _avg(evaluated_entries, "profit_ratio"),
        "avg_high_ratio": round(sum(highs) / len(highs), 4) if highs else None,
        "avg_low_ratio": round(sum(lows) / len(lows), 4) if lows else None,
        "verdict_count": {"HIT": hit_count, "MISS": evaluated_count - hit_count},
        "per_action_stats": per_action_stats,
        "valuation_missing_rate": (
            round(valuation_missing_points / total_analyzed, 4) if total_analyzed else None
        ),
    }


async def _analyze_at_llm(symbol: str, as_of, history_count: int = 150) -> dict:
    """LLM 版单点：真实 value_assessment（LLM 定性）+ technical_analysis（LLM 技术分析）。

    与生产引擎的差异：
    - VA 工具调用由回测引擎预执行（注入 as_of，保证防未来函数）。
    - TA graph 以 backtest_mode=True 运行：禁用经验注入与决策落库/飞书推送。
    - 组合 action 与生产一致：门控拦截（blocked）→ HOLD；否则最终 action
      由技术方向决定（buy→BUY / sell→SELL / neutral→HOLD）。
    """
    code = _normalize_symbol(symbol)
    try:
        bars_asc = _fetch_bars_asof(code, as_of, history_count)
        if len(bars_asc) < MIN_HISTORY_BARS:
            return {"skipped": True, "reason": "历史K线不足", "as_of": str(as_of), "symbol": code}
        close = float(bars_asc[-1]["close"])  # ASC 最后一根 = as_of 当日收盘

        # ── 估值：真实 VA 子 Agent（LLM 定性分析，内部预执行 assess_value） ──
        from agents.value_assessment_agent import run_value_assessment_llm

        va = await run_value_assessment_llm(code, "", as_of=str(as_of))
        if not isinstance(va, dict):
            va = {}
        blocked = bool(va.get("blocked"))
        final_score = va.get("final_score")
        va_summary = {
            "score": final_score,
            "final_level": va.get("final_level", ""),
            "summary": va.get("summary", ""),
            "recommend": va.get("recommend"),
            "reason": va.get("reason", ""),
        }

        # ── 技术面：真实 TA 子 Agent（LLM 技术分析，回测模式禁副作用） ──
        import json

        from agents.technical_analysis_agent import build_technical_analysis_agent

        ta_agent = build_technical_analysis_agent()
        user_json = json.dumps({
            "stock_identifier": code,
            "as_of": str(as_of),
            "va_summary": va_summary,
        }, ensure_ascii=False)
        ta_result = await ta_agent["runnable"].ainvoke({
            "messages": [{"role": "user", "content": user_json}],
            "backtest_mode": True,
        })
        pa = ta_result.get("structured_response") or {}
        if not isinstance(pa, dict):
            pa = {}
        direction = pa.get("direction") or "neutral"
        try:
            confidence = float(pa.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0

        # ── 组合决策（与生产引擎一致：最终 action 由技术方向决定） ──
        if blocked:
            action = "HOLD"
        elif direction == "buy":
            action = "BUY"
        elif direction == "sell":
            action = "SELL"
        else:
            action = "HOLD"

        return {
            "skipped": False,
            "symbol": code,
            "as_of": str(as_of),
            "close": close,
            "direction": direction,
            "confidence": confidence,
            "final_score": final_score,
            "level": va.get("final_level", ""),
            "action": action,
            "blocked": blocked,
            "block_reason": va.get("block_reason", ""),
            "valuation_missing": False,
            "signals": pa.get("signals", []),
            "cycle_hint": pa.get("market_cycle", ""),
        }
    except Exception as exc:
        logger.error("_analyze_at_llm 失败: symbol=%s as_of=%s error=%s", code, as_of, exc)
        return {"skipped": True, "reason": str(exc), "as_of": str(as_of), "symbol": code}


async def run_backtest_llm(symbol, start, end, step: int = 5, horizon: int = 10,
                           history_count: int = 150) -> dict:
    """LLM 模式回测：真实 VA + TA 子 Agent 逐点分析 + horizon 日验证 + 汇总统计。

    start/end 支持 date 或 "YYYY-MM-DD" 字符串。
    返回 {"meta": {...}, "decisions": [...], "summary": {...}}（meta.mode = "llm"）。
    注意：LLM 通用知识存在时点泄漏，回测结果仅代表引擎行为近似。
    """
    code = _normalize_symbol(symbol)
    start_date = _coerce_date(start)
    end_date = _coerce_date(end)

    dates = _list_trade_dates(code, start_date, end_date)
    step = max(1, int(step))
    sampled = dates[::step]

    decisions: list[dict] = []
    total = len(sampled)
    for i, d in enumerate(sampled):
        result = await _analyze_at_llm(code, d, history_count)

        action = result.get("action")
        evaluated = False
        verdict = None
        profit_ratio = None
        high_ratio = None
        low_ratio = None

        if not result.get("skipped") and action in ("BUY", "SELL"):
            try:
                future_bars = _fetch_future_bars(code, d, horizon)
                ev = _evaluate(action, float(result.get("close") or 0.0), future_bars, horizon)
                evaluated = bool(ev.get("evaluated", False))
                verdict = ev.get("verdict")
                profit_ratio = ev.get("profit_ratio")
                high_ratio = ev.get("high_ratio")
                low_ratio = ev.get("low_ratio")
            except Exception as exc:
                logger.warning("LLM 回测验证失败: symbol=%s as_of=%s error=%s", code, d, exc)

        decisions.append({
            "as_of": str(d),
            "symbol": result.get("symbol", code),
            "action": action,
            "direction": result.get("direction"),
            "confidence": result.get("confidence"),
            "final_score": result.get("final_score"),
            "close": result.get("close"),
            "evaluated": evaluated,
            "verdict": verdict,
            "profit_ratio": profit_ratio,
            "high_ratio": high_ratio,
            "low_ratio": low_ratio,
            "skipped": bool(result.get("skipped")),
            "valuation_missing": bool(result.get("valuation_missing")),
        })

        if (i + 1) % 5 == 0:
            logger.info("LLM 回测进度 %d/%d（%s）", i + 1, total, code)

    summary = _build_summary(decisions, dates, sampled)

    meta = {
        "symbol": code,
        "start": str(start_date),
        "end": str(end_date),
        "step": step,
        "horizon": horizon,
        "history_count": history_count,
        "mode": "llm",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return {"meta": meta, "decisions": decisions, "summary": summary}
