"""
自选股管理子 Agent — 业务逻辑 + 3 个独立 Tool + 结构化输出。

数据流：main_agent → 本模块 (WATCHLIST_SUBAGENT) → watchlist_service → MySQL

设计：
  - WatchlistResult  Pydantic 模型定义结构化输出 Schema
  - WatchlistAgent  类封装业务逻辑（静态方法）
  - 3 个 @tool       独立工具（add / remove / list）
  - WATCHLIST_SUBAGENT  注册配置（含 response_format）
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from langchain.tools import tool
from pydantic import BaseModel, Field

from agents.exceptions import STOCK_NOT_FOUND, WATCHLIST_OP_FAILED, degraded_message
from agents.stock_utils import resolve_symbol
from shared.config import get_llm

logger = logging.getLogger(__name__)


# ── 结构化输出 Schema ────────────────────────────────────────────────────────


class WatchlistResult(BaseModel):
    """自选股管理操作的标准化结果 — 子 Agent 返回给主 Agent 的 Schema。

    主 Agent 收到此 JSON 后可编程解析，而非处理自由文本。
    """

    success: bool = Field(description="操作是否成功")
    message: str = Field(description="面向用户的操作结果文本")
    action: str = Field(description="执行的操作类型：add / remove / list")
    stock_identifier: Optional[str] = Field(
        default=None, description="操作的股票标识（add/remove 时）"
    )
    items: Optional[list[dict]] = Field(
        default=None, description="自选股列表（list 操作时返回）"
    )


# ── 业务逻辑封装 ──────────────────────────────────────────────────────────────


class WatchlistAgent:
    """自选股管理子 Agent 逻辑封装（静态方法，供 @tool 调用）。"""

    @staticmethod
    def add(stock_identifier: str) -> WatchlistResult:
        if not stock_identifier:
            return WatchlistResult(
                success=False,
                message="请告诉我您想将哪只股票加入自选股，"
                "例如「关注茅台」或「把五粮液加入自选」。",
                action="add",
            )

        try:
            symbol = resolve_symbol(stock_identifier)
            if not symbol:
                return WatchlistResult(
                    success=False,
                    message=degraded_message(STOCK_NOT_FOUND),
                    action="add",
                    stock_identifier=stock_identifier,
                )

            from services.watchlist_service import add_to_watchlist

            added = add_to_watchlist(symbol)
            if added:
                return WatchlistResult(
                    success=True,
                    message=f"已将 {stock_identifier} 添加到自选股",
                    action="add",
                    stock_identifier=stock_identifier,
                )
            else:
                return WatchlistResult(
                    success=True,
                    message=f"{stock_identifier} 已在自选股中",
                    action="add",
                    stock_identifier=stock_identifier,
                )
        except Exception as e:
            logger.error("Add stock failed: %s", e)
            return WatchlistResult(
                success=False,
                message=degraded_message(WATCHLIST_OP_FAILED, detail=str(e)),
                action="add",
                stock_identifier=stock_identifier,
            )

    @staticmethod
    def remove(stock_identifier: str) -> WatchlistResult:
        if not stock_identifier:
            return WatchlistResult(
                success=False,
                message="请告诉我您想将哪只股票移出自选股，"
                "例如「移除茅台」或「把五粮液移出自选」。",
                action="remove",
            )

        try:
            symbol = resolve_symbol(stock_identifier)
            if not symbol:
                return WatchlistResult(
                    success=False,
                    message=degraded_message(STOCK_NOT_FOUND),
                    action="remove",
                    stock_identifier=stock_identifier,
                )

            from services.watchlist_service import remove_from_watchlist

            removed = remove_from_watchlist(symbol)
            if removed:
                return WatchlistResult(
                    success=True,
                    message=f"已将 {stock_identifier} 从自选股移除",
                    action="remove",
                    stock_identifier=stock_identifier,
                )
            else:
                return WatchlistResult(
                    success=True,
                    message=f"{stock_identifier} 不在自选股中",
                    action="remove",
                    stock_identifier=stock_identifier,
                )
        except Exception as e:
            logger.error("Remove stock failed: %s", e)
            return WatchlistResult(
                success=False,
                message=degraded_message(WATCHLIST_OP_FAILED, detail=str(e)),
                action="remove",
                stock_identifier=stock_identifier,
            )

    @staticmethod
    def list_all() -> WatchlistResult:
        try:
            from services.watchlist_service import get_watchlist

            watchlist = get_watchlist()
            if not watchlist:
                return WatchlistResult(
                    success=True,
                    message="您的自选股列表为空",
                    action="list",
                    items=[],
                )

            items: list[dict[str, Any]] = [
                {
                    "symbol": item.get("symbol", ""),
                    "name": item.get("name", ""),
                    "price": item.get("price", 0),
                    "change": item.get("change", 0),
                }
                for item in watchlist
            ]

            lines = ["您的自选股："]
            for item in items:
                change_str = f"{item['change']:+.2f}%" if item.get("change") else ""
                lines.append(f"• {item['symbol']} {item['name']} - {item['price']} {change_str}")

            return WatchlistResult(
                success=True,
                message="\n".join(lines),
                action="list",
                items=items,
            )
        except Exception as e:
            logger.error("List watchlist failed: %s", e)
            return WatchlistResult(
                success=False,
                message=degraded_message(WATCHLIST_OP_FAILED, detail=str(e)),
                action="list",
            )


# ── Tool 定义 ─────────────────────────────────────────────────────────────────


@tool
def add_watchlist(stock_identifier: str) -> str:
    """将指定股票添加到自选股列表。

    参数:
        stock_identifier: 股票代码（6位数字）或股票名称，如 "600519" 或 "贵州茅台"。
    """
    return WatchlistAgent.add(stock_identifier).model_dump_json()


@tool
def remove_watchlist(stock_identifier: str) -> str:
    """从自选股列表中移除指定股票。

    参数:
        stock_identifier: 股票代码（6位数字）或股票名称，如 "600519" 或 "贵州茅台"。
    """
    return WatchlistAgent.remove(stock_identifier).model_dump_json()


@tool
def list_watchlist() -> str:
    """查询当前自选股列表，返回所有自选股的代码、名称、价格和涨跌幅。
    无需参数，直接调用即可获得完整列表。
    """
    return WatchlistAgent.list_all().model_dump_json()


# ── SubAgent 注册配置 ─────────────────────────────────────────────────────────

SYSTEM_PROMPT = """你是投资罗盘的自选股管理子 Agent，负责处理用户的自选股操作。

