"""AI 卡片解读服务 — 独立运行 ai_reader 子 Agent，返回结构化解读。

操盘模式看板右上角「AI分析」按钮的后端链路：不经过完整两阶段决策引擎、
不写入会话历史，直接编译 ai_reader SubAgent spec（同一份记忆 backend，
读同一份 AGENTS.md / preferences.md），调用 `read_card_data` 取数据快照后
输出 CardInterpretation（summary / key_points / risks）。

说明：解读结果不沉淀记忆（ai_reader 只读；沉淀统一由主 Agent 管理），
每次点击均为即时解读。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 与 main_agent.py 保持一致：ai_reader 支持的五类卡片
CARD_TYPES = ("technical", "fundflow", "chip", "shareholder", "target")


async def interpret_card(symbol: str, card_type: str) -> dict[str, Any]:
    """独立运行 ai_reader 子 Agent，返回 CardInterpretation dict。

    Args:
        symbol: 股票代码（6 位，如 600519）。
        card_type: technical / fundflow / chip / target。

    Returns:
        结构化解读 dict；失败时返回 ``{"error": True, "error_message": ...}``。
    """
    if card_type not in CARD_TYPES:
        return {"error": True, "error_message": f"未知卡片类型: {card_type}，可选 {CARD_TYPES}"}

    try:
        from agents.ai_reader_agent import build_ai_reader_subagent
        from deepagents.backends import FilesystemBackend
        from deepagents.middleware.subagents import create_sub_agent

        # 同一份记忆 backend（虚拟文件系统读同一份文件）→ 记忆统一
        project_dir = Path(__file__).resolve().parent.parent
        memory_backend = FilesystemBackend(root_dir=project_dir, virtual_mode=True)
        spec = build_ai_reader_subagent(memory_backend)
        runnable = create_sub_agent(spec)

        prompt = f"请对 {symbol} 的 {card_type} 卡片执行即时解读，并返回结构化结果。"
        result = await runnable.ainvoke({"messages": [{"role": "user", "content": prompt}]})

        payload = _extract_interpretation(result)
        if payload is None:
            return {
                "error": True,
                "error_message": "ai_reader 未返回结构化解读结果，请稍后重试",
            }
        # 保证响应含 symbol / stock_name（解读失败兜底用代码）
        payload.setdefault("symbol", symbol)
        return payload

    except Exception as exc:  # noqa: BLE001
        logger.error("interpret_card failed %s/%s: %s", symbol, card_type, exc, exc_info=True)
        return {"error": True, "error_message": f"AI 解读失败: {exc}"}


def _extract_interpretation(result: dict[str, Any]) -> dict[str, Any] | None:
    """从子 Agent 运行结果提取 CardInterpretation。

    优先取 ``structured_response``（结构化输出通道）；缺失时回溯最后一条
    非空 AI 消息并尝试按 JSON 解析（response_format 兜底路径）。
    """
    structured = result.get("structured_response")
    if structured is not None:
        if hasattr(structured, "model_dump"):
            return structured.model_dump()
        if isinstance(structured, dict):
            return structured

    messages = result.get("messages") or []
    for msg in reversed(messages):
        text = ""
        if isinstance(msg, dict):
            if msg.get("type") == "ai":
                text = msg.get("content") or ""
        elif getattr(msg, "type", "") == "ai":
            text = getattr(msg, "content", "") or ""
        if not text:
            continue
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            continue
    return None
