"""AkShare-based A-share K-line data source (polling, no broker required).

Migrated from PA_Agent with adaptations:
- Skip Baostock fallback (not needed for initial A-share only)
- Use shared.ashare_common utility functions
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from shared.ashare_common import (
    df_to_bars_asc,
    is_index_symbol,
    normalize_ashare_symbol,
    normalize_ohlcv_df,
    resample_rows_to_4h,
    rows_to_kline_bars,
)
from shared.base import DataSource, DataSourceTransientError, KlineBar

logger = logging.getLogger(__name__)

_CN_TZ = ZoneInfo("Asia/Shanghai")

_AK_MIN_INTERVAL_S = 0.9
_last_ak_fetch_mono: float = 0.0

_MINUTE_PERIOD: dict[str, str] = {
    "1h": "60",
}

_SUPPORTED_TIMEFRAMES: tuple[str, ...] = ("1h", "4h", "1d")

_PRESET_SYMBOLS: tuple[str, ...] = (
    "000001",
    "600519",
    "000300",
    "399006",
)


def _cn_now() -> datetime:
    return datetime.now(tz=_CN_TZ)


def _ashare_session_open(now: datetime | None = None) -> bool:
    now = now or _cn_now()
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    morning = 9 * 60 + 30 <= t < 11 * 60 + 30
    afternoon = 13 * 60 <= t < 15 * 60
    return morning or afternoon


def _strip_symbol_suffix(symbol: str) -> str:
    """Convert '000001.SZ' or '000001' to raw 6-digit code '000001'."""
    raw = (symbol or "").strip()
    digits = re.sub(r"\D", "", raw)
    if len(digits) >= 6:
        return digits[-6:]
    return digits


class AkShareSource(DataSource):
    """A-share quotes via AkShare (East Money); polls on each snapshot."""

    def __init__(self) -> None:
        self._symbol: str = ""
        self._timeframe: str = ""
        self._connected: bool = False

    def connect(self) -> None:
        import akshare  # noqa: F401
        self._connected = True
        logger.info("AkShareSource connected")

    def disconnect(self) -> None:
        self._connected = False
        logger.info("AkShareSource disconnected")

    def list_symbols(self) -> list[str]:
        return list(_PRESET_SYMBOLS)

    def supported_timeframes(self) -> list[str]:
        return list(_SUPPORTED_TIMEFRAMES)

    def subscribe(self, symbol: str, timeframe: str) -> None:
        if timeframe not in _SUPPORTED_TIMEFRAMES:
            raise ValueError(
                f"Unsupported timeframe: {timeframe!r}. "
                f"Use one of {list(_SUPPORTED_TIMEFRAMES)}"
            )
        code = normalize_ashare_symbol(symbol)
        if not code:
            raise ValueError("A股代码无效，请输入 6 位数字（如 600519）或指数 sh000300")
        self._symbol = code
        self._timeframe = timeframe
        logger.info("AkShareSource subscribed: %s %s", code, timeframe)

    def unsubscribe(self) -> None:
        self._symbol = ""
        self._timeframe = ""
        logger.info("AkShareSource unsubscribed")

    def latest_snapshot(self, n: int) -> list[KlineBar]:
        if not self._connected:
            raise DataSourceTransientError("AkShare 未连接")
        if not self._symbol or not self._timeframe:
            raise DataSourceTransientError("AkShare 未订阅品种/周期")

        fetch_n = max(n + 5, 30)
        try:
            rows_asc = self._fetch_history(self._symbol, self._timeframe, fetch_n)
        except DataSourceTransientError:
            raise
        except Exception as exc:
            logger.warning("AkShare fetch failed: %s", exc)
            raise DataSourceTransientError(f"AkShare 拉取失败: {exc}") from exc

        if not rows_asc:
            raise DataSourceTransientError(
                f"AkShare 未返回数据: {self._symbol} {self._timeframe}"
            )

        if _ashare_session_open():
            self._apply_spot_to_forming(rows_asc)

        rows_newest = list(reversed(rows_asc[-fetch_n:]))
        for i, row in enumerate(rows_newest):
            row["closed"] = not (i == 0 and _ashare_session_open())

        return rows_to_kline_bars(rows_newest, n)

    # ── Fetch ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _throttle_akshare() -> None:
        global _last_ak_fetch_mono
        now = time.monotonic()
        wait = _AK_MIN_INTERVAL_S - (now - _last_ak_fetch_mono)
        if wait > 0:
            time.sleep(wait)
        _last_ak_fetch_mono = time.monotonic()

    @staticmethod
    def _call_with_retries(
        label: str,
        fn: Any,
        *,
        attempts: int = 4,
        max_wait_s: float = 12.0,
    ) -> Any:
        last_exc: Exception | None = None
        waited = 0.0
        for i in range(attempts):
            AkShareSource._throttle_akshare()
            try:
                return fn()
            except Exception as exc:
                last_exc = exc
                if i + 1 >= attempts:
                    break
                delay = min(3.0, max(1.0, max_wait_s - waited))
                if delay <= 0:
                    break
                time.sleep(delay)
                waited += delay
                logger.debug("%s retry %d/%d: %s", label, i + 2, attempts, exc)
        assert last_exc is not None
        raise last_exc

    def _fetch_history(self, symbol: str, timeframe: str, n: int) -> list[dict[str, Any]]:
        if timeframe == "1d":
            return self._fetch_daily_ak(symbol, n)
        if timeframe == "1h":
            return self._fetch_minute_ak(symbol, "60", n)
        if timeframe == "4h":
            rows_60 = self._fetch_minute_ak(symbol, "60", n * 4 + 8)
            return resample_rows_to_4h(rows_60)[-n:]
        return []

    def _fetch_daily_ak(self, symbol: str, n: int) -> list[dict[str, Any]]:
        import akshare as ak

        end = _cn_now().strftime("%Y%m%d")
        start = (_cn_now() - timedelta(days=max(n * 2, 400))).strftime("%Y%m%d")
        if is_index_symbol(symbol):
            idx = _index_symbol_for_api(symbol)
            df = self._call_with_retries(
                f"index_daily {idx}",
                lambda: ak.stock_zh_index_daily_em(symbol=idx),
            )
            if df is None or df.empty:
                return []
            df = df.tail(n + 5)
            norm = normalize_ohlcv_df(df, time_col="date")
            if norm.empty:
                return []
            return df_to_bars_asc(norm, time_col="date")
        code = normalize_ashare_symbol(symbol)
        df = self._call_with_retries(
            f"daily {code}",
            lambda: ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start,
                end_date=end,
                adjust="qfq",
            ),
        )
        norm = normalize_ohlcv_df(df, time_col="date")
        if norm.empty:
            return []
        return df_to_bars_asc(norm.tail(n + 5), time_col="date")

    def _fetch_minute_ak(self, symbol: str, period: str, n: int) -> list[dict[str, Any]]:
        import akshare as ak

        end_dt = _cn_now()
        days = max(30, (n // 4) + 15)
        start_dt = end_dt - timedelta(days=days)
        start_s = start_dt.strftime("%Y-%m-%d 09:30:00")
        end_s = end_dt.strftime("%Y-%m-%d 15:00:00")
        if is_index_symbol(symbol):
            idx = _index_symbol_for_api(symbol)
            df = self._call_with_retries(
                f"index_min {idx}",
                lambda: ak.index_zh_a_hist_min_em(
                    symbol=idx,
                    period=period,
                    start_date=start_s,
                    end_date=end_s,
                ),
            )
        else:
            code = normalize_ashare_symbol(symbol)

            def _pull() -> Any:
                return ak.stock_zh_a_hist_min_em(
                    symbol=code,
                    period=period,
                    start_date=start_s,
                    end_date=end_s,
                    adjust="qfq",
                )

            df = self._call_with_retries(f"min {code} {period}", _pull)
        norm = normalize_ohlcv_df(df, time_col="time")
        if norm.empty:
            return []
        return df_to_bars_asc(norm.tail(n + 8), time_col="time")

    def _apply_spot_to_forming(self, rows_asc: list[dict[str, Any]]) -> None:
        if not _ashare_session_open():
            return
        price = self._fetch_spot_price(self._symbol)
        if price is None or not rows_asc:
            return
        last = rows_asc[-1]
        last["close"] = price
        last["high"] = max(last["high"], price)
        last["low"] = min(last["low"], price)

    def _fetch_spot_price(self, symbol: str) -> float | None:
        try:
            import akshare as ak

            if is_index_symbol(symbol):
                return None
            code = normalize_ashare_symbol(symbol)
            df = self._call_with_retries(
                f"spot {code}",
                lambda: ak.stock_individual_info_em(symbol=code),
                attempts=2,
                max_wait_s=6.0,
            )
            if df is None or df.empty:
                return None
            item_col = "item" if "item" in df.columns else df.columns[0]
            val_col = "value" if "value" in df.columns else df.columns[1]
            for item, val in zip(df[item_col], df[val_col], strict=False):
                if str(item).strip() in ("最新", "最新价"):
                    return float(val)
            return None
        except Exception as exc:
            logger.debug("AkShare spot fetch failed: %s", exc)
            return None


def _index_symbol_for_api(symbol: str) -> str:
    sym = normalize_ashare_symbol(symbol)
    if sym.startswith(("sh", "sz")):
        return sym
    if sym.startswith("399"):
        return f"sz{sym}"
    return f"sh{sym}"
