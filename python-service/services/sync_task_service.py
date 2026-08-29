"""Sync task service — 批量回填任务状态管理（断点续传）。"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.config import settings
from sqlalchemy import create_engine

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


def upsert_task(symbol: str, start_year: int, end_year: int) -> int:
    """创建或获取任务记录，返回 task id。

    - 若 (symbol, start_year, end_year) 已存在且 status 为 PENDING/FAILED/PARTIAL，
      返回原任务 id（断点续传）。
    - 若已存在且 status 为 SUCCESS，不重复处理，返回原 id。
    - 否则插入新记录。
    """
    session = _session()
    try:
        row = session.execute(
            text("""
                SELECT id, status, current_year FROM sync_task
                WHERE symbol = :sym AND start_year = :sy AND end_year = :ey
            """),
            {"sym": symbol, "sy": start_year, "ey": end_year},
        ).fetchone()

        if row:
            return row.id

        result = session.execute(
            text("""
                INSERT INTO sync_task (symbol, start_year, end_year, current_year, status)
                VALUES (:sym, :sy, :ey, 0, 'PENDING')
            """),
            {"sym": symbol, "sy": start_year, "ey": end_year},
        )
        session.commit()
        return result.lastrowid
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def mark_running(task_id: int) -> None:
    session = _session()
    try:
        session.execute(
            text("UPDATE sync_task SET status = 'RUNNING', updated_at = NOW() WHERE id = :id"),
            {"id": task_id},
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def mark_success(task_id: int, records_fetched: int) -> None:
    session = _session()
    try:
        session.execute(
            text("""
                UPDATE sync_task
                SET status = 'SUCCESS', records_fetched = :n, error_msg = NULL, updated_at = NOW()
                WHERE id = :id
            """),
            {"n": records_fetched, "id": task_id},
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def mark_failed(task_id: int, error_msg: str, records_fetched: int = 0) -> None:
    session = _session()
    try:
        session.execute(
            text("""
                UPDATE sync_task
                SET status = 'FAILED', error_msg = :msg, records_fetched = :n,
                    retry_count = retry_count + 1, updated_at = NOW()
                WHERE id = :id
            """),
            {"msg": error_msg[:500], "n": records_fetched, "id": task_id},
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def mark_partial(task_id: int, current_year: int, records_fetched: int, error_msg: str) -> None:
    """记录部分完成（某一年失败，但之前年份已成功）。"""
    session = _session()
    try:
        session.execute(
            text("""
                UPDATE sync_task
                SET status = 'PARTIAL', current_year = :cy, records_fetched = :n,
                    error_msg = :msg, updated_at = NOW()
                WHERE id = :id
            """),
            {"cy": current_year, "n": records_fetched, "msg": error_msg[:500], "id": task_id},
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def update_progress(task_id: int, current_year: int, records_fetched: int) -> None:
    """更新当前进度（每完成一年调用）。"""
    session = _session()
    try:
        session.execute(
            text("""
                UPDATE sync_task
                SET current_year = :cy, records_fetched = :n, updated_at = NOW()
                WHERE id = :id
            """),
            {"cy": current_year, "n": records_fetched, "id": task_id},
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_task(task_id: int) -> Optional[dict[str, Any]]:
    session = _session()
    try:
        row = session.execute(
            text("""
                SELECT id, symbol, start_year, end_year, current_year, status,
                       records_fetched, retry_count, error_msg, updated_at
                FROM sync_task WHERE id = :id
            """),
            {"id": task_id},
        ).fetchone()
        if not row:
            return None
        return {
            "id": row.id,
            "symbol": row.symbol,
            "start_year": row.start_year,
            "end_year": row.end_year,
            "current_year": row.current_year,
            "status": row.status,
            "records_fetched": row.records_fetched,
            "retry_count": row.retry_count,
            "error_msg": row.error_msg,
            "updated_at": row.updated_at.strftime("%Y-%m-%d %H:%M:%S") if row.updated_at else None,
        }
    finally:
        session.close()


def get_task_status_by_symbols(symbols: list[str], start_year: int, end_year: int) -> list[dict[str, Any]]:
    """查询给定股票列表的任务状态。"""
    if not symbols:
        return []
    session = _session()
    try:
        placeholders = ",".join(f":s{i}" for i in range(len(symbols)))
        params = {f"s{i}": s for i, s in enumerate(symbols)}
        params["sy"] = start_year
        params["ey"] = end_year
        rows = session.execute(
            text(f"""
                SELECT id, symbol, start_year, end_year, current_year, status,
                       records_fetched, retry_count, error_msg, updated_at
                FROM sync_task
                WHERE symbol IN ({placeholders}) AND start_year = :sy AND end_year = :ey
                ORDER BY symbol
            """),
            params,
        ).fetchall()
        return [
            {
                "id": r.id,
                "symbol": r.symbol,
                "start_year": r.start_year,
                "end_year": r.end_year,
                "current_year": r.current_year,
                "status": r.status,
                "records_fetched": r.records_fetched,
                "retry_count": r.retry_count,
                "error_msg": r.error_msg,
                "updated_at": r.updated_at.strftime("%Y-%m-%d %H:%M:%S") if r.updated_at else None,
            }
            for r in rows
        ]
    finally:
        session.close()
