"""Market data service — 行情数据 CRUD + 查询。"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import text

from services import kline_cache_service as kcs
from shared.config import settings
from shared.data_filter import filter_kline_bars
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


def get_latest_market_date(symbol: str) -> Optional[datetime.date]:
    # 必带 timeframe：索引 (symbol, timeframe, trade_date) 下，仅按 symbol 过滤会
    # 失去 MIN/MAX 优化（需扫该标的所有周期行），补等值条件后恢复 O(1)
    session = _session()
    try:
        row = session.execute(
            text("SELECT MAX(trade_date) FROM market_data WHERE symbol = :sym AND timeframe = '1d'"),
            {"sym": symbol},
        ).fetchone()
        if row and row[0]:
            return row[0]
        return None
    finally:
        session.close()


def upsert_market_data(rows: list[dict[str, Any]]) -> None:
    session = _session()
    try:
        for row in rows:
            session.execute(
                text("""
                    INSERT INTO market_data
                        (symbol, trade_date, timeframe, ts_open, open, high, low, close,
                         volume, amount, pct_chg, closed)
                    VALUES
                        (:symbol, :trade_date, :timeframe, :ts_open, :open, :high, :low, :close,
                         :volume, :amount, :pct_chg, :closed)
                    ON DUPLICATE KEY UPDATE
                        open = VALUES(open), high = VALUES(high), low = VALUES(low),
                        close = VALUES(close), volume = VALUES(volume), amount = VALUES(amount),
                        pct_chg = VALUES(pct_chg), closed = VALUES(closed),
                        fetched_at = NOW()
                """),
                row,
            )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    # 缓存失效信号：必须在 commit 之后发出，否则 Java 可能抢先回源读到旧值并
    # 写回缓存（read-modify-write 竞态）。这里调用会吞掉自身异常，不影响写入。
    kcs.bump_kline_versions(row.get("symbol") for row in rows)


def bars_to_rows(symbol: str, bars: list) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bar in reversed(bars):
        ts_sec = int(bar.ts_open) / 1000
        trade_date = datetime.utcfromtimestamp(ts_sec).date()
        rows.append({
            "symbol": symbol,
            "trade_date": trade_date,
            "timeframe": "1d",
            "ts_open": int(bar.ts_open),
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": int(bar.volume),
            "amount": float(bar.amount),
            "pct_chg": float(bar.pct_chg) if bar.pct_chg is not None else None,
            "closed": bar.closed,
        })
    valid, rejected = filter_kline_bars(rows)
    if rejected:
        logger.warning("Filtered %d/%d rows for %s", len(rejected), len(rows), symbol)
    return valid


def estimate_days_since(latest_date: datetime.date) -> int:
    today = datetime.now().date()
    delta = today - latest_date
    return max(1, delta.days)


def bar_trade_date(bar) -> datetime.date:
    ts_sec = int(bar.ts_open) / 1000
    return datetime.utcfromtimestamp(ts_sec).date()


def get_realtime_quote(symbols: list[str]) -> list[dict[str, Any]]:
    session = _session()
    try:
        quotes: list[dict[str, Any]] = []
        for sym in symbols:
            row = session.execute(
                text("""
                    SELECT m1.close, m1.pct_chg, m1.trade_date,
                           m2.close AS pre_close
                    FROM market_data m1
                    LEFT JOIN market_data m2
                        ON m2.symbol = m1.symbol
                        AND m2.timeframe = '1d'
                        AND m2.trade_date = (
                            SELECT MAX(trade_date) FROM market_data
                            WHERE symbol = m1.symbol AND timeframe = '1d' AND trade_date < m1.trade_date
                        )
                    WHERE m1.symbol = :sym AND m1.timeframe = '1d'
                    ORDER BY m1.trade_date DESC
                    LIMIT 1
                """),
                {"sym": sym},
            ).fetchone()
            if row:
                trade_date_str = ""
                if row.trade_date:
                    if hasattr(row.trade_date, 'strftime'):
                        trade_date_str = row.trade_date.strftime("%Y-%m-%d")
                    else:
                        trade_date_str = str(row.trade_date)
                quotes.append({
                    "symbol": sym,
                    "close": float(row.close) if row.close is not None else None,
                    "change_pct": float(row.pct_chg) if row.pct_chg is not None else None,
                    "pre_close": float(row.pre_close) if row.pre_close is not None else None,
                    "trade_date": trade_date_str,
                })
            else:
                quotes.append({"symbol": sym, "close": None, "change_pct": None, "pre_close": None, "trade_date": None})
        return quotes
    finally:
        session.close()


def get_kline_history(
    symbol: str,
    timeframe: str = "1d",
    start_date: Optional[str] = None,  # YYYY-MM-DD
    end_date: Optional[str] = None,
    limit: int = 120,
) -> list[dict[str, Any]]:
    """查询历史 K 线数据。

    - 支持按日期范围或全量查询，按 trade_date DESC 取 limit 条后正序返回。
    - start_date/end_date 接受 YYYY-MM-DD 字符串，内部转为 date 对象传入 SQL。
    """
    sql = (
        "SELECT symbol, trade_date, timeframe, ts_open, open, high, low, close, "
        "volume, amount, pct_chg, closed "
        "FROM market_data "
        "WHERE symbol = :sym AND timeframe = :tf"
    )
    params: dict[str, Any] = {"sym": symbol, "tf": timeframe, "limit": limit}
    if start_date:
        sd = datetime.strptime(start_date, "%Y-%m-%d").date()
        sql += " AND trade_date >= :start_date"
        params["start_date"] = sd
    if end_date:
        ed = datetime.strptime(end_date, "%Y-%m-%d").date()
        sql += " AND trade_date <= :end_date"
        params["end_date"] = ed
    sql += " ORDER BY trade_date DESC LIMIT :limit"

    session = _session()
    try:
        rows = session.execute(text(sql), params).fetchall()
    finally:
        session.close()

    bars: list[dict[str, Any]] = []
    for r in reversed(rows):
        td = r.trade_date
        if hasattr(td, "strftime"):
            td_str = td.strftime("%Y-%m-%d")
        else:
            td_str = str(td)
        bars.append({
            "symbol": r.symbol,
            "trade_date": td_str,
            "timeframe": r.timeframe,
            "ts_open": int(r.ts_open) if r.ts_open is not None else 0,
            "open": float(r.open) if r.open is not None else 0.0,
            "high": float(r.high) if r.high is not None else 0.0,
            "low": float(r.low) if r.low is not None else 0.0,
            "close": float(r.close) if r.close is not None else 0.0,
            "volume": int(r.volume) if r.volume is not None else 0,
            "amount": float(r.amount) if r.amount is not None else 0.0,
            "pct_chg": float(r.pct_chg) if r.pct_chg is not None else None,
            "closed": int(r.closed) if r.closed is not None else 1,
        })
    return bars
