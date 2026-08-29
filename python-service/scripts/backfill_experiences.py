#!/usr/bin/env python3
"""历史回测数据批量填充 — 扫描 K 线数据识别典型形态并生成经验条目。

Usage::

    # 默认模式：扫描最近 60 个交易日，识别典型形态
    python scripts/backfill_experiences.py

    # 指定扫描范围和输出限制
    python scripts/backfill_experiences.py --days 120 --limit 200

    # 仅处理指定股票
    python scripts/backfill_experiences.py --symbols 600519,000858
"""

from __future__ import annotations

import argparse
import logging
import sys
import os
from datetime import datetime, timedelta, timezone
from typing import Any

# Ensure package root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from shared.config import settings
from models.experience_entry import ExperienceEntry
from services.experience_library import get_experience_library, reset_backend_for_testing

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

engine = create_engine(settings.DATABASE_URL)


# ──────────────────────────────────────────────────────────────────────────────
# Pattern detection helpers
# ──────────────────────────────────────────────────────────────────────────────


def _get_recent_bars(
    session: Session, symbol: str, days: int = 60
) -> list[dict[str, Any]]:
    """Fetch recent daily K-line bars for *symbol*."""
    rows = session.execute(
        text("""
            SELECT trade_date, open, high, low, close, volume, amount, pct_chg
            FROM market_data
            WHERE symbol = :sym AND timeframe = '1d' AND closed = TRUE
            ORDER BY trade_date DESC
            LIMIT :lim
        """),
        {"sym": symbol, "lim": days},
    ).fetchall()
    return [row._asdict() for row in rows]


def _detect_macd_golden_cross(bars: list[dict]) -> bool:
    """Detect MACD golden cross (EMA12 crosses above EMA26) on latest bar."""
    if len(bars) < 27:
        return False
    closes = [float(b["close"]) for b in reversed(bars)]
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    if len(ema12) < 2 or len(ema26) < 2:
        return False
    # Latest two MACD values
    macd_prev = ema12[-2] - ema26[-2]
    macd_curr = ema12[-1] - ema26[-1]
    return macd_prev <= 0 and macd_curr > 0


def _detect_macd_death_cross(bars: list[dict]) -> bool:
    """Detect MACD death cross (EMA12 crosses below EMA26) on latest bar."""
    if len(bars) < 27:
        return False
    closes = [float(b["close"]) for b in reversed(bars)]
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    if len(ema12) < 2 or len(ema26) < 2:
        return False
    macd_prev = ema12[-2] - ema26[-2]
    macd_curr = ema12[-1] - ema26[-1]
    return macd_prev >= 0 and macd_curr < 0


def _detect_volume_breakout(bars: list[dict]) -> bool:
    """Detect volume > 2x avg of previous 20 days, with positive price change."""
    if len(bars) < 21:
        return False
    volumes = [float(b["volume"]) for b in bars[:21]]
    latest_vol = volumes[0]
    avg_vol = sum(volumes[1:]) / len(volumes[1:]) if volumes[1:] else 1
    latest_pct = float(bars[0].get("pct_chg", 0))
    return latest_vol > 2 * avg_vol and latest_pct > 2.0


def _detect_limit_up(bars: list[dict]) -> bool:
    """Detect 10% (or 20% for ChiNext/STAR) limit-up on latest bar."""
    if not bars:
        return False
    latest = bars[0]
    pct = float(latest.get("pct_chg", 0))
    return pct >= 9.5


def _detect_limit_down(bars: list[dict]) -> bool:
    """Detect limit-down on latest bar."""
    if not bars:
        return False
    latest = bars[0]
    pct = float(latest.get("pct_chg", 0))
    return pct <= -9.5


def _detect_gap_up(bars: list[dict]) -> bool:
    """Detect gap-up: today's low > yesterday's high."""
    if len(bars) < 2:
        return False
    today_low = float(bars[0]["low"])
    yesterday_high = float(bars[1]["high"])
    return today_low > yesterday_high


def _detect_gap_down(bars: list[dict]) -> bool:
    """Detect gap-down: today's high < yesterday's low."""
    if len(bars) < 2:
        return False
    today_high = float(bars[0]["high"])
    yesterday_low = float(bars[1]["low"])
    return today_high < yesterday_low


def _ema(values: list[float], period: int) -> list[float]:
    """Compute EMA for the given values."""
    if not values:
        return []
    multiplier = 2.0 / (period + 1)
    result = [values[0]]
    for v in values[1:]:
        result.append((v - result[-1]) * multiplier + result[-1])
    return result


