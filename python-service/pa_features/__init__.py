"""pa_features：程序化市场特征计算模块（从 Pa_Agent 移植）。

为 LLM 提供客观锚点：区间位置、铁丝网、H/L 计数、结构级别、突破事件、
MeasuredMove 候选与逐棒几何特征表。

典型用法：:

    from pa_features import from_bars, render_all_features
    frame = from_bars(bars_newest_first, symbol="002594", timeframe="1d")
    text = render_all_features(frame)
"""
from __future__ import annotations

from .adapter import from_bars, render_all_features
from .base import IndicatorBundle, KlineBar, KlineFrame, normalize_kline_bar
from .indicators import (
    AtrState,
    EmaState,
    atr_full,
    atr_incremental,
    ema_full,
    ema_incremental,
    make_atr_state,
    make_ema_state,
    state_after,
    state_after_atr,
)
from .kline_features import (
    KlineGeometryFeature,
    bar_candle_direction_label,
    compute_kline_geometry_features,
    render_kline_feature_table,
)
from .market_features import (
    BreakoutEvent,
    HLCountState,
    MeasuredMoveCandidate,
    SimpleMarketFeatures,
    SwingPivot,
    build_program_features_dict,
    compute_simple_market_features,
    inject_market_features_section,
    render_simple_market_features,
)
from .price_tick import infer_price_tick_from_frame

__all__ = [
    # 适配器
    "from_bars",
    "render_all_features",
    # 数据类型
    "KlineBar",
    "KlineFrame",
    "IndicatorBundle",
    "normalize_kline_bar",
    # 指标
    "ema_full",
    "ema_incremental",
    "EmaState",
    "make_ema_state",
    "state_after",
    "atr_full",
    "atr_incremental",
    "AtrState",
    "make_atr_state",
    "state_after_atr",
    # 价格跳动
    "infer_price_tick_from_frame",
    # 市场结构特征
    "SimpleMarketFeatures",
    "SwingPivot",
    "BreakoutEvent",
    "HLCountState",
    "MeasuredMoveCandidate",
    "compute_simple_market_features",
    "render_simple_market_features",
    "build_program_features_dict",
    "inject_market_features_section",
    # 逐棒几何特征
    "KlineGeometryFeature",
    "compute_kline_geometry_features",
    "render_kline_feature_table",
    "bar_candle_direction_label",
]
