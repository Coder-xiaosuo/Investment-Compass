"""入库前 K 线数据质量过滤器。

在数据写入 market_data 表前执行校验，防止脏数据污染数据库。
校验规则：
- 价格: open/high/low/close > 0
- 高低关系: low <= close <= high
- 成交量: volume >= 0
- 涨跌幅: pct_chg is None or abs(pct_chg) < 100
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def filter_kline_bar(bar: dict[str, Any]) -> tuple[bool, str]:
    """校验单根 K 线数据是否合法。

    Args:
        bar: 包含 ohlcv 字段的字典。

    Returns:
        (is_valid, reason) 二元组。
    """
    open_ = bar.get("open", 0)
    high = bar.get("high", 0)
    low = bar.get("low", 0)
    close = bar.get("close", 0)
    volume = bar.get("volume", 0)
    pct_chg = bar.get("pct_chg")

    if open_ <= 0:
        return False, f"open <= 0 ({open_})"
    if high <= 0:
        return False, f"high <= 0 ({high})"
    if low <= 0:
        return False, f"low <= 0 ({low})"
    if close <= 0:
        return False, f"close <= 0 ({close})"

    if low > high:
        return False, f"low ({low}) > high ({high})"

    if close < low:
        return False, f"close ({close}) < low ({low})"
    if close > high:
        return False, f"close ({close}) > high ({high})"

    if volume < 0:
        return False, f"volume < 0 ({volume})"

    if pct_chg is not None and abs(pct_chg) >= 100:
        return False, f"abs(pct_chg) >= 100 ({pct_chg})"

    return True, ""


def filter_kline_bars(bars: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """批量过滤 K 线数据。

    Args:
        bars: K 线字典列表。

    Returns:
        (valid_bars, rejected_bars) 二元组。
    """
    valid: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for bar in bars:
        ok, reason = filter_kline_bar(bar)
        if ok:
            valid.append(bar)
        else:
            symbol = bar.get("symbol", "?")
            trade_date = bar.get("trade_date", "?")
            logger.warning("Data filter rejected [%s] %s: %s", symbol, trade_date, reason)
            rejected.append(bar)
    return valid, rejected
