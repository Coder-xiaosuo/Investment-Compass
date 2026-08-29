"""AI Reader SubAgent — 看板卡片即时解读子 Agent。

作为 DeepAgents SubAgent 注册（路径①：原始 spec，middleware 显式挂载
MemoryMiddleware 实现「记忆统一」）。面向操盘模式看板右上角「AI分析」按钮：

- 子 Agent 通过 `read_card_data` 工具获取指定股票某张卡片的**数据快照**（纯函数，
  复用 K线指标 / 资金流 / 股东户数 / 筹码成本 / 目标价决策），不依赖完整
  两阶段决策引擎，单次 LLM 输出结构化解读（summary / key_points / risks）。
- **记忆统一**：middleware 传入与主 Agent 相同的 MemoryMiddleware（同一 backend +
  同一 sources），子 Agent 读取同一份 AGENTS.md / preferences.md。
- **记忆只读**：system_prompt 明确禁止 edit_file/write_file，记忆沉淀统一由
  主 Agent 管理，避免多 Agent 并发写记忆文件。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from langchain.tools import tool
from pydantic import BaseModel, Field

from shared.config import get_llm, settings

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Structured output schema
# ──────────────────────────────────────────────────────────────────────────────


class CardInterpretation(BaseModel):
    """看板卡片解读结构化结果——ai_reader 返回给主 Agent 的 Schema。"""

    symbol: str = Field(description="股票代码")
    stock_name: str = Field(description="股票名称")
    card_type: str = Field(description="卡片类型：technical / fundflow / chip / shareholder / target")
    summary: str = Field(description="1 段核心解读（结合数据快照与用户偏好）")
    key_points: list[str] = Field(default_factory=list, description="结构化要点列表（2-4 条）")
    risks: list[str] = Field(default_factory=list, description="风险提示列表（0-2 条）")


# ──────────────────────────────────────────────────────────────────────────────
# 数据工具（纯函数，无 LLM）——按卡片类型聚合数据快照
# ──────────────────────────────────────────────────────────────────────────────


def _resolve_code(symbol: str) -> str:
    """解析 6 位股票代码（统一走 DB 补全交易所后缀）。"""
    from agents.stock_utils import resolve_symbol

    return resolve_symbol(symbol) or symbol


def _stock_name(code: str) -> str:
    try:
        from services.stock_metadata_service import search_stocks

        matches = search_stocks(code, limit=1)
        if matches:
            return matches[0].get("stockName") or matches[0].get("stock_name") or code
    except Exception as exc:  # noqa: BLE001
        logger.warning("stock_name lookup failed %s: %s", code, exc)
    return code


@tool
def read_card_data(symbol: str, card_type: str) -> str:
    """获取指定股票某张看板卡片的数据快照（纯函数，无 LLM 调用）。

    按卡片类型返回结构化的数据 JSON，供 AI 解读子 Agent 结合用户偏好做即时解读：

    参数:
        symbol: 股票代码（6位数字，如 600519）。
        card_type: 卡片类型，可选值：
          - "technical" 技术面 K线/趋势/量能/支撑阻力
          - "fundflow"  大单资金流向（主力净流入/汇总/当日快照）
          - "chip"      筹码成本（近60日量价加权平均成本/获利盘占比）
          - "shareholder" 散户数量（股东户数历史变化/增减趋势）
          - "target"    目标价决策（主控台最近 composite_decision 的 TechnicalResult）

    返回:
        对应卡片的数据快照 JSON 字符串。
    """
    code = _resolve_code(symbol)
    if not code:
        return json.dumps({"error": True, "error_message": f"无法识别股票代码: {symbol}"}, ensure_ascii=False)

    if card_type == "technical":
        return _snapshot_technical(code)
    if card_type == "fundflow":
        return _snapshot_fundflow(code)
    if card_type == "chip":
        return _snapshot_chip(code)
    if card_type == "shareholder":
        return _snapshot_shareholder(code)
    if card_type == "target":
        return _snapshot_target(code)

    return json.dumps({"error": True, "error_message": f"未知卡片类型: {card_type}"}, ensure_ascii=False)


def _snapshot_technical(code: str) -> str:
    """技术面：复用 PA 纯算法指标（K线摘要/趋势/量能/波动率/支撑阻力）。"""
    try:
        from agents.pa_agent import _compute_market_data  # noqa: PLC0415
        from agents.stock_utils import get_kline_bars  # noqa: PLC0415

        bars = get_kline_bars(code, "1d", 100)
        if not bars:
            return json.dumps({"error": True, "error_message": f"无法获取 {code} 的 K 线数据"}, ensure_ascii=False)
        data = _compute_market_data(bars)
        return json.dumps({
            "symbol": code,
            "stock_name": _stock_name(code),
            "card_type": "technical",
            "market_data": data,
        }, ensure_ascii=False, default=str)
    except Exception as exc:  # noqa: BLE001
        logger.error("technical snapshot failed %s: %s", code, exc)
        return json.dumps({"error": True, "error_message": f"技术面数据获取失败: {exc}"}, ensure_ascii=False)


def _snapshot_fundflow(code: str) -> str:
    """资金流：东财逐日（daily）优先，失败降级同花顺当日快照（snapshot）。"""
    try:
        from services.demo_flow_service import get_stock_fundflow  # noqa: PLC0415

        payload = get_stock_fundflow(code, days=10)
        if payload.get("error"):
            return json.dumps(payload, ensure_ascii=False)
        return json.dumps({
            "symbol": code,
            "stock_name": _stock_name(code),
            "card_type": "fundflow",
            "source": payload.get("source"),
            "mode": payload.get("mode"),
            "daily": payload.get("daily"),
            "summary": payload.get("summary"),
            "snapshot": payload.get("snapshot"),
        }, ensure_ascii=False, default=str)
    except Exception as exc:  # noqa: BLE001
        logger.error("fundflow snapshot failed %s: %s", code, exc)
        return json.dumps({"error": True, "error_message": f"资金流数据获取失败: {exc}"}, ensure_ascii=False)


def _snapshot_chip(code: str) -> str:
    """筹码成本：近 60 日量价加权平均成本 + 现价位置 + 获利盘估算（替代算法，DEMO）。"""
    try:
        from agents.stock_utils import get_kline_bars  # noqa: PLC0415

        bars = get_kline_bars(code, "1d", 60)
        if not bars:
            return json.dumps({"error": True, "error_message": f"无法获取 {code} 的 K 线数据"}, ensure_ascii=False)
        # bars[0] 为最新（newest-first）
        closes = [b.close for b in bars]
        volumes = [b.volume for b in bars]
        current = closes[0]
        total_v = sum(volumes) or 1.0
        avg_cost = sum(c * v for c, v in zip(closes, volumes)) / total_v
        high_60 = max(b.high for b in bars)
        low_60 = min(b.low for b in bars)
        # 获利盘占比：现价下方的收盘价成交量占比（近似）
        profit_volume = sum(v for c, v in zip(closes, volumes) if c <= current)
        profit_ratio = round(profit_volume / total_v * 100, 1)
        return json.dumps({
            "symbol": code,
            "stock_name": _stock_name(code),
            "card_type": "chip",
            "current_price": round(current, 2),
            "avg_cost": round(avg_cost, 2),
            "profit_ratio_pct": profit_ratio,
            "trapped_ratio_pct": round(100 - profit_ratio, 1),
            "high_60d": round(high_60, 2),
            "low_60d": round(low_60, 2),
            "note": "成交密集区替代算法（DEMO）：近60日量价加权",
        }, ensure_ascii=False, default=str)
    except Exception as exc:  # noqa: BLE001
        logger.error("chip snapshot failed %s: %s", code, exc)
        return json.dumps({"error": True, "error_message": f"筹码成本获取失败: {exc}"}, ensure_ascii=False)


def _snapshot_shareholder(code: str) -> str:
    """散户数量：股东户数历史变化（最新户数/环比增减/近期增减趋势）。"""
    try:
        from services.demo_flow_service import get_shareholder_count  # noqa: PLC0415

        payload = get_shareholder_count(code)
        if payload.get("error"):
            return json.dumps(payload, ensure_ascii=False)
        rows = payload.get("rows") or []
        if not rows:
            return json.dumps({
                "symbol": code,
                "stock_name": _stock_name(code),
                "card_type": "shareholder",
                "error": True,
                "error_message": "该股暂无股东户数数据",
            }, ensure_ascii=False)
        latest = rows[0]  # 最新一期（rows 为时间倒序）
        # 近 5 期增减方向统计（正=户数增/筹码分散，负=户数减/筹码集中）
        recent = rows[: min(5, len(rows))]
        up_days = sum(1 for r in recent if (r.get("change") or 0) > 0)
        down_days = sum(1 for r in recent if (r.get("change") or 0) < 0)
        return json.dumps({
            "symbol": code,
            "stock_name": _stock_name(code),
            "card_type": "shareholder",
            "latest_date": latest.get("date", ""),
            "latest_count": latest.get("count"),
            "latest_change": latest.get("change"),
            "latest_change_pct": latest.get("change_pct"),
            "recent_periods": len(recent),
            "recent_up_periods": up_days,
            "recent_down_periods": down_days,
            "note": "股东户数增多=筹码分散（偏空信号）；减少=筹码集中（偏多信号）",
        }, ensure_ascii=False, default=str)
    except Exception as exc:  # noqa: BLE001
        logger.error("shareholder snapshot failed %s: %s", code, exc)
        return json.dumps({"error": True, "error_message": f"散户数量获取失败: {exc}"}, ensure_ascii=False)


def _snapshot_target(code: str) -> str:
    """目标价：从 message 表取该股最近 composite_decision 的 card_data.result（TechnicalResult）。"""
    try:
        from sqlalchemy import create_engine, text  # noqa: PLC0415

        engine = create_engine(
            settings.DATABASE_URL,
            pool_pre_ping=True,
            pool_size=1,
            max_overflow=0,
            pool_recycle=300,
            pool_timeout=10,
        )
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT card_data FROM message "
                    "WHERE content_type='composite_decision' AND card_data IS NOT NULL "
                    "ORDER BY id DESC LIMIT 50"
                )
            ).fetchall()
        engine.dispose()
        for (card_json,) in rows:
            try:
                card = json.loads(card_json) if isinstance(card_json, str) else (card_json or {})
            except (ValueError, TypeError):
                continue
            result = card.get("result") or {}
            sym = card.get("symbol") or result.get("stock_code") or ""
            if sym and code in str(sym):
                # 仅当存在 TA 结果（resistance 非空）时才视为目标价记录；
                # 估值结果（无 resistance）不算 AI 目标价预测，继续查更早记录
                if result.get("resistance") is None:
                    continue
                payload = {
                    "symbol": code,
                    "stock_name": _stock_name(code),
                    "card_type": "target",
                    "resistance": result.get("resistance"),
                    "support": result.get("support"),
                    "entry_price": result.get("entry_price"),
                    "estimated_win_rate": result.get("estimated_win_rate"),
                    "direction": result.get("direction"),
                    "confidence": result.get("confidence"),
                    "summary": result.get("summary", ""),
                    "key_factors": result.get("key_factors", []),
                    "risk_warnings": result.get("risk_warnings", []),
                    "analyzed_at": card.get("created_at"),
                }
                return json.dumps(payload, ensure_ascii=False, default=str)
        return json.dumps({
            "symbol": code,
            "stock_name": _stock_name(code),
            "card_type": "target",
            "error": True,
            "error_message": "该股暂无 AI 目标价分析记录",
        }, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        logger.error("target snapshot failed %s: %s", code, exc)
        return json.dumps({"error": True, "error_message": f"目标价记录读取失败: {exc}"}, ensure_ascii=False)


# ──────────────────────────────────────────────────────────────────────────────
# SubAgent definition（路径①：原始 spec + 显式 MemoryMiddleware 记忆统一）
# ──────────────────────────────────────────────────────────────────────────────

_READER_SYSTEM_PROMPT = """你是投资罗盘看板的数据解读助手。用户点击看板卡片右上角的「AI分析」，请求你对**指定股票的某张卡片数据**做即时、简洁的解读。

