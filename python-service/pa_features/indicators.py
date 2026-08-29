"""EMA / ATR 指标实现（纯函数）。

从 Pa_Agent ``pa_agent/indicators/ema.py`` 与 ``atr.py`` 合并移植，
保留全量计算与增量状态机两种形式，实现逻辑与 Pa_Agent 完全一致。
"""
from __future__ import annotations

import math
from dataclasses import dataclass


# ── Exponential Moving Average (EMA) ─────────────────────────────────────────

@dataclass(frozen=True)
class EmaState:
    """增量 EMA 计算的最小状态。"""
    last: float       # 最新 EMA 值（预热期内为 nan）
    period: int
    count: int        # 已处理的数据点数
    _sum: float       # 预热期内的滚动累加和


def ema_full(values: list[float], period: int) -> list[float]:
    """在 *values*（旧→新）上计算 EMA，返回等长列表。

    - 索引 0 .. period-2：nan（预热期）
    - 索引 period-1：前 *period* 个值的简单平均
    - 索引 period .. 末尾：EMA，乘子 α = 2/(period+1)

    Args:
        values: 价格序列，旧→新。
        period: EMA 周期（必须 >= 1）。
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")
    n = len(values)
    result = [math.nan] * n
    if n < period:
        return result

    alpha = 2.0 / (period + 1)
    # 以前 *period* 个值的简单平均作为种子
    seed = sum(values[:period]) / period
    result[period - 1] = seed
    prev = seed
    for i in range(period, n):
        prev = values[i] * alpha + prev * (1.0 - alpha)
        result[i] = prev
    return result


def ema_incremental(state: EmaState, x: float) -> EmaState:
    """用新值 *x* 更新 EMA 状态。

    预热期内（count < period）累加滚动和；在 count == period-1
    （即本次调用后 count == period）时以简单平均作为种子；
    预热结束后应用标准 EMA 公式。
    """
    period = state.period
    count = state.count + 1
    alpha = 2.0 / (period + 1)

    if count < period:
        # 仍在预热：累加和，last 保持 nan
        return EmaState(last=math.nan, period=period, count=count, _sum=state._sum + x)
    elif count == period:
        # 种子：简单平均
        seed = (state._sum + x) / period
        return EmaState(last=seed, period=period, count=count, _sum=0.0)
    else:
        # 标准 EMA 更新
        new_last = x * alpha + state.last * (1.0 - alpha)
        return EmaState(last=new_last, period=period, count=count, _sum=0.0)


def make_ema_state(period: int) -> EmaState:
    """为给定周期创建全新的 EmaState。"""
    return EmaState(last=math.nan, period=period, count=0, _sum=0.0)


def state_after(values: list[float], period: int) -> EmaState:
    """返回处理完 *values* 全部值之后的 EmaState。"""
    state = make_ema_state(period)
    for v in values:
        state = ema_incremental(state, v)
    return state


# ── Average True Range (ATR, Wilder 平滑) ────────────────────────────────────

@dataclass(frozen=True)
class AtrState:
    """增量 ATR 计算的最小状态。"""
    last: float       # 最新 ATR 值（预热期内为 nan）
    period: int
    count: int        # 已处理的 K 线数量
    prev_close: float # 前一根 K 线的收盘价（未设置时为 nan）
    _sum_tr: float    # 预热期内 TR 的滚动累加和


def _true_range(high: float, low: float, prev_close: float) -> float:
    """计算单根 K 线的 True Range。"""
    hl = abs(high - low)
    if math.isnan(prev_close):
        return hl
    return max(hl, abs(high - prev_close), abs(low - prev_close))


def atr_full(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> list[float]:
    """在并列 OHLC 列表（旧→新）上计算 ATR，返回等长列表。

    - 索引 0 .. period-2：nan（预热期）
    - 索引 period-1：前 *period* 个 True Range 的简单平均
    - 索引 period .. 末尾：Wilder 平滑  ATR_t = (ATR_{t-1}*(period-1) + TR_t) / period

    Args:
        highs, lows, closes: 价格序列，旧→新，三者等长。
        period: ATR 周期（必须 >= 1）。
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")
    n = len(highs)
    if n != len(lows) or n != len(closes):
        raise ValueError("highs, lows, closes must have the same length")
    result = [math.nan] * n
    if n < period:
        return result

    # 逐棒计算 TR
    trs: list[float] = []
    for i in range(n):
        prev_c = closes[i - 1] if i > 0 else math.nan
        trs.append(_true_range(highs[i], lows[i], prev_c))

    # 以前 *period* 个 TR 的简单平均作为种子
    seed = sum(trs[:period]) / period
    result[period - 1] = seed
    prev_atr = seed
    for i in range(period, n):
        prev_atr = (prev_atr * (period - 1) + trs[i]) / period
        result[i] = prev_atr
    return result


def atr_incremental(state: AtrState, high: float, low: float, close: float) -> AtrState:
    """用一根新 K 线（high, low, close）更新 ATR 状态。

    预热期内（count < period）累加 TR 和；在 count == period 时以
    简单平均作为种子；预热结束后应用 Wilder 平滑。
    """
    period = state.period
    count = state.count + 1
    tr = _true_range(high, low, state.prev_close)

    if count < period:
        return AtrState(
            last=math.nan, period=period, count=count,
            prev_close=close, _sum_tr=state._sum_tr + tr,
        )
    elif count == period:
        seed = (state._sum_tr + tr) / period
        return AtrState(
            last=seed, period=period, count=count,
            prev_close=close, _sum_tr=0.0,
        )
    else:
        new_last = (state.last * (period - 1) + tr) / period
        return AtrState(
            last=new_last, period=period, count=count,
            prev_close=close, _sum_tr=0.0,
        )


def make_atr_state(period: int = 14) -> AtrState:
    """为给定周期创建全新的 AtrState。"""
    return AtrState(last=math.nan, period=period, count=0, prev_close=math.nan, _sum_tr=0.0)


def state_after_atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> AtrState:
    """返回处理完所有 K 线之后的 AtrState。"""
    state = make_atr_state(period)
    for h, l, c in zip(highs, lows, closes):
        state = atr_incremental(state, h, l, c)
    return state
