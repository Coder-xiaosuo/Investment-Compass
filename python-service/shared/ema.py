"""Exponential Moving Average (EMA) — full and incremental."""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class EmaState:
    """Minimal state for incremental EMA computation."""
    last: float       # most recent EMA value (nan during warm-up)
    period: int
    count: int        # number of values seen so far
    _sum: float       # running sum during warm-up phase


def ema_full(values: list[float], period: int) -> list[float]:
    """Compute EMA over *values* (oldest-first).

    Returns a list of the same length:
    - Indices 0 .. period-2: nan  (warm-up)
    - Index period-1: simple mean of first *period* values
    - Index period .. end: EMA with multiplier α = 2/(period+1)

    Args:
        values: Price series, oldest first.
        period: EMA period (must be >= 1).
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")
    n = len(values)
    result = [math.nan] * n
    if n < period:
        return result

    alpha = 2.0 / (period + 1)
    # Seed with simple mean of first *period* values
    seed = sum(values[:period]) / period
    result[period - 1] = seed
    prev = seed
    for i in range(period, n):
        prev = values[i] * alpha + prev * (1.0 - alpha)
        result[i] = prev
    return result


def ema_incremental(state: EmaState, x: float) -> EmaState:
    """Update EMA state with one new value *x*.

    During warm-up (count < period), accumulates a running sum.
    At count == period-1 (i.e., after this call count == period), seeds the EMA.
    After warm-up, applies the standard EMA formula.
    """
    period = state.period
    count = state.count + 1
    alpha = 2.0 / (period + 1)

    if count < period:
        # Still in warm-up: accumulate sum, last stays nan
        return EmaState(last=math.nan, period=period, count=count, _sum=state._sum + x)
    elif count == period:
        # Seed: simple mean
        seed = (state._sum + x) / period
        return EmaState(last=seed, period=period, count=count, _sum=0.0)
    else:
        # Normal EMA update
        new_last = x * alpha + state.last * (1.0 - alpha)
        return EmaState(last=new_last, period=period, count=count, _sum=0.0)


def make_ema_state(period: int) -> EmaState:
    """Create a fresh EmaState for a given period."""
    return EmaState(last=math.nan, period=period, count=0, _sum=0.0)


def state_after(values: list[float], period: int) -> EmaState:
    """Return the EmaState after processing all values in *values*."""
    state = make_ema_state(period)
    for v in values:
        state = ema_incremental(state, v)
    return state
