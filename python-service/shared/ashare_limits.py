"""A-share limit-up / limit-down detection for table and chart markers."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Sequence
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from shared.base import KlineBar, KlineFrame

_CN_TZ = ZoneInfo("Asia/Shanghai")


def normalize_stock_code(symbol: str) -> str:
    raw = (symbol or "").strip().lower()
    if raw.startswith(("sh", "sz")) and len(raw) >= 8:
        return raw[2:8]
    digits = "".join(ch for ch in raw if ch.isdigit())
    return digits[-6:] if len(digits) >= 6 else digits


def limit_pct(symbol: str, stock_name: str = "") -> float:
    """Return daily limit ratio (0.10 = 10%)."""
    name = (stock_name or "").upper()
    if "ST" in name:
        return 0.05
    code = normalize_stock_code(symbol)
    if code.startswith(("300", "301", "688", "689")):
        return 0.20
    if code.startswith(("8", "43", "92")):
        return 0.30
    return 0.10


def limit_prices(prev_close: float, ratio: float) -> tuple[float, float]:
    up = round(prev_close * (1.0 + ratio), 2)
    down = round(prev_close * (1.0 - ratio), 2)
    return up, down


def _bar_trade_date(bar: "KlineBar"):
    ts_ms = int(bar.ts_open)
    if ts_ms < 1_000_000_000_000:
        ts_ms *= 1000
    return datetime.fromtimestamp(ts_ms / 1000, tz=_CN_TZ).date()


def trading_day_close_map(bars: Sequence["KlineBar"]) -> dict:
    """Map each trading date to that session's official close (last bar of the day)."""
    closes: dict = {}
    for bar in reversed(bars):
        closes[_bar_trade_date(bar)] = bar.close
    return closes


def _bars_cache_key(bars: Sequence["KlineBar"]) -> tuple:
    """Hashable key for memoizing close maps on a bar sequence."""
    return tuple((int(b.ts_open), float(b.close)) for b in bars)


_LAST_CLOSE_MAP_KEY: tuple | None = None
_LAST_CLOSE_MAP: dict = {}


def _close_map_for_bars(bars: Sequence["KlineBar"]) -> dict:
    global _LAST_CLOSE_MAP_KEY, _LAST_CLOSE_MAP
    key = _bars_cache_key(bars)
    if key == _LAST_CLOSE_MAP_KEY:
        return _LAST_CLOSE_MAP
    closes = trading_day_close_map(bars)
    _LAST_CLOSE_MAP_KEY = key
    _LAST_CLOSE_MAP = closes
    return closes


def prev_trading_day_close(bars: Sequence["KlineBar"], index: int) -> float | None:
    """Previous trading day's close for ``bars[index]`` (newest-first list)."""
    if index < 0 or index >= len(bars):
        return None
    day = _bar_trade_date(bars[index])
    closes = _close_map_for_bars(bars)
    days = sorted(closes.keys(), reverse=True)
    try:
        pos = days.index(day)
    except ValueError:
        return None
    if pos + 1 >= len(days):
        return None
    return closes[days[pos + 1]]


def effective_pct_chg(bar: "KlineBar", prev_close: float | None) -> float | None:
    """Return change %; prefer API ``pct_chg``, else compute from prev close."""
    pct = getattr(bar, "pct_chg", None)
    if pct is not None:
        return float(pct)
    if prev_close is None or prev_close <= 0:
        return None
    return (bar.close - prev_close) / prev_close * 100.0


def _near(price: float, target: float, eps: float = 0.015) -> bool:
    return abs(price - target) <= eps


def limit_bar_label(
    bar: "KlineBar",
    *,
    prev_close: float | None,
    symbol: str,
    stock_name: str = "",
) -> str:
    """Return 涨停 / 一字涨停 / 跌停 / 一字跌停, or empty string."""
    if prev_close is None or prev_close <= 0:
        prev_close = None
    pct = effective_pct_chg(bar, prev_close)
    if pct is None:
        return ""

    ratio = limit_pct(symbol, stock_name)
    lim_pct = ratio * 100.0
    eps = 0.12

    up_px, down_px = limit_prices(prev_close, ratio) if prev_close else (None, None)

    if pct >= lim_pct - eps:
        if up_px is not None and _near(bar.open, up_px) and _near(bar.low, up_px):
            return "一字涨停"
        return "涨停"

    if pct <= -lim_pct + eps:
        if down_px is not None and _near(bar.open, down_px) and _near(bar.high, down_px):
            return "一字跌停"
        return "跌停"

    return ""


def limit_labels_for_frame(
    bars: Sequence["KlineBar"],
    symbol: str,
    *,
    stock_name: str = "",
) -> list[str]:
    """Parallel labels for newest-first *bars*."""
    closes = _close_map_for_bars(bars)
    days_sorted = sorted(closes.keys(), reverse=True)
    day_index = {d: i for i, d in enumerate(days_sorted)}

    labels: list[str] = []
    for bar in bars:
        day = _bar_trade_date(bar)
        pos = day_index.get(day)
        prev_close = None
        if pos is not None and pos + 1 < len(days_sorted):
            prev_close = closes[days_sorted[pos + 1]]
        labels.append(
            limit_bar_label(
                bar,
                prev_close=prev_close,
                symbol=symbol,
                stock_name=stock_name,
            )
        )
    return labels
