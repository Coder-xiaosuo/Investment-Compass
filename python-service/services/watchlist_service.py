"""Watchlist service — 自选股管理。"""
from __future__ import annotations

import logging
from typing import Any, List

from sqlalchemy import text

from shared.config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

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


def _row_to_dict(row) -> dict[str, Any]:
    return {
        "symbol": getattr(row, "symbol", ""),
        "name": getattr(row, "symbol", ""),
        "price": 0.0,
        "change": 0.0,
    }


def add_to_watchlist(symbol: str) -> bool:
    session = _session()
    try:
        existing = session.execute(
            text("SELECT id FROM watchlist WHERE symbol = :sym"),
            {"sym": symbol},
        ).fetchone()
        if existing:
            return False

        session.execute(
            text("INSERT INTO watchlist (symbol) VALUES (:sym)"),
            {"sym": symbol},
        )
        session.commit()
        return True
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def remove_from_watchlist(symbol: str) -> bool:
    session = _session()
    try:
        result = session.execute(
            text("DELETE FROM watchlist WHERE symbol = :sym"),
            {"sym": symbol},
        )
        session.commit()
        return result.rowcount > 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_watchlist() -> List[dict[str, Any]]:
    session = _session()
    try:
        rows = session.execute(
            text("SELECT symbol FROM watchlist ORDER BY created_at DESC"),
        ).fetchall()
        return [_row_to_dict(row) for row in rows]
    finally:
        session.close()