"""Experience Injection Middleware.

Injects relevant historical experience entries into sub-agent prompts
before analysis.  This is called by ``agent_router`` before dispatching
to a sub-agent.

Usage::

    from middleware.experience_injection import inject_experience

    context = inject_experience(entities, context)
    # context now contains ``experience_refs`` with formatted text
"""

from __future__ import annotations

import logging
from typing import Any

from models.experience_entry import ExperienceQuery
from services.experience_library import get_experience_library

logger = logging.getLogger(__name__)

# Max entries to inject
_MAX_ENTRIES = 3

# 注入预算治理：单条案例 ≤400 字、总注入 ≤1200 字（超限截断，保留开头 + 省略标记）
_MAX_PER_ENTRY_CHARS = 400
_MAX_TOTAL_CHARS = 1200


def _truncate_text(text: str, max_chars: int) -> str:
    """按字符数截断文本：保留开头，超出部分以省略标记收尾（总长不超过 max_chars）。"""
    if max_chars <= 0 or not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def inject_experience(
    entities: dict[str, Any],
    context: dict[str, Any] | None = None,
    user_intent: str = "",
) -> dict[str, Any]:
    """Query the experience library and inject relevant cases into *context*.

    Parameters
    ----------
    entities:
        Intention entities, expected to contain ``symbol``, ``stock_name``,
        ``market_cycle``, ``sector``, etc.
    context:
        Existing context dict (optional).  A new one is created when
        ``None``.
    user_intent:
        用户原始意图文本（可选）。提供时优先作为语义查询文本（与股票名称组合）；
        未提供时回退到 stock_name + market_cycle + sector。market_cycle /
        sector 不强依赖——只要存在可检索的语义文本即尝试查询。

    Returns
    -------
    dict[str, Any]
        The *context* dict (or a new one) with the key
        ``experience_refs`` populated with formatted reference text.
        If no entries are found, ``experience_refs`` is an empty string.
        任何查询异常均返回空字符串，绝不向上抛异常。
    """
    if context is None:
        context = {}

    # Build query from entities
    market_cycle = entities.get("market_cycle", "") or context.get("market_cycle", "")
    sector = entities.get("sector", "") or context.get("sector", "")
    stock_name = entities.get("stock_name", "")

    # 语义查询文本：优先 user_intent 原文 + 股票名称；无 user_intent 时保持
    # 原有 stock_name + market_cycle + sector 组合
    query_text_parts = []
    if user_intent:
        query_text_parts.append(user_intent)
        if stock_name:
            query_text_parts.append(stock_name)
    else:
        if stock_name:
            query_text_parts.append(stock_name)
        if market_cycle:
            query_text_parts.append(market_cycle)
        if sector:
            query_text_parts.append(sector)
    query_text = " ".join(query_text_parts) or ""

    # market_cycle 不强依赖：只要存在可检索的语义文本就尝试查询
    if not query_text:
        # 没有任何可检索依据 —— 跳过注入
        context["experience_refs"] = ""
        return context

    query = ExperienceQuery(
        market_cycle=market_cycle,
        sector=sector,
        query_text=query_text,
        top_k=_MAX_ENTRIES,
    )

    try:
        lib = get_experience_library()
        entries = lib.query(query)
    except Exception:
        logger.warning("Experience injection: query failed", exc_info=True)
        context["experience_refs"] = ""
        return context

    if not entries:
        logger.debug("Experience injection: no relevant entries found")
        context["experience_refs"] = ""
        return context

    # 格式化条目为 markdown；反例（outcome.verdict == MISS）最多保留 1 条，
    # 并加「⚠️ 失败反例」前缀 + 复盘关键信息（profit_ratio / actual_trend）。
    # 排序仍按检索分数，仅对多余的 MISS 丢弃。
    # 每条案例的行先独立收集到 blocks，便于最后统一做注入预算截断。
    header = "## 历史参考案例\n"
    blocks: list[list[str]] = []
    miss_shown = 0
    idx = 0
    for entry in entries:
        summary = entry.analysis_summary or {}
        outcome = entry.outcome or {}
        verdict = str(outcome.get("verdict", "")).upper()
        is_miss = verdict == "MISS"

        if is_miss:
            miss_shown += 1
            if miss_shown > 1:
                # 反例只保留 1 条，超过的丢弃（排序仍按分数）
                continue

        idx += 1
        title = f"### 案例 {idx}: {entry.stock_name}({entry.stock_code})"
        if is_miss:
            title = (
                f"### 案例 {idx}: ⚠️ 失败反例（相同信号曾导致判断失误）"
                f"{entry.stock_name}({entry.stock_code})"
            )
        block_lines: list[str] = [title]
        if entry.market_cycle:
            block_lines.append(f"- 市场周期: {entry.market_cycle}")
        if entry.pattern:
            block_lines.append(f"- 形态: {entry.pattern}")
        if entry.sector:
            block_lines.append(f"- 板块: {entry.sector}")

        val = summary.get("valuation", "")
        pa = summary.get("pa_conclusion", "")
        dec = summary.get("final_decision", "")
        if val:
            block_lines.append(f"- 估值结论: {val}")
        if pa:
            block_lines.append(f"- 技术分析: {pa}")
        if dec:
            block_lines.append(f"- 最终决策: {dec}")

        # 反例附上复盘关键信息（实际走势 + 盈亏），其余条目保持原有展示
        actual = outcome.get("actual_trend", "")
        if actual:
            block_lines.append(f"- 后续走势: {actual}")
        if is_miss:
            profit = outcome.get("profit_ratio")
            if profit is not None:
                block_lines.append(f"- 实际盈亏: {float(profit) * 100:.2f}%")

        blocks.append(block_lines)

    # ── 注入预算治理 ──
    # 单条案例 ≤ _MAX_PER_ENTRY_CHARS 字、总注入 ≤ _MAX_TOTAL_CHARS 字；
    # 超限截断（保留开头 + 省略标记），总预算耗尽后丢弃后续案例。
    total_chars = len(header)
    rendered: list[str] = []
    for block_lines in blocks:
        block_text = "\n".join(block_lines)
        # 单条预算：先按条截断
        block_text = _truncate_text(block_text, _MAX_PER_ENTRY_CHARS)
        # 总预算：为块间空行预留 1 字符
        remain = _MAX_TOTAL_CHARS - total_chars
        if remain <= 0:
            break
        if len(block_text) + 1 > remain:
            if remain > 1:
                rendered.append(_truncate_text(block_text, remain - 1))
            break
        rendered.append(block_text)
        total_chars += len(block_text) + 1

    context["experience_refs"] = header + "\n\n".join(rendered)

    logger.info(
        "Injected %d experience entries for %s", len(entries), stock_name or "unknown"
    )
    return context


def format_experience_for_prompt(
    experience_refs: str,
    target_agent: str = "",
) -> str:
    """Wrap experience refs into a prompt-friendly block.

    If *experience_refs* is empty, returns an empty string.
    """
    if not experience_refs:
        return ""

    header = (
        f"以下是与当前分析标的相关或同板块的历史分析案例，"
        f"供 {target_agent} 分析时参考。请注意历史表现不代表未来结果。\n\n"
        if target_agent
        else ""
    )
    return f"{header}{experience_refs}\n"
