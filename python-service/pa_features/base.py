"""核心数据类型：KlineBar / KlineFrame / IndicatorBundle。

从 Pa_Agent ``pa_agent/data/base.py`` 移植，仅保留计算特征所需的数据类
（KlineBar、KlineFrame 及其必要依赖 IndicatorBundle），并内联了
``ts_open_to_ms`` 的简化实现（与 Pa_Agent ``datetime_ts.ts_open_to_ms``
逻辑一致），使本包完全自包含、不依赖外部数据源抽象。
"""
from __future__ import annotations

from dataclasses import dataclass


# ── KlineBar ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class KlineBar:
    """单根 OHLCV K 线，附带序号与是否收盘的标记。"""
    seq: int           # 1 = 最新已收盘 K 线，N = 最旧；0 = 正在形成中的 K 线（不计入统计）
    ts_open: float     # K 线开盘时间的 Unix 时间戳（毫秒，UTC）
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float = 0.0   # 成交额；数据源不提供时为 0
    pct_chg: float | None = None  # 涨跌幅 (%)，由接口提供时填入，否则为 None
    closed: bool = True   # False 表示当前正在形成中的 K 线


def _ts_open_to_ms(ts_open: float) -> float:
    """将 K 线开盘时间归一化为毫秒级 Unix 时间戳（与 Pa_Agent 一致）。"""
    ts = float(ts_open)
    if ts <= 0:
        return ts
    if ts < 1e10:
        return ts * 1000.0
    return ts


def normalize_kline_bar(bar: KlineBar) -> KlineBar:
    """规范化 K 线字段：ts_open 统一为毫秒；保证 high >= low、low <= close <= high。"""
    ts_ms = _ts_open_to_ms(bar.ts_open)
    high = max(bar.high, bar.low)
    low = min(bar.high, bar.low)
    close = max(low, min(high, bar.close))
    if (
        high == bar.high
        and low == bar.low
        and close == bar.close
        and ts_ms == bar.ts_open
    ):
        return bar
    return KlineBar(
        seq=bar.seq,
        ts_open=ts_ms,
        open=bar.open,
        high=high,
        low=low,
        close=close,
        volume=bar.volume,
        amount=getattr(bar, "amount", 0.0),
        pct_chg=getattr(bar, "pct_chg", None),
        closed=bar.closed,
    )


# ── IndicatorBundle ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class IndicatorBundle:
    """单根 K 线粒度的技术指标集合，与 KlineFrame 的 bars 列表逐根对齐。"""
    ema20: tuple[float, ...]   # 20 周期 EMA；长度与 bars 相同，预热期内为 nan
    atr14: tuple[float, ...]   # 14 周期 ATR；长度与 bars 相同，预热期内为 nan


# ── KlineFrame ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class KlineFrame:
    """K 线行情的不可变快照，包含 N 根 K 线及其对应的技术指标。

    bars[0] 为最新 K 线（seq=1），bars[-1] 为最旧 K 线（seq=N）。
    snapshot_ts_local_ms 为生成该快照时的本机本地时间（毫秒）。
    """
    symbol: str
    timeframe: str
    bars: tuple[KlineBar, ...]
    indicators: IndicatorBundle
    snapshot_ts_local_ms: int   # 快照生成时的本地时间（自 epoch 起的毫秒数）
