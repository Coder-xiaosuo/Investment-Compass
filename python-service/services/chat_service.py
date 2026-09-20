"""Chat service — 对话与消息管理。"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Optional

from sqlalchemy import text
from langchain_core.messages.utils import count_tokens_approximately

from shared.config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


from agents.exceptions import degraded_message

logger = logging.getLogger(__name__)

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


def _row_to_dict(row, cols: list[str]) -> dict[str, Any]:
    d = {}
    for col in cols:
        val = getattr(row, col, None)
        if isinstance(val, datetime):
            val = val.strftime("%Y-%m-%d %H:%M:%S")
        d[col] = val
    return d


def create_conversation(title: str = "新会话", kind: str = "analysis") -> dict:
    session = _session()
    try:
        # 右侧对话（panel）默认标题："新对话 + 序号"（按同 kind 已有数量递增）
        if kind == "panel" and title in ("", "新会话"):
            count = session.execute(
                text("SELECT COUNT(*) FROM conversation WHERE kind = :kind"),
                {"kind": kind},
            ).scalar() or 0
            title = f"新对话 {count + 1}"
        result = session.execute(
            text("INSERT INTO conversation (title, status, kind) VALUES (:title, 1, :kind)"),
            {"title": title, "kind": kind},
        )
        session.commit()
        conv_id = result.lastrowid
        row = session.execute(
            text("SELECT * FROM conversation WHERE id = :cid"),
            {"cid": conv_id},
        ).fetchone()
        cols = ["id", "title", "user_id", "status", "kind", "summary", "token_count", "message_count", "context_tokens", "created_at", "updated_at"]
        return _row_to_dict(row, cols) if row else {"id": conv_id, "title": title, "status": 1, "kind": kind, "message_count": 0}
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def list_conversations(status: int = 1, kind: str | None = None) -> list[dict]:
    session = _session()
    try:
        if kind:
            rows = session.execute(
                text("SELECT * FROM conversation WHERE status = :status AND kind = :kind ORDER BY updated_at DESC"),
                {"status": status, "kind": kind},
            ).fetchall()
        else:
            rows = session.execute(
                text("SELECT * FROM conversation WHERE status = :status ORDER BY updated_at DESC"),
                {"status": status},
            ).fetchall()
        cols = ["id", "title", "user_id", "status", "kind", "summary", "token_count", "message_count", "context_tokens", "created_at", "updated_at"]
        return [_row_to_dict(r, cols) for r in rows]
    finally:
        session.close()


def rename_conversation(conv_id: int, title: str) -> bool:
    """重命名会话标题（右侧对话栏顶部 ✎ 编辑）。"""
    session = _session()
    try:
        result = session.execute(
            text("UPDATE conversation SET title = :t WHERE id = :cid"),
            {"t": title, "cid": conv_id},
        )
        session.commit()
        return result.rowcount > 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_conversation(conv_id: int) -> Optional[dict]:
    session = _session()
    try:
        row = session.execute(
            text("SELECT * FROM conversation WHERE id = :cid"),
            {"cid": conv_id},
        ).fetchone()
        if not row:
            return None
        cols = ["id", "title", "user_id", "status", "kind", "summary", "token_count", "message_count", "context_tokens", "created_at", "updated_at"]
        return _row_to_dict(row, cols)
    finally:
        session.close()


def archive_conversation(conv_id: int) -> bool:
    session = _session()
    try:
        result = session.execute(
            text("UPDATE conversation SET status = 2 WHERE id = :cid"),
            {"cid": conv_id},
        )
        session.commit()
        return result.rowcount > 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def delete_conversation(conv_id: int) -> bool:
    session = _session()
    try:
        session.execute(
            text("DELETE FROM message WHERE conversation_id = :cid"),
            {"cid": conv_id},
        )
        result = session.execute(
            text("DELETE FROM conversation WHERE id = :cid"),
            {"cid": conv_id},
        )
        session.commit()
        return result.rowcount > 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_messages(conv_id: int, page: int = 1, page_size: int = 30) -> dict:
    session = _session()
    try:
        offset = (page - 1) * page_size
        rows = session.execute(
            text("SELECT * FROM message WHERE conversation_id = :cid ORDER BY sequence ASC LIMIT :lim OFFSET :off"),
            {"cid": conv_id, "lim": page_size, "off": offset},
        ).fetchall()
        total = session.execute(
            text("SELECT COUNT(*) FROM message WHERE conversation_id = :cid"),
            {"cid": conv_id},
        ).scalar()
        cols = ["id", "conversation_id", "role", "content", "content_type", "card_data", "token_count", "sequence", "parent_id", "tool_name", "tool_result", "created_at"]
        items = [_row_to_dict(r, cols) for r in rows]
        return {"items": items, "total": total, "page": page, "page_size": page_size}
    finally:
        session.close()


def send_message(conv_id: int, content: str, content_type: str = "text") -> dict:
    session = _session()
    try:
        result = session.execute(
            text("SELECT MAX(sequence) FROM message WHERE conversation_id = :cid"),
            {"cid": conv_id},
        ).scalar()
        max_seq = result if result is not None else 0
        new_seq = max_seq + 1

        result = session.execute(
            text("""
                INSERT INTO message (conversation_id, role, content, content_type, sequence)
                VALUES (:cid, 'user', :content, :ctype, :seq)
            """),
            {"cid": conv_id, "content": content, "ctype": content_type, "seq": new_seq},
        )
        session.commit()
        user_msg_id = result.lastrowid

        _auto_update_title(conv_id, content)

        user_msg = session.execute(
            text("SELECT * FROM message WHERE id = :mid"),
            {"mid": user_msg_id},
        ).fetchone()
        msg_cols = ["id", "conversation_id", "role", "content", "content_type", "card_data", "token_count", "sequence", "parent_id", "tool_name", "tool_result", "created_at"]

        assistant_msg = _agent_reply(conv_id, user_msg_id, content)

        return {
            "user_message": _row_to_dict(user_msg, msg_cols) if user_msg else None,
            "assistant_message": assistant_msg,
        }
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_and_send(content: str, title: str | None = None) -> dict:
    if not title:
        title = "新会话"
    conv = create_conversation(title)
    conv_id = conv["id"]
    msg_result = send_message(conv_id, content)
    return {
        "conversation": conv,
        "user_message": msg_result["user_message"],
        "assistant_message": msg_result["assistant_message"],
    }


def _auto_update_title(conv_id: int, content: str) -> None:
    session = _session()
    try:
        row = session.execute(
            text("SELECT title FROM conversation WHERE id = :cid"),
            {"cid": conv_id},
        ).fetchone()
        if row and row.title == "新会话":
            new_title = content[:20]
            if len(content) > 20:
                new_title += "..."
            session.execute(
                text("UPDATE conversation SET title = :t, message_count = message_count + 1 WHERE id = :cid"),
                {"t": new_title, "cid": conv_id},
            )
            session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _agent_reply(conv_id: int, user_msg_id: int, user_content: str) -> dict:
    session = _session()
    try:
        result = session.execute(
            text("SELECT MAX(sequence) FROM message WHERE conversation_id = :cid"),
            {"cid": conv_id},
        ).scalar()
        max_seq = result if result is not None else 0
        new_seq = max_seq + 1

        # ── Phase 1: 优先使用主 Agent ───────────────────────────────────────────
        main_content = None

        try:
            from agents.main_agent import ainvoke as main_ainvoke
            import asyncio

            main_result = asyncio.run(main_ainvoke(user_content))

            error_ctx = main_result.get("error_context")
            if not error_ctx:
                main_content = main_result.get("content", "")
            else:
                logger.warning(
                    "Main agent returned error, falling back: %s",
                    error_ctx.get("detail", ""),
                )
        except Exception as e:
            logger.warning("Main agent call failed, falling back: %s", e, exc_info=True)

        # ── Phase 2: 主 Agent 成功 → 使用主 Agent 结果 ────────────────────────
        if main_content:
            response_content = main_content
            response_content_type = "text"
            response_card_data = None
        else:
            # ── Phase 3: 主 Agent 不可用 → 标准降级提示 ─────────────────────────
            error_code = "agent_unavailable"
            if error_ctx:
                error_code = error_ctx.get("code", "agent_unavailable")
            response_content = degraded_message(error_code)
            response_content_type = "text"
            response_card_data = None

        card_data_json = json.dumps(response_card_data) if response_card_data else None

        result = session.execute(
            text("""
                INSERT INTO message (conversation_id, role, content, content_type, sequence, parent_id, card_data)
                VALUES (:cid, 'assistant', :content, :ctype, :seq, :pid, :card_data)
            """),
            {
                "cid": conv_id,
                "content": response_content,
                "ctype": response_content_type,
                "seq": new_seq,
                "pid": user_msg_id,
                "card_data": card_data_json,
            },
        )
        session.commit()
        assistant_id = result.lastrowid

        session.execute(
            text("UPDATE conversation SET message_count = message_count + 1 WHERE id = :cid"),
            {"cid": conv_id},
        )
        session.commit()

        msg = session.execute(
            text("SELECT * FROM message WHERE id = :mid"),
            {"mid": assistant_id},
        ).fetchone()
        cols = ["id", "conversation_id", "role", "content", "content_type", "card_data", "token_count", "sequence", "parent_id", "tool_name", "tool_result", "created_at"]
        return _row_to_dict(msg, cols) if msg else {}
    except Exception as e:
        logger.error(f"Agent reply failed: {e}", exc_info=True)
        session.rollback()
        return _fallback_reply(conv_id, user_msg_id, user_content)
    finally:
        session.close()


def _fallback_reply(conv_id: int, user_msg_id: int, user_content: str) -> dict:
    session = _session()
    try:
        result = session.execute(
            text("SELECT MAX(sequence) FROM message WHERE conversation_id = :cid"),
            {"cid": conv_id},
        ).scalar()
        max_seq = result if result is not None else 0
        new_seq = max_seq + 1

        # 最终降级：使用标准错误提示
        reply_text = degraded_message("agent_unavailable")

        result = session.execute(
            text("""
                INSERT INTO message (conversation_id, role, content, content_type, sequence, parent_id)
                VALUES (:cid, 'assistant', :content, 'text', :seq, :pid)
            """),
            {"cid": conv_id, "content": reply_text, "seq": new_seq, "pid": user_msg_id},
        )
        session.commit()
        assistant_id = result.lastrowid

        session.execute(
            text("UPDATE conversation SET message_count = message_count + 1 WHERE id = :cid"),
            {"cid": conv_id},
        )
        session.commit()

        msg = session.execute(
            text("SELECT * FROM message WHERE id = :mid"),
            {"mid": assistant_id},
        ).fetchone()
        cols = ["id", "conversation_id", "role", "content", "content_type", "card_data", "token_count", "sequence", "parent_id", "tool_name", "tool_result", "created_at"]
        return _row_to_dict(msg, cols) if msg else {}
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ── 流式对话（SSE） ───────────────────────────────────────────────────────────


def _estimate_tokens(content: str) -> int:
    """估算单条消息的 token 数。

    与 deepagents SummarizationMiddleware 的默认 token_counter
    （langchain_core 的 count_tokens_approximately）保持同一口径，
    保证前端展示的会话 token 用量与后端自动压缩的触发阈值可对得上。
    """
    if not content:
        return 0
    try:
        return int(count_tokens_approximately([content]))
    except Exception:
        # 兜底：按字符估算（中英文混合场景约 2 字符/token）
        return max(1, len(content) // 2)


def _insert_message(
    conv_id: int,
    role: str,
    content: str,
    content_type: str = "text",
    parent_id: Optional[int] = None,
    card_data: Optional[dict] = None,
    token_count: Optional[int] = None,
) -> int:
    """插入一条消息，自动分配 sequence，更新 conversation.message_count。

    幂等性：同 (conversation_id, sequence) 已存在（重放/并发）时直接复用
    已有行 id，不重复插入也不重复计数；并发兜底由 UNIQUE 约束 + 
    ON DUPLICATE KEY UPDATE 保证。

    Args:
        token_count: 该条消息的 token 数（None 表示不写入，用于存量消息）。
            传入时同时累加到 conversation.token_count（会话上下文总用量）。
    """
    session = _session()
    try:
        max_seq = session.execute(
            text("SELECT MAX(sequence) FROM message WHERE conversation_id = :cid"),
            {"cid": conv_id},
        ).scalar()
        new_seq = (max_seq or 0) + 1

        # 幂等重放：该序号消息已存在则直接返回（避免重复计数）
        existing = session.execute(
            text("SELECT id FROM message WHERE conversation_id = :cid AND sequence = :seq"),
            {"cid": conv_id, "seq": new_seq},
        ).fetchone()
        if existing:
            return int(existing[0])

        card_data_json = json.dumps(card_data, ensure_ascii=False) if card_data else None

        result = session.execute(
            text("""
                INSERT INTO message (conversation_id, role, content, content_type, sequence, parent_id, card_data, token_count)
                VALUES (:cid, :role, :content, :ctype, :seq, :pid, :card_data, :tok)
                ON DUPLICATE KEY UPDATE id = id
            """),
            {
                "cid": conv_id,
                "role": role,
                "content": content,
                "ctype": content_type,
                "seq": new_seq,
                "pid": parent_id,
                "card_data": card_data_json,
                "tok": token_count if token_count is not None else 0,
            },
        )
        session.commit()
        msg_id = result.lastrowid

        session.execute(
            text("""
                UPDATE conversation
                SET message_count = message_count + 1,
                    token_count = token_count + :tok
                WHERE id = :cid
            """),
            {"cid": conv_id, "tok": token_count if token_count is not None else 0},
        )
        session.commit()
        return msg_id
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _sse_event(data: dict) -> str:
    """构造 SSE 事件字符串。"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _update_context_tokens(conv_id: int, context_tokens: int) -> None:
    """落库会话当前上下文占用（真实模型 input_tokens）。"""
    session = _session()
    try:
        session.execute(
            text("UPDATE conversation SET context_tokens = :tok WHERE id = :cid"),
            {"tok": int(context_tokens), "cid": conv_id},
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _persist_assistant_turn(
    conv_id: int,
    full_content: str,
    trace: list[dict],
    subagent_result: dict | None,
    card_symbol: str,
    card_stock_name: str,
    card_subagent: str,
    context_tokens: Optional[int],
    usage_total_tokens: Optional[int],
) -> bool:
    """落库助手消息（含复合卡片）、上下文占用与决策报告。

    **全同步实现**：正常结束与「客户端断连」两条路径共用。断连路径在
    asyncio.CancelledError 的 finally 中调用，此时任何 await 都会被立即取消，
    因此这里刻意不使用 await。

    Returns:
        是否实际落库了助手消息（无内容时返回 False，调用方据此决定后续动作）。
    """
    if not full_content:
        return False

    content_type = "text"
    card_data = None
    if subagent_result or trace:
        content_type = "composite_decision"
        # trace_id 由 TA 子 Agent 一次生成，随 subagent_result 回传，
        # 用于报告文件幂等命名与前端定位同一次决策
        card_data = _build_composite_card_data(
            subagent_result, trace, card_symbol, card_stock_name, card_subagent
        )

    _insert_message(
        conv_id,
        "assistant",
        full_content,
        content_type,
        card_data=card_data,
        # 优先用真实模型 total_tokens（含子 Agent 往返），降级用文本估算
        token_count=usage_total_tokens or _estimate_tokens(full_content),
    )

    # 落库真实上下文占用（最后一次模型调用的 input_tokens）
    if context_tokens is not None:
        try:
            _update_context_tokens(conv_id, context_tokens)
        except Exception as e:
            logger.warning("更新 context_tokens 失败: %s", e)

    # 报告落盘（失败仅告警）；用稳定 trace_id 命名保证重放收敛
    if content_type == "composite_decision" and card_data:
        try:
            from services.report_service import write_decision_report
            write_decision_report(full_content, card_data, card_data.get("trace_id"))
        except Exception:
            logger.warning("write_decision_report failed", exc_info=True)

    return True


def _finalize_cancelled_stream(thread_id: str | None, interrupted: bool) -> None:
    """客户端断连收尾：更新线程状态（全同步，可在 finally 中调用）。

    - 已产出 HITL 中断 → 维持 INTERRUPTED（用户仍需决策，可直接 resume）
    - 否则 → CANCELLED（本轮未跑完，不可 resume，避免污染 resume 目标）
    """
    if not thread_id:
        return
    from services import thread_service

    try:
        if interrupted:
            thread_service.mark_interrupted(thread_id)
        else:
            thread_service.mark_cancelled(thread_id)
        logger.info(
            "断连收尾：thread_id=%s status=%s",
            thread_id,
            "INTERRUPTED" if interrupted else "CANCELLED",
        )
    except Exception as e:
        logger.warning("断连收尾失败（thread_id=%s）: %s", thread_id, e)


def _build_composite_card_data(
    subagent_result: dict | None,
    trace: list[dict],
    card_symbol: str,
    card_stock_name: str,
    card_subagent: str,
) -> dict | None:
    """组装 composite_decision 的 card_data（决策卡片完整结构）。

    - 基础字段：symbol / stock_name / subagent / analysis_trace / result / trace_id
    - 卡片字段（TA merge_node 已把 va_summary/pa_result/fusion 附进
      structured_response，此处扁平化为前端 DecisionCard 期望的形态）：
      value_assessment（估值评分）/ pa_analysis（PA 技术面）/ fusion（融合决策）
    """
    if not (subagent_result or trace):
        return None
    card_trace_id = subagent_result.get("trace_id", "") if subagent_result else ""
    card_data: dict = {
        "symbol": card_symbol or None,
        "stock_name": card_stock_name or None,
        "subagent": card_subagent or None,
        "analysis_trace": trace,
        "result": subagent_result,
        "trace_id": card_trace_id or None,
    }
    if subagent_result:
        va_summary = subagent_result.get("va_summary") or {}
        card_data["value_assessment"] = {
            "final_score": va_summary.get("final_score") if va_summary.get("final_score") is not None else va_summary.get("score"),
            "final_level": va_summary.get("final_level"),
            "blocked": bool(va_summary.get("blocked")),
            "warnings": va_summary.get("warnings", []),
            "summary": va_summary.get("summary", ""),
        }
        card_data["pa_analysis"] = {
            "card_data": {
                "direction": subagent_result.get("direction"),
                "trade_confidence": round((subagent_result.get("confidence") or 0) * 100) if subagent_result.get("confidence") is not None else None,
            }
        }
        card_data["fusion"] = subagent_result.get("fusion") or {}
    return card_data


async def stream_agent_reply(
    conv_id: int,
    user_content: str,
    thread_id: str | None = None,
    chunk_size: int = 8,
    interval_s: float = 0.015,
) -> AsyncGenerator[str, None]:
    """流式对话回复：存用户消息 → 流式主 Agent 回复 → 存助手消息。

    Args:
        conv_id: 会话 ID。
        user_content: 用户输入。
        thread_id: langgraph 线程 ID（HITL resume 用）；为 None 时调用
            thread_service.create_thread 为该会话创建新线程。
        chunk_size: 每个 SSE chunk 聚合的 token 数（默认 8）。
        interval_s: chunk 间最小间隔秒（默认 15ms）。

    Yields:
        SSE 事件字符串（均为 JSON）：
        - {"type": "chunk", "chunk": 主 Agent 回复文本片段}
        - {"type": "subagent_started", "subagent": ..., "task_id": ...}
        - {"type": "subagent_completed", "subagent": ..., "task_id": ...}
        - {"type": "subagent_result", "subagent": ..., "task_id": ...,
           "result": 子 Agent 结构化结果（可选）}
        - {"type": "stage", "subagent": ..., "stage": "technical",
           "status": "started"|"done", "direction"?: 方向,
           "stock_code"?: 代码, "stock_name"?: 名称}
          （仅 technical_analysis 子 Agent 内部阶段事件；估值阶段进度由
           subagent_started / subagent_completed(value_assessment) 承担，
           不产出 stage 事件）
        - {"type": "interrupt", "data": HITLRequest, "thread_id": 线程 ID}
          （HITL 中断：估值完成征求用户决策，前端据此展示决策 UI 并调
           /resume 续流）
        - {"done": true}（结束）

    流结束时按中断状态落库线程状态：interrupt → INTERRUPTED，否则 DONE。
    结束前会把 analysis_trace 与结构化结果合并进 assistant 消息的
    card_data（content_type="composite_decision"），供历史回放渲染。

    客户端断连（abort / 网络中断 / 关页面）时 generator 被取消，此时在
    finally 中全同步落库已产出内容，并将线程标记为 CANCELLED：它与 HITL 的
    INTERRUPTED 严格区分，不可作为 resume 目标，从而保证前端刷新后不丢整轮结果。
    """
    # 1. 存用户消息 + 自动更新标题
    _insert_message(conv_id, "user", user_content, token_count=_estimate_tokens(user_content))
    _auto_update_title(conv_id, user_content)

    # 2. 获取会话绑定的 Agent 线程（方案 C：会话与线程一对一，
    #    跨轮对话在同一线程上延续，HITL resume 依赖该 thread_id）
    from services import thread_service
    if not thread_id:
        try:
            thread_id = thread_service.get_or_create_thread(conv_id)
        except Exception as e:
            # 线程表写入失败（如 DB 不可用）时降级：agent 层会自生成
            # 临时 thread_id，但该线程无法被持久化/resume
            logger.warning("get_or_create_thread 失败，本线程无法 resume: %s", e)
            thread_id = None

    # 3. 流式主 Agent 回复（结构化事件流）
    from agents.main_agent import astream_agent_events

    buffer: list[str] = []
    full_parts: list[str] = []
    trace: list[dict] = []
    subagent_result: dict | None = None
    card_symbol = ""
    card_stock_name = ""
    card_subagent = ""
    interrupted = False
    # 真实上下文用量：来自 agent 层 usage 事件（最后一次模型调用），
    # 用于落库 conversation.context_tokens 与 assistant 消息 token_count。
    context_tokens: Optional[int] = None
    usage_total_tokens: Optional[int] = None
    # 客户端断连标记：finally 中据此决定是否执行断连落库收尾
    cancelled = False

    try:
        async for event in astream_agent_events(user_content, thread_id=thread_id):
            if event.get("type") == "token":
                full_parts.append(event["content"])
                buffer.append(event["content"])
                if len(buffer) >= chunk_size:
                    yield _sse_event({"type": "chunk", "chunk": "".join(buffer)})
                    buffer.clear()
                    await asyncio.sleep(interval_s)
            elif event.get("type") == "usage":
                # 真实模型用量：最后一次调用的上下文量
                context_tokens = event.get("input_tokens") or context_tokens
                usage_total_tokens = event.get("total_tokens") or usage_total_tokens
                # 透传前端（实时刷新上下文占用）
                yield _sse_event(event)
            elif event.get("type") == "done":
                # agent 层结束事件：记录是否因 HITL 中断结束（不透传，
                # 统一由本函数结尾发 {"done": true}，保持前端兼容）
                interrupted = bool(event.get("interrupted", False))
            else:
                # 收集持久化所需数据（analysis_trace / 结构化结果）
                if event.get("type") == "stage":
                    if event.get("status") == "done":
                        entry: dict = {"stage": event.get("stage"), "status": "done"}
                        if event.get("score") is not None:
                            entry["score"] = event["score"]
                        if event.get("direction") is not None:
                            entry["direction"] = event["direction"]
                        trace.append(entry)
                    if event.get("stock_code"):
                        card_symbol = card_symbol or event["stock_code"]
                    if event.get("stock_name"):
                        card_stock_name = card_stock_name or event["stock_name"]
                    if event.get("subagent"):
                        card_subagent = card_subagent or event["subagent"]
                elif event.get("type") == "subagent_result":
                    subagent_result = event.get("result")
                    if event.get("subagent"):
                        card_subagent = event["subagent"]
                    if subagent_result:
                        card_symbol = card_symbol or subagent_result.get("stock_code", "")
                        card_stock_name = card_stock_name or subagent_result.get("stock_name", "")

                # 非 token 事件：先冲刷待发 token，再透传
                if buffer:
                    yield _sse_event({"type": "chunk", "chunk": "".join(buffer)})
                    buffer.clear()
                    await asyncio.sleep(interval_s)
                # HITL 中断事件必须带 thread_id，供前端 resume 使用
                if event.get("type") == "interrupt" and thread_id:
                    event = {**event, "thread_id": thread_id}
                yield _sse_event(event)
        if buffer:
            yield _sse_event({"type": "chunk", "chunk": "".join(buffer)})
            buffer.clear()
            await asyncio.sleep(interval_s)
    except (asyncio.CancelledError, GeneratorExit):
        # 客户端断连（abort / 网络中断 / 关闭页面）或服务端取消：向上传播，
        # 但先经 finally 把已产出内容落库，避免刷新后整轮结果蒸发。
        # - CancelledError：ASGI 取消响应任务时抛出
        # - GeneratorExit：服务器关闭/回收生成器时抛出
        # 两者都继承 BaseException，下面的 except Exception 抓不到。
        cancelled = True
        raise
    except Exception as e:
        logger.error("Stream reply failed: %s", e, exc_info=True)
        yield _sse_event({"type": "chunk", "chunk": degraded_message("agent_error", detail=str(e))})
    finally:
        if cancelled:
            # 断连分支内任何 await 都会被立即取消，因此此处只用全同步实现。
            try:
                if _persist_assistant_turn(
                    conv_id,
                    "".join(full_parts),
                    trace,
                    subagent_result,
                    card_symbol,
                    card_stock_name,
                    card_subagent,
                    context_tokens,
                    usage_total_tokens,
                ):
                    logger.info("断连落库完成：conversation_id=%s", conv_id)
            except Exception as e:
                logger.warning("断连落库失败（conversation_id=%s）: %s", conv_id, e)
            _finalize_cancelled_stream(thread_id, interrupted)

    # 3. 存助手消息（若主 Agent 有输出）；有 trace/结果时落复合卡片数据
    if _persist_assistant_turn(
        conv_id,
        "".join(full_parts),
        trace,
        subagent_result,
        card_symbol,
        card_stock_name,
        card_subagent,
        context_tokens,
        usage_total_tokens,
    ):
        # 4.6 经验写回路异步触发（复盘→提升，失败不影响响应）
        try:
            from services.experience_loop_service import run_experience_loop
            asyncio.create_task(asyncio.to_thread(run_experience_loop))
        except Exception:
            logger.warning("experience loop trigger failed", exc_info=True)

    # 4. 线程状态落库：中断 → INTERRUPTED（可 resume），否则 → DONE
    if thread_id:
        try:
            if interrupted:
                thread_service.mark_interrupted(thread_id)
            else:
                thread_service.mark_done(thread_id)
        except Exception as e:
            logger.warning("更新线程状态失败（thread_id=%s）: %s", thread_id, e)

    # 5. 结束事件
    yield _sse_event({"done": True})


async def resume_agent_reply(
    conversation_id: int,
    decisions: list[dict],
    chunk_size: int = 8,
    interval_s: float = 0.015,
) -> AsyncGenerator[str, None]:
    """恢复 HITL 中断的分析流：提交用户决策后 SSE 续流。

    从 agent_threads 表取该会话最近一条 INTERRUPTED 线程，用
    ``Command(resume={"decisions": decisions})`` 续流同一线程。

    Args:
        conversation_id: 会话 ID。
        decisions: 用户决策列表，如 [{"type": "approve"}] /
            [{"type": "reject"}] / [{"type": "respond", "content": ...}]。
        chunk_size: 每个 SSE chunk 聚合的 token 数（默认 8）。
        interval_s: chunk 间最小间隔秒（默认 15ms）。

    Yields:
        与 stream_agent_reply 相同格式的 SSE 事件字符串。
        无中断线程时产出 {"type": "error", "message": ...} 后结束。
    """
    from services import thread_service

    # 1. 定位可续流线程（优先会话绑定线程，其次最近 INTERRUPTED）；
    #    无则产出错误事件并结束
    thread_id = thread_service.get_resumable_thread(conversation_id)
    if not thread_id:
        yield _sse_event({
            "type": "error",
            "message": "没有可恢复的中断分析，请重新发起分析",
        })
        return

    # 2. resume 续流（事件格式与 stream_agent_reply 一致）
    from agents.main_agent import astream_agent_events

    buffer: list[str] = []
    full_parts: list[str] = []
    trace: list[dict] = []
    subagent_result: dict | None = None
    card_symbol = ""
    card_stock_name = ""
    card_subagent = ""
    interrupted = False
    # 真实上下文用量（同 stream 路径）
    context_tokens: Optional[int] = None
    usage_total_tokens: Optional[int] = None
    # 客户端断连标记：finally 中据此决定是否执行断连落库收尾
    cancelled = False

    try:
        async for event in astream_agent_events(
            "", thread_id=thread_id, resume_decisions=decisions
        ):
            if event.get("type") == "token":
                full_parts.append(event["content"])
                buffer.append(event["content"])
                if len(buffer) >= chunk_size:
                    yield _sse_event({"type": "chunk", "chunk": "".join(buffer)})
                    buffer.clear()
                    await asyncio.sleep(interval_s)
            elif event.get("type") == "usage":
                context_tokens = event.get("input_tokens") or context_tokens
                usage_total_tokens = event.get("total_tokens") or usage_total_tokens
                yield _sse_event(event)
            elif event.get("type") == "done":
                # agent 层结束事件：不透传，结尾统一发 {"done": true}
                interrupted = bool(event.get("interrupted", False))
            else:
                # 收集持久化所需数据（技术面 stage / 结构化结果）
                if event.get("type") == "stage":
                    if event.get("status") == "done":
                        entry: dict = {"stage": event.get("stage"), "status": "done"}
                        if event.get("score") is not None:
                            entry["score"] = event["score"]
                        if event.get("direction") is not None:
                            entry["direction"] = event["direction"]
                        trace.append(entry)
                    if event.get("stock_code"):
                        card_symbol = card_symbol or event["stock_code"]
                    if event.get("stock_name"):
                        card_stock_name = card_stock_name or event["stock_name"]
                    if event.get("subagent"):
                        card_subagent = card_subagent or event["subagent"]
                elif event.get("type") == "subagent_result":
                    subagent_result = event.get("result")
                    if event.get("subagent"):
                        card_subagent = event["subagent"]
                    if subagent_result:
                        card_symbol = card_symbol or subagent_result.get("stock_code", "")
                        card_stock_name = card_stock_name or subagent_result.get("stock_name", "")

                # 非 token 事件：先冲刷待发 token，再透传
                if buffer:
                    yield _sse_event({"type": "chunk", "chunk": "".join(buffer)})
                    buffer.clear()
                    await asyncio.sleep(interval_s)
                # HITL 中断事件必须带 thread_id，供前端 resume 使用
                if event.get("type") == "interrupt" and thread_id:
                    event = {**event, "thread_id": thread_id}
                yield _sse_event(event)
        if buffer:
            yield _sse_event({"type": "chunk", "chunk": "".join(buffer)})
            buffer.clear()
            await asyncio.sleep(interval_s)
    except (asyncio.CancelledError, GeneratorExit):
        # 客户端断连：向上传播，先经 finally 落库续流已产出内容
        cancelled = True
        raise
    except Exception as e:
        logger.error("Resume stream failed: %s", e, exc_info=True)
        yield _sse_event({"type": "chunk", "chunk": degraded_message("agent_error", detail=str(e))})
    finally:
        if cancelled:
            # 再次中断 → 本轮仍等待用户决策，维持 INTERRUPTED 且不落库；
            # 否则落库已产出内容并标记 CANCELLED。
            if not interrupted:
                try:
                    if _persist_assistant_turn(
                        conversation_id,
                        "".join(full_parts),
                        trace,
                        subagent_result,
                        card_symbol,
                        card_stock_name,
                        card_subagent,
                        context_tokens,
                        usage_total_tokens,
                    ):
                        logger.info("断连落库完成（resume）：conversation_id=%s", conversation_id)
                except Exception as e:
                    logger.warning(
                        "断连落库失败（resume，conversation_id=%s）: %s", conversation_id, e
                    )
            _finalize_cancelled_stream(thread_id, interrupted)

    # 2.5 存助手消息（续流产出；若再次中断则不落库，等待新一轮决策）
    if not interrupted and _persist_assistant_turn(
        conversation_id,
        "".join(full_parts),
        trace,
        subagent_result,
        card_symbol,
        card_stock_name,
        card_subagent,
        context_tokens,
        usage_total_tokens,
    ):
        # 经验写回路异步触发（复盘→提升，失败不影响响应）
        try:
            from services.experience_loop_service import run_experience_loop
            asyncio.create_task(asyncio.to_thread(run_experience_loop))
        except Exception:
            logger.warning("experience loop trigger failed", exc_info=True)

    # 3. 线程状态落库：resume 后再次中断 → 保持 INTERRUPTED；否则 → DONE
    try:
        if interrupted:
            thread_service.mark_interrupted(thread_id)
        else:
            thread_service.mark_done(thread_id)
    except Exception as e:
        logger.warning("更新线程状态失败（thread_id=%s）: %s", thread_id, e)

    # 4. 结束事件
    yield _sse_event({"done": True})
