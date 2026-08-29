"""应用异常码与降级提示 — 统一管理所有标准错误码和对应的用户提示文本。"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


# ── 标准错误码 ──────────────────────────────────────────────────────────────

# Agent 级错误
MISSING_API_KEY = "missing_api_key"
AGENT_ERROR = "agent_error"
AGENT_UNAVAILABLE = "agent_unavailable"

# 股票相关
STOCK_NOT_FOUND = "stock_not_found"
KLINE_DATA_MISSING = "kline_data_missing"
INSUFFICIENT_BARS = "insufficient_bars"
ANALYSIS_FAILED = "analysis_failed"

# 意图相关
UNSUPPORTED_INTENT = "unsupported_intent"

# 自选股相关
WATCHLIST_OP_FAILED = "watchlist_op_failed"


# ── 错误码 → 用户提示文本 ───────────────────────────────────────────────────

_DEGRADED_MESSAGES: dict[str, str] = {
    MISSING_API_KEY: (
        "投资罗盘暂时无法提供服务：AI 分析引擎未配置。"
        "请联系管理员配置 API Key 后重试。"
    ),
    AGENT_ERROR: (
        "投资罗盘暂时无法提供服务：分析引擎遇到异常。"
    ),
    AGENT_UNAVAILABLE: (
        "投资罗盘暂时无法提供服务，请稍后重试。"
    ),
    STOCK_NOT_FOUND: (
        "未找到相关股票数据。\n\n"
        "可能的原因：\n"
        "1. 该股票可能在港股或美股交易\n"
        "2. 股票名称输入有误，请尝试使用6位数字代码\n\n"
        "提示：当前仅支持A股市场。"
    ),
    KLINE_DATA_MISSING: (
        "无法获取该股票的行情数据。\n\n"
        "可能的原因：\n"
        "1. 股票代码输入有误\n"
        "2. 该股票暂无交易数据\n"
        "3. 数据库连接异常\n\n"
        "请检查股票代码是否正确，或稍后重试。"
    ),
    ANALYSIS_FAILED: (
        "分析该股票时出现异常，请稍后重试，或检查股票代码是否正确。"
    ),
    UNSUPPORTED_INTENT: (
        "暂不支持该功能。\n\n"
        "当前支持：股票分析、行情查询、自选股管理等。"
    ),
    WATCHLIST_OP_FAILED: (
        "自选股操作失败，请稍后重试。"
    ),
}

# ── 兜底提示 ─────────────────────────────────────────────────────────────────

_GENERIC_MESSAGE = "投资罗盘暂时无法处理您的请求，请稍后重试。"


def degraded_message(error_code: str, detail: str = "") -> str:
    """根据错误码返回标准降级提示文本。

    Args:
        error_code: 标准错误码，来自本模块的常量。
        detail: 可选的详细错误信息，追加在提示文本末尾。

    Returns:
        面向用户的友好提示文本。
    """
    msg = _DEGRADED_MESSAGES.get(error_code, _GENERIC_MESSAGE)
    if detail:
        msg = f"{msg}\n\n（错误详情：{detail}）"
    return msg
