"""从 K 线 OHLC 小数位推断最小价格跳动（tick）。

从 Pa_Agent ``pa_agent/util/price_tick.py`` 移植，仅保留特征计算所需的
``infer_price_tick_from_frame``（其余突破单定价辅助函数不属于纯算法特征层）。
"""
from __future__ import annotations

from typing import Any


def infer_price_tick_from_frame(kline_frame: Any) -> float | None:
    """根据快照中 OHLC 的小数位猜测一个最小跳动（如 XAU 0.01 或 0.001）。"""
    bars = getattr(kline_frame, "bars", None) if kline_frame is not None else None
    if not bars:
        return None

    max_decimals = 0
    for bar in bars:
        for attr in ("open", "high", "low", "close"):
            try:
                value = float(getattr(bar, attr))
            except (TypeError, ValueError):
                continue
            text = f"{value:.12f}".rstrip("0")
            if "." in text:
                max_decimals = max(max_decimals, len(text.split(".")[1]))

    if max_decimals <= 0:
        return 1.0
    return 10 ** (-min(max_decimals, 6))