## 可用工具

你有三个独立工具可用，每个工具返回 JSON 格式的结构化结果：

1. **add_watchlist(stock_identifier)** — 添加股票到自选股
   - stock_identifier: 股票代码（6位数字）或名称
   - 返回: {"success": true/false, "message": "...", "action": "add", "stock_identifier": "..."}

2. **remove_watchlist(stock_identifier)** — 从自选股移除股票
   - stock_identifier: 股票代码（6位数字）或名称
   - 返回: {"success": true/false, "message": "...", "action": "remove", "stock_identifier": "..."}

3. **list_watchlist()** — 查询自选股列表
   - 无参数，直接调用
   - 返回: {"success": true, "message": "...", "action": "list", "items": [...]}

## 工作流程

1. 分析用户输入，判断操作类型
2. 提取股票代码或名称（仅 add/remove 时需要）
3. 调用对应的工具
4. 将工具返回的结果整理为标准 WatchlistResult 输出

## 对话示例

用户：「帮我关注贵州茅台」
→ 工具: add_watchlist(stock_identifier="贵州茅台")
→ 输出: {"success": true, "message": "已将 贵州茅台 添加到自选股", "action": "add", "stock_identifier": "贵州茅台"}

用户：「把五粮液移出自选」
→ 工具: remove_watchlist(stock_identifier="五粮液")
→ 输出: {"success": true, "message": "已将 五粮液 从自选股移除", "action": "remove", "stock_identifier": "五粮液"}

用户：「我的自选股」
→ 工具: list_watchlist()
→ 输出: {"success": true, "message": "您的自选股：\\n• 600519 贵州茅台 - 1800.00 +0.50%", "action": "list", "items": [{"symbol": "600519", "name": "贵州茅台", "price": 1800.0, "change": 0.5}]}

## 输出要求

- 严格按照 WatchlistResult 格式输出结构化 JSON
- 如实反映工具返回的数据，不要编造
- 操作失败时在 message 中说明原因
- 始终以中文回答"""

WATCHLIST_SUBAGENT: dict = {
    "name": "watchlist_manage",
    "description": "管理自选股：添加股票(add)、移除股票(remove)、查询自选股列表(list)",
    # 工具型结构化子 Agent：DeepSeek thinking 模式不支持 tool_choice，
    # 而 create_agent 对 response_format + tools 会强制 tool_choice → 必须关闭 thinking
    "model": get_llm(enable_thinking=False),
    "system_prompt": SYSTEM_PROMPT,
    "tools": [add_watchlist, remove_watchlist, list_watchlist],
    "response_format": WatchlistResult,
}