_DETECTORS: list[tuple[str, str, Any]] = [
    ("MACD金叉", "macd_golden_cross", _detect_macd_golden_cross),
    ("MACD死叉", "macd_death_cross", _detect_macd_death_cross),
    ("放量突破", "volume_breakout", _detect_volume_breakout),
    ("涨停", "limit_up", _detect_limit_up),
    ("跌停", "limit_down", _detect_limit_down),
    ("跳空高开", "gap_up", _detect_gap_up),
    ("跳空低开", "gap_down", _detect_gap_down),
]


def _detect_patterns(bars: list[dict]) -> list[str]:
    """Run all pattern detectors and return matched pattern names."""
    matched = []
    for name, key, detector in _DETECTORS:
        try:
            if detector(bars):
                matched.append(name)
        except Exception:
            continue
    return matched


# ──────────────────────────────────────────────────────────────────────────────
# Main backfill logic
# ──────────────────────────────────────────────────────────────────────────────


def _get_all_stock_codes(session: Session) -> list[tuple[str, str]]:
    """Return list of (symbol, stock_name) for all active stocks."""
    rows = session.execute(
        text("SELECT symbol, stock_name FROM stock_metadata WHERE is_active = 1 ORDER BY symbol")
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def build_entry(
    symbol: str,
    stock_name: str,
    pattern: str,
    latest_bar: dict,
) -> ExperienceEntry:
    """Build an ExperienceEntry from detected pattern and latest bar data.

    This is a lightweight entry — analysis_summary is derived from the
    price action rather than from a full analysis run.
    """
    close = float(latest_bar["close"])
    pct_chg = float(latest_bar.get("pct_chg", 0))
    volume = float(latest_bar.get("volume", 0))

    return ExperienceEntry(
        id=f"bexp_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{symbol}_{pattern[:8]}",
        timestamp=datetime.now(timezone.utc),
        stock_code=symbol,
        stock_name=stock_name,
        pattern=pattern,
        analysis_summary={
            "valuation": "",
            "pa_conclusion": f"检测到{pattern}形态，当日涨幅{pct_chg:.2f}%，收盘价{close:.2f}",
            "final_decision": "",
        },
        tags=["backfill", pattern],
    )


def run_backfill(
    days: int = 60,
    limit: int = 0,
    symbols: list[str] | None = None,
) -> int:
    """Run backfill and return the number of entries saved.

    Parameters
    ----------
    days:
        Number of trailing trading days to scan.
    limit:
        Max entries to save (0 = unlimited).
    symbols:
        List of stock symbols to process.  ``None`` = all active stocks.
    """
    session = Session(engine)
    lib = get_experience_library()
    saved_count = 0

    try:
        stocks = _get_all_stock_codes(session)
        if symbols:
            stocks = [s for s in stocks if s[0] in symbols]

        logger.info("Processing %d stocks (scanning %d days)...", len(stocks), days)

        for symbol, stock_name in stocks:
            if limit and saved_count >= limit:
                break

            bars = _get_recent_bars(session, symbol, days)
            if len(bars) < 10:
                continue

            patterns = _detect_patterns(bars)
            if not patterns:
                continue

            latest_bar = bars[0]
            for pattern in patterns:
                if limit and saved_count >= limit:
                    break
                try:
                    entry = build_entry(symbol, stock_name, pattern, latest_bar)
                    lib.save(entry)
                    saved_count += 1
                    if saved_count % 50 == 0:
                        logger.info("Saved %d entries so far...", saved_count)
                except Exception as e:
                    logger.warning(
                        "Failed to save entry for %s/%s: %s",
                        symbol, pattern, e,
                    )

    finally:
        session.close()

    logger.info("Backfill complete: %d entries saved", saved_count)
    return saved_count


# ──────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill experience library from K-line data")
    parser.add_argument("--days", type=int, default=60, help="Days of trailing K-line data to scan")
    parser.add_argument("--limit", type=int, default=0, help="Max entries to save (0 = unlimited)")
    parser.add_argument(
        "--symbols", type=str, default="",
        help="Comma-separated stock codes (default: all active stocks)",
    )
    args = parser.parse_args()

    symbol_list = [s.strip() for s in args.symbols.split(",") if s.strip()] if args.symbols else None

    logger.info(
        "Starting backfill: days=%d, limit=%d, symbols=%s",
        args.days,
        args.limit or "unlimited",
        symbol_list or "all",
    )

    count = run_backfill(
        days=args.days,
        limit=args.limit,
        symbols=symbol_list,
    )

    logger.info("Done. Total entries saved: %d", count)


if __name__ == "__main__":
    main()
