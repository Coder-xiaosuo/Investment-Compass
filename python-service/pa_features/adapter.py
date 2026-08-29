"""适配器：把当前项目 KlineBar 列表转换为 pa_features.KlineFrame。

输入 bars 为当前项目 ``shared.base.KlineBar`` 列表（索引 0 = 最新，
newest-first，seq=1 为最新已收盘棒，与 Pa_Agent 语义一致）。

本模块不 import shared 包（鸭子类型），保持 pa_features 完全自包含；
指标（EMA20/ATR14）在构造 KlineFrame 时按 Pa_Agent 约定一次性算好并
与 bars 逐根对齐（索引 0 = 最新棒的指标值）。
"""
from __future__ import annotations

import time
from typing import Any, Sequence

from .base import IndicatorBundle, KlineBar, KlineFrame
from .indicators import atr_full, ema_full
from .kline_features import compute_kline_geometry_features, render_kline_feature_table
from .market_features import compute_simple_market_features, render_simple_market_features

_EMA_PERIOD = 20
_ATR_PERIOD = 14


def _to_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def from_bars(
    bars: Sequence[Any],
    symbol: str = "",
    timeframe: str = "1d",
) -> KlineFrame:
    """把当前项目 KlineBar 列表（newest-first）转成 pa_features.KlineFrame。

    - ``bars`` 索引 0 = 最新 K 线；seq 按位置 1..n 重新赋值（与 Pa_Agent
      seq=1 最新一致），顺序保持 newest-first 不变。
    - 字段逐一映射 open/high/low/close/volume/amount/pct_chg/ts_open/closed，
      数值统一转 float。
    - 派生指标：EMA20（收盘价）、ATR14 在 oldest-first 序列上计算后翻转，
      与 newest-first 的 bars 逐根对齐。
    """
    pa_bars: list[KlineBar] = []
    for i, b in enumerate(bars):
        pa_bars.append(
            KlineBar(
                seq=i + 1,
                ts_open=_to_float(getattr(b, "ts_open", 0.0)),
                open=_to_float(getattr(b, "open", 0.0)),
                high=_to_float(getattr(b, "high", 0.0)),
                low=_to_float(getattr(b, "low", 0.0)),
                close=_to_float(getattr(b, "close", 0.0)),
                volume=_to_float(getattr(b, "volume", 0.0)),
                amount=_to_float(getattr(b, "amount", 0.0)),
                pct_chg=getattr(b, "pct_chg", None),
                closed=bool(getattr(b, "closed", True)),
            )
        )

    if not pa_bars:
        return KlineFrame(
            symbol=symbol,
            timeframe=timeframe,
            bars=(),
            indicators=IndicatorBundle(ema20=(), atr14=()),
            snapshot_ts_local_ms=int(time.time() * 1000),
        )

    bars_tuple = tuple(pa_bars)
    # 指标在 oldest-first 序列上计算，再翻转回 newest-first 对齐。
    closes_old = [b.close for b in reversed(bars_tuple)]
    highs_old = [b.high for b in reversed(bars_tuple)]
    lows_old = [b.low for b in reversed(bars_tuple)]
    ema20_old = ema_full(closes_old, _EMA_PERIOD)
    atr14_old = atr_full(highs_old, lows_old, closes_old, _ATR_PERIOD)

    return KlineFrame(
        symbol=symbol,
        timeframe=timeframe,
        bars=bars_tuple,
        indicators=IndicatorBundle(
            ema20=tuple(reversed(ema20_old)),
            atr14=tuple(reversed(atr14_old)),
        ),
        snapshot_ts_local_ms=int(time.time() * 1000),
    )


def render_all_features(frame: KlineFrame) -> str:
    """拼接市场结构特征 + 逐棒几何特征表，输出给 LLM 的特征文本块。"""
    features = compute_simple_market_features(frame)
    geometry = compute_kline_geometry_features(frame)
    return (
        render_simple_market_features(features)
        + "\n\n"
        + render_kline_feature_table(geometry)
    )
