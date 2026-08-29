"""数据模型层核心定义。

本模块定义了 K 线数据流中使用的核心不可变数据结构，以及行情数据源
(DataSource) 的抽象基类。主要内容包括：

- KlineBar：单根 OHLCV K 线（开高低收 + 成交量/成交额）。
- normalize_kline_bar：对 K 线字段进行规范化处理（时间戳、高低收关系）。
- IndicatorBundle：与 KlineFrame 中 bars 列表逐根对齐的技术指标集合。
- KlineFrame：包含 N 根 K 线及其对应指标的不可变快照。
- DataSource / DataSourceError / DataSourceTransientError：行情数据源抽象接口与异常体系。
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Sequence


# ── KlineBar ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class KlineBar:
    """单根 OHLCV K 线，附带序号与是否收盘的标记。

    该结构为不可变 (frozen) 数据类，表示某一时间周期内的一根 K 线，
    包含开盘价、最高价、最低价、收盘价、成交量、成交额等基础行情字段，
    以及用于排序的序号 (seq) 和标识是否仍在形成中的标记 (closed)。
    """
    seq: int           # 序号：1 = 最新已收盘 K 线，N = 最旧 K 线；0 = 正在形成中的 K 线（不计入统计）
    ts_open: float     # K 线开盘时间的 Unix 时间戳（毫秒，UTC）
    open: float        # 开盘价
    high: float        # 最高价
    low: float         # 最低价
    close: float       # 收盘价
    volume: float      # 成交量
    amount: float = 0.0   # 成交额；数据源不提供时为 0
    pct_chg: float | None = None  # 涨跌幅 (%)，由接口提供时填入，否则为 None
    closed: bool = True   # 是否已收盘；False 表示当前正在形成中的 K 线


def normalize_kline_bar(bar: KlineBar) -> KlineBar:
    """对 K 线字段进行规范化处理。

    规范化内容包括：
    - 将 ``ts_open`` 统一为毫秒级 Unix 时间戳；
    - 保证 ``high >= low``（取较大者为 high，较小者为 low）；
    - 保证 ``low <= close <= high``（将 close 截断到 [low, high] 区间内）。

    若原始 K 线已满足上述条件，则原样返回；否则返回一个修正后的新 KlineBar。
    """
    from shared.datetime_ts import ts_open_to_ms

    ts_ms = ts_open_to_ms(bar.ts_open)
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
    """单根 K 线粒度的技术指标集合，与 KlineFrame 的 bars 列表逐根对齐。

    每个字段都是一个与 bars 等长的元组，索引一一对应；在指标的预热期
    (warm-up period) 内对应的值用 nan 表示。
    """
    ema20: tuple[float, ...]   # 20 周期指数移动平均线；长度与 bars 相同，预热期内为 nan
    atr14: tuple[float, ...]   # 14 周期平均真实波幅 (ATR)；长度与 bars 相同，预热期内为 nan


# ── KlineFrame ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class KlineFrame:
    """K 线行情的不可变快照，包含 N 根 K 线及其对应的技术指标。

    bars[0] 为最新 K 线 (seq=1, closed=False，即正在形成中的 K 线)。
    bars[-1] 为最旧 K 线 (seq=N, closed=True)。
    snapshot_ts_local_ms 为生成该快照时的本机本地时间。
    """
    symbol: str                       # 标的代码，如 "EURUSD"、"000001.SZ"
    timeframe: str                    # 时间周期，如 "1m"、"5m"、"1h"、"1d"
    bars: tuple[KlineBar, ...]        # K 线元组，索引 0 为最新 K 线
    indicators: IndicatorBundle       # 与 bars 逐根对齐的技术指标集合
    snapshot_ts_local_ms: int         # 快照生成时的本地时间（自 epoch 起的毫秒数）
    volume_ratios: tuple[float | None, ...] = ()  # 量比：volume[i] / 5日均量，与 bars 逐根对齐


# ── DataSource ABC ────────────────────────────────────────────────────────────

class DataSourceError(Exception):
    """数据源相关异常的基类。"""


class DataSourceTransientError(DataSourceError):
    """数据源瞬时异常（可重试）。

    用于表示网络抖动等可恢复的临时性错误，调用方可据此进行重试。
    """


class DataSource(ABC):
    """K 线行情数据源的抽象接口。

    定义了行情数据源需实现的标准方法集合，包括连接管理、标的与周期查询、
    订阅/取消订阅以及获取最新快照等。

    已知实现：
    - TradingViewSource：当前主力实现。
    - MT5Source：占位桩实现 (stub)。
    """

    @abstractmethod
    def connect(self) -> None:
        """建立连接并进行认证。"""

    @abstractmethod
    def disconnect(self) -> None:
        """干净地断开连接，释放资源。"""

    @abstractmethod
    def list_symbols(self) -> list[str]:
        """返回数据源可用的标的代码列表。"""

    @abstractmethod
    def supported_timeframes(self) -> list[str]:
        """返回支持的时间周期字符串列表，例如 ['1m','5m','1h','1d']。"""

    @abstractmethod
    def subscribe(self, symbol: str, timeframe: str) -> None:
        """订阅指定 *symbol* 在 *timeframe* 周期下的实时行情更新。"""

    @abstractmethod
    def unsubscribe(self) -> None:
        """取消当前订阅。"""

    @abstractmethod
    def latest_snapshot(self, n: int) -> list[KlineBar]:
        """返回最近 *n* 根 K 线（索引 0 为最新，包含正在形成中的 K 线）。

        当出现可恢复的网络问题时，抛出 DataSourceTransientError。
        """
