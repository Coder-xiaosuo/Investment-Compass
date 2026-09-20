"""Thread service — Agent 线程管理（HITL 线程状态）。

负责 agent_threads 表读写：会话与 langgraph thread_id 的映射、
中断（INTERRUPTED）与完成（DONE）状态流转，供 HITL 中断/恢复定位线程。
"""
from __future__ import annotations

import logging
from typing import Optional

from langchain_core.utils.uuid import uuid7
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.config import settings

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


def create_thread(conversation_id: int) -> str:
    """为会话创建一条 Agent 线程记录，返回 langgraph thread_id（uuid7）。

    创建后将该 thread_id 绑定到 conversation.thread_id（方案 C：会话与
    线程一对一），保证跨轮对话在同一线程上延续（会话记忆）。
    """
    thread_id = str(uuid7())
    session = _session()
    try:
        session.execute(
            text("""
                INSERT INTO agent_threads (conversation_id, thread_id, status)
                VALUES (:cid, :tid, 'ACTIVE')
            """),
            {"cid": conversation_id, "tid": thread_id},
        )
        _bind_thread(session, conversation_id, thread_id)
        session.commit()
        logger.info("create_thread: conversation_id=%s thread_id=%s", conversation_id, thread_id)
        return thread_id
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_or_create_thread(conversation_id: int) -> str:
    """获取会话绑定的 langgraph 线程（无则创建），保证跨轮对话连续。

    优先级：
    1. conversation.thread_id 已绑定 → 直接返回（跨轮复用，会话记忆生效）；
    2. agent_threads 已有该会话的历史线程 → 绑定最新一条并返回（兼容旧数据，
       避免已产生的历史消息上下文丢失）；
    3. 都没有 → 新建线程并绑定。

    Returns:
        langgraph thread_id（字符串）。
    """
    session = _session()
    try:
        # 1. 会话已绑定线程
        bound = session.execute(
            text("SELECT thread_id FROM conversation WHERE id = :cid"),
            {"cid": conversation_id},
        ).fetchone()
        if bound and bound.thread_id:
            return bound.thread_id

        # 2. 兼容旧数据：复用该会话已有的最新线程（避免历史上下文断裂）
        old = session.execute(
            text("""
                SELECT thread_id FROM agent_threads
                WHERE conversation_id = :cid
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
            """),
            {"cid": conversation_id},
        ).fetchone()
        if old:
            _bind_thread(session, conversation_id, old.thread_id)
            session.commit()
            logger.info(
                "get_or_create_thread: 复用既有线程 conversation_id=%s thread_id=%s",
                conversation_id, old.thread_id,
            )
            return old.thread_id
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    # 3. 无任何历史线程 → 新建并绑定
    return create_thread(conversation_id)


def _bind_thread(session: Session, conversation_id: int, thread_id: str) -> None:
    """将 thread_id 绑定到 conversation 表（幂等）。"""
    session.execute(
        text("UPDATE conversation SET thread_id = :tid WHERE id = :cid AND thread_id IS NULL"),
        {"tid": thread_id, "cid": conversation_id},
    )


def mark_interrupted(thread_id: str) -> bool:
    """将线程标记为 INTERRUPTED（估值完成，等待用户决策）。"""
    return _update_status(thread_id, "INTERRUPTED")


def mark_done(thread_id: str) -> bool:
    """将线程标记为 DONE（整个分析流程结束）。"""
    return _update_status(thread_id, "DONE")


def mark_cancelled(thread_id: str) -> bool:
    """将线程标记为 CANCELLED（客户端断连，本轮未跑完）。

    与 INTERRUPTED 严格区分：CANCELLED 是「非 HITL 的中途终止」，
    不能作为 resume 目标，因此 get_resumable_thread / get_latest_interrupted
    只认 INTERRUPTED，不会误取到断连线程。
    """
    return _update_status(thread_id, "CANCELLED")


def _update_status(thread_id: str, status: str) -> bool:
    session = _session()
    try:
        result = session.execute(
            text("UPDATE agent_threads SET status = :status WHERE thread_id = :tid"),
            {"status": status, "tid": thread_id},
        )
        session.commit()
        return result.rowcount > 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_latest_interrupted(conversation_id: int) -> Optional[str]:
    """查询该会话最近一条 INTERRUPTED 线程的 thread_id；无则返回 None。"""
    session = _session()
    try:
        row = session.execute(
            text("""
                SELECT thread_id FROM agent_threads
                WHERE conversation_id = :cid AND status = 'INTERRUPTED'
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
            """),
            {"cid": conversation_id},
        ).fetchone()
        return row.thread_id if row else None
    finally:
        session.close()


def get_resumable_thread(conversation_id: int) -> Optional[str]:
    """返回该会话可 resume 的线程（优先会话绑定线程，其次最近 INTERRUPTED）。

    方案 C 下会话与线程一对一绑定；resume 时应优先使用绑定线程，
    仅在其状态为 INTERRUPTED 时有效，否则回退到最近一条 INTERRUPTED 线程。
    """
    session = _session()
    try:
        # 1. 会话绑定线程：状态为 INTERRUPTED 才可续流
        bound = session.execute(
            text("SELECT thread_id FROM conversation WHERE id = :cid"),
            {"cid": conversation_id},
        ).fetchone()
        if bound and bound.thread_id:
            st = session.execute(
                text("SELECT status FROM agent_threads WHERE thread_id = :tid"),
                {"tid": bound.thread_id},
            ).fetchone()
            if st and st.status == "INTERRUPTED":
                return bound.thread_id
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    # 2. 回退：最近一条 INTERRUPTED 线程（兼容旧多线程数据）
    return get_latest_interrupted(conversation_id)