## 工作流程

1. 确认股票代码与卡片类型（technical / fundflow / chip / shareholder / target）
2. 调用 `read_card_data` 工具获取该卡片的数据快照
3. 结合数据快照与 <agent_memory> 中的用户偏好（风险偏好、关注维度等），输出结构化的 CardInterpretation

## 解读要求

- **summary**：1 段核心解读（3-5 句），直接说明当前状态与含义，引用快照中的关键数值（如现价、净流入、平均成本、目标价）
- **key_points**：2-4 条结构化要点，每条一句，突出最有信息量的信号（放量/缩量、主力方向、获利盘占比、支撑阻力距离等）
- **risks**：0-2 条风险提示（数据降级、外部数据源不可用、算法近似等如实说明）
- 语言：中文；风格克制、数据驱动，不编造快照中不存在的数值

## 记忆规则（只读）

- <agent_memory> 仅供阅读参考（用户偏好、项目规则），用于调整解读口径
- **禁止**调用 edit_file / write_file / delete 等写操作工具；记忆沉淀统一由主 Agent 管理
- 绝不输出任何敏感信息或 API Key"""


def build_ai_reader_subagent(fs_backend: Any) -> dict:
    """构建 ai_reader 子 Agent（原始 SubAgent spec）。

    Args:
        fs_backend: 与主 Agent 相同的文件系统 backend（CompositeBackend），
            用于 MemoryMiddleware 读取同一份记忆文件，实现记忆统一。
    """
    from deepagents.middleware.memory import MemoryMiddleware  # noqa: PLC0415

    return {
        "name": "ai_reader",
        "description": (
            "看板卡片即时解读：对指定股票某张看板卡片的当前数据（技术面指标/"
            "大单资金流/筹码成本/散户数量/目标价决策）做结构化解读与风险提示。"
            "适用于操盘模式看板右上角「AI分析」；输出 summary/key_points/risks。"
        ),
        "system_prompt": _READER_SYSTEM_PROMPT,
        # 工具型结构化子 Agent：DeepSeek thinking 模式不支持 tool_choice，
        # 而 create_agent 对 response_format + tools 会强制 tool_choice → 必须关闭 thinking
        "model": get_llm(enable_thinking=False),
        "tools": [read_card_data],
        # 记忆统一：与主 Agent 同一 backend + 同一 sources，读取同一份记忆
        "middleware": [
            MemoryMiddleware(
                backend=fs_backend,
                sources=["/AGENTS.md", "/memories/preferences.md"],
            )
        ],
        "response_format": CardInterpretation,
    }
