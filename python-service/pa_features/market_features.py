"""简单确定性的市场结构特征，为 LLM 提供客观锚点。

从 Pa_Agent ``pa_agent/ai/market_features.py`` 完整移植，仅将 import
路径改为包内相对导入。只计算客观、低歧义的事实（区间位置、重叠、波段、
突破收回、H/L 计数触发、结构/MM 候选）；楔形、MTR 等复杂形态标签仍交由模型判断。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .base import KlineBar, KlineFrame
from .price_tick import infer_price_tick_from_frame

MARKET_FEATURES_SECTION_PREFIX = "## 程序结构辅助特征"
_DEFAULT_LOOKBACK = 40
_RECENT_BREAKOUT_MAX_SEQ = 12
_MAX_BREAKOUT_EVENTS = 6
_EVENT_PRIORITY = {"failed": 0, "breakout": 1, "test": 2}
_OVERLAP_WINDOW = 10
_BARBWIRE_OVERLAP_THRESHOLD = 0.65
_BARBWIRE_WIDTH_ATR_MAX = 3.0
_BARBWIRE_SCORE_THRESHOLD = 0.6
_BREAKOUT_RECLAIM_BARS = 5
_BREAKOUT_TEST_TOLERANCE_ATR = 0.15


@dataclass(frozen=True)
class SwingPivot:
    seq: int
    kind: str  # high | low
    price: float


@dataclass(frozen=True)
class BreakoutEvent:
    level_price: float
    level_kind: str
    event: str  # breakout | failed | test
    trigger_seq: int
    bar_range: str
    note: str


@dataclass(frozen=True)
class HLCountState:
    bull_count: int
    bear_count: int
    last_bull_trigger_seq: int | None
    last_bear_trigger_seq: int | None
    bull_candidate: str  # none | h1 | h2 | h3
    bear_candidate: str  # none | l1 | l2 | l3
    bar_range: str


@dataclass(frozen=True)
class MeasuredMoveCandidate:
    kind: str  # range_up | range_down | leg_up | leg_down
    reference: str
    height: float
    target_price: float
    bar_range: str


@dataclass(frozen=True)
class SimpleMarketFeatures:
    lookback_bars: int
    range_high: float | None
    range_low: float | None
    range_width_atr: float | None
    price_position: float | None
    zone: str
    dist_to_high_atr: float | None
    dist_to_low_atr: float | None
    overlap_mean_10: float | None
    doji_inside_ratio_10: float | None
    barbwire_score: float
    barbwire_candidate: bool
    swing_structure: str
    swings: tuple[SwingPivot, ...]
    pullback_depth_atr: float | None
    pullback_bars: int | None
    breakout_events: tuple[BreakoutEvent, ...]
    hl_count: HLCountState
    supports: tuple[float, ...]
    resistances: tuple[float, ...]
    invalidation_long: float | None
    invalidation_short: float | None
    measured_moves: tuple[MeasuredMoveCandidate, ...]


def compute_simple_market_features(
    frame: KlineFrame,
    *,
    lookback: int = _DEFAULT_LOOKBACK,
) -> SimpleMarketFeatures:
    """为一个 KlineFrame 计算简单预计算特征包。"""
    bars = frame.bars
    n = len(bars)
    if n == 0:
        return _empty_features(lookback)

    window = bars[: min(lookback, n)]
    atr_val = _current_atr(frame)
    close = float(window[0].close)

    range_high, range_low = _range_envelope(window)
    range_width_atr = None
    price_position = None
    zone = "unknown"
    dist_high = None
    dist_low = None

    if range_high is not None and range_low is not None and range_high > range_low:
        width = range_high - range_low
        if atr_val and atr_val > 0:
            range_width_atr = round(width / atr_val, 3)
            dist_high = round((range_high - close) / atr_val, 3)
            dist_low = round((close - range_low) / atr_val, 3)
        price_position = round((close - range_low) / width, 3)
        zone = _zone_from_position(price_position)

    overlap_mean = _mean_overlap_ratio(window, min(_OVERLAP_WINDOW, len(window)))
    doji_ratio = _doji_inside_ratio(window, min(_OVERLAP_WINDOW, len(window)))
    barbwire_score = _barbwire_score(
        overlap_mean,
        doji_ratio,
        range_width_atr,
        window,
        atr_val,
    )

    swings = _find_swings_with_seq(window)
    swing_structure = _label_swing_structure(swings)
    pullback_depth, pullback_bars = _pullback_metrics(window, swings, atr_val, close)

    tick = infer_price_tick_from_frame(frame) or 0.0
    raw_breakout_events = _detect_breakout_events(
        window,
        range_high,
        range_low,
        tick=tick,
        atr=atr_val,
    )
    breakout_events = _dedupe_breakout_events(raw_breakout_events)

    hl_count = _compute_hl_count(window, atr_val)
    supports, resistances = _structure_levels(window, close, swings)
    invalidation_long = supports[0] if supports else None
    invalidation_short = resistances[0] if resistances else None
    measured_moves = _measured_move_candidates(
        range_high,
        range_low,
        swings,
        close,
        lookback=min(lookback, n),
    )

    return SimpleMarketFeatures(
        lookback_bars=min(lookback, n),
        range_high=range_high,
        range_low=range_low,
        range_width_atr=range_width_atr,
        price_position=price_position,
        zone=zone,
        dist_to_high_atr=dist_high,
        dist_to_low_atr=dist_low,
        overlap_mean_10=overlap_mean,
        doji_inside_ratio_10=doji_ratio,
        barbwire_score=round(barbwire_score, 3),
        barbwire_candidate=barbwire_score >= _BARBWIRE_SCORE_THRESHOLD,
        swing_structure=swing_structure,
        swings=tuple(swings),
        pullback_depth_atr=pullback_depth,
        pullback_bars=pullback_bars,
        breakout_events=tuple(breakout_events),
        hl_count=hl_count,
        supports=tuple(supports),
        resistances=tuple(resistances),
        invalidation_long=invalidation_long,
        invalidation_short=invalidation_short,
        measured_moves=tuple(measured_moves),
    )


def render_simple_market_features(features: SimpleMarketFeatures) -> str:
    """渲染紧凑的中文摘要，供阶段一 / 阶段二提示词使用。"""
    lines = [
        "## 程序结构辅助特征（简单预计算，客观参考；楔形/MTR 等复杂形态仍由你判断）",
        "",
        "### 区间位置",
    ]
    if features.range_high is not None and features.range_low is not None:
        lines.append(
            f"- 近{features.lookback_bars}棒包络：高 **{features.range_high}** / 低 **{features.range_low}**"
        )
        if features.range_width_atr is not None:
            lines.append(f"- 区间宽度：{features.range_width_atr}×ATR")
        if features.price_position is not None:
            zone_zh = {
                "upper_third": "上三分之一（偏阻力/上沿）",
                "middle_third": "中部（区间中部风险高）",
                "lower_third": "下三分之一（偏支撑/下沿）",
                "unknown": "未知",
            }.get(features.zone, features.zone)
            lines.append(
                f"- 收盘位置分位：**{features.price_position:.2f}** → {zone_zh}"
            )
        if features.dist_to_high_atr is not None and features.dist_to_low_atr is not None:
            lines.append(
                f"- 距上沿 {features.dist_to_high_atr}×ATR / 距下沿 {features.dist_to_low_atr}×ATR"
            )
    else:
        lines.append("- 数据不足，未计算区间包络")

    lines.extend(["", "### 重叠 / 铁丝网"])
    if features.overlap_mean_10 is not None:
        lines.append(f"- 近10棒平均重叠：{features.overlap_mean_10:.2f}")
    if features.doji_inside_ratio_10 is not None:
        lines.append(f"- 近10棒十字星+内包占比：{features.doji_inside_ratio_10:.0%}")
    lines.append(
        f"- 铁丝网分数：**{features.barbwire_score:.2f}**"
        f"（{'≥阈值，候选铁丝网/TTR' if features.barbwire_candidate else '未达铁丝网阈值'}）"
    )

    lines.extend(["", "### 波段结构"])
    lines.append(f"- 结构标签：**{features.swing_structure}**")
    if features.swings:
        swing_text = ", ".join(
            f"K{p.seq}{'高' if p.kind == 'high' else '低'}{p.price}" for p in features.swings[:6]
        )
        lines.append(f"- 最近枢轴（新→旧）：{swing_text}")
    if features.pullback_depth_atr is not None:
        bars_part = f"，持续{features.pullback_bars}棒" if features.pullback_bars else ""
        lines.append(f"- 自最近极点回撤：{features.pullback_depth_atr}×ATR{bars_part}")

    lines.extend(["", "### 突破 / 收回 / 回测"])
    if features.breakout_events:
        for ev in features.breakout_events[:4]:
            kind_zh = {
                "range_high": "区间上沿",
                "range_low": "区间下沿",
            }.get(ev.level_kind, ev.level_kind)
            event_zh = {
                "breakout": "突破",
                "failed": "突破失败/收回",
                "test": "突破回测",
            }.get(ev.event, ev.event)
            lines.append(
                f"- {event_zh} {kind_zh} **{ev.level_price}** @ K{ev.trigger_seq}"
                f"（{ev.bar_range}）{ev.note}"
            )
    else:
        lines.append("- 近窗口内无显著区间突破/收回事件")

    hc = features.hl_count
    lines.extend(["", "### H/L 计数触发（突破前一棒极点）"])
    lines.append(
        f"- 多头计数：**{hc.bull_count}**（候选 {hc.bull_candidate.upper()}）"
        + (f"，最近触发 K{hc.last_bull_trigger_seq}" if hc.last_bull_trigger_seq else "")
    )
    lines.append(
        f"- 空头计数：**{hc.bear_count}**（候选 {hc.bear_candidate.upper()}）"
        + (f"，最近触发 K{hc.last_bear_trigger_seq}" if hc.last_bear_trigger_seq else "")
    )
    lines.append(f"- 计数窗口：{hc.bar_range}")

    lines.extend(["", "### 结构价位候选"])
    if features.supports:
        lines.append(f"- 下方支撑（近→远）：{', '.join(str(p) for p in features.supports[:3])}")
    if features.resistances:
        lines.append(f"- 上方阻力（近→远）：{', '.join(str(p) for p in features.resistances[:3])}")
    if features.invalidation_long is not None:
        lines.append(f"- 做多结构失效参考：跌破 **{features.invalidation_long}**")
    if features.invalidation_short is not None:
        lines.append(f"- 做空结构失效参考：升破 **{features.invalidation_short}**")

    lines.extend(["", "### Measured Move 候选（算术投影，非下单依据）"])
    if features.measured_moves:
        for mm in features.measured_moves[:4]:
            lines.append(
                f"- {mm.kind}：高度 {mm.height} → 目标 **{mm.target_price}**"
                f"（{mm.reference}，{mm.bar_range}）"
            )
    else:
        lines.append("- 无足够结构计算 MM")

    lines.append("")
    lines.append(
        "说明：以上为程序客观计算；`detected_patterns` / 三价仍须你结合 playbook 综合判断。"
    )
    return "\n".join(lines)


def build_program_features_dict(frame: KlineFrame) -> dict[str, Any]:
    """为 stage1_json['program_features'] 生成紧凑的程序计算事实。"""
    features = compute_simple_market_features(frame)
    return {
        "barbwire_score": features.barbwire_score,
        "barbwire_candidate": features.barbwire_candidate,
        "overlap_mean_10": features.overlap_mean_10,
        "price_position": features.price_position,
        "zone": features.zone,
        "swing_structure": features.swing_structure,
    }


def inject_market_features_section(prompt: str, features_block: str) -> str:
    """在阶段一用户提示词中插入或替换程序市场特征块。"""
    if not features_block.strip():
        return prompt
    block = features_block.strip()
    if MARKET_FEATURES_SECTION_PREFIX in prompt:
        start = prompt.index(MARKET_FEATURES_SECTION_PREFIX)
        tail = prompt[start:]
        end_rel = len(tail)
        for marker in (
            "\n## 程序预填充",
            "\n请根据以上数据",
            "\n请基于上方完整",
            "\n请基于上一轮结论",
        ):
            if marker in tail:
                end_rel = min(end_rel, tail.index(marker))
        footer = "说明：以上为程序客观计算"
        if footer in tail:
            footer_end = tail.find("\n\n", tail.index(footer))
            if footer_end != -1:
                end_rel = min(end_rel, footer_end)
        return prompt[:start] + block + prompt[start + end_rel :]

    for anchor in (
        "## 程序预填充节点判断依据",
        "请根据以上数据，严格输出阶段一",
        "请基于上方完整K线数据",
        "请基于上一轮结论、新增K线和当前完整K线",
    ):
        if anchor in prompt:
            idx = prompt.index(anchor)
            return prompt[:idx].rstrip() + "\n\n" + block + "\n\n" + prompt[idx:]
    return prompt.rstrip() + "\n\n" + block + "\n"


def _dedupe_breakout_events(events: list[BreakoutEvent]) -> list[BreakoutEvent]:
    """仅保留近期事件；每个价格水平只保留一个最新事件。"""
    if not events:
        return []
    recent = [e for e in events if e.trigger_seq <= _RECENT_BREAKOUT_MAX_SEQ]
    pool = recent if recent else list(events[-_MAX_BREAKOUT_EVENTS:])
    by_level: dict[tuple[str, float], BreakoutEvent] = {}
    for event in pool:
        key = (event.level_kind, round(event.level_price, 6))
        prev = by_level.get(key)
        if prev is None:
            by_level[key] = event
            continue
        if event.trigger_seq < prev.trigger_seq:
            winner = event
        elif event.trigger_seq > prev.trigger_seq:
            winner = prev
        elif _EVENT_PRIORITY[event.event] < _EVENT_PRIORITY[prev.event]:
            winner = event
        else:
            winner = prev
        by_level[key] = winner
    return sorted(by_level.values(), key=lambda e: e.trigger_seq)[:_MAX_BREAKOUT_EVENTS]


def _empty_features(lookback: int) -> SimpleMarketFeatures:
    empty_hl = HLCountState(0, 0, None, None, "none", "none", "不适用")
    return SimpleMarketFeatures(
        lookback_bars=0,
        range_high=None,
        range_low=None,
        range_width_atr=None,
        price_position=None,
        zone="unknown",
        dist_to_high_atr=None,
        dist_to_low_atr=None,
        overlap_mean_10=None,
        doji_inside_ratio_10=None,
        barbwire_score=0.0,
        barbwire_candidate=False,
        swing_structure="insufficient",
        swings=(),
        pullback_depth_atr=None,
        pullback_bars=None,
        breakout_events=(),
        hl_count=empty_hl,
        supports=(),
        resistances=(),
        invalidation_long=None,
        invalidation_short=None,
        measured_moves=(),
    )


def _current_atr(frame: KlineFrame) -> float | None:
    atr14 = frame.indicators.atr14
    if not atr14:
        return None
    val = atr14[0]
    if math.isnan(val) or val <= 0:
        return None
    return float(val)


def _range_envelope(bars: tuple[KlineBar, ...]) -> tuple[float | None, float | None]:
    if not bars:
        return None, None
    return max(float(b.high) for b in bars), min(float(b.low) for b in bars)


def _zone_from_position(position: float) -> str:
    if position < 1 / 3:
        return "lower_third"
    if position > 2 / 3:
        return "upper_third"
    return "middle_third"


def _overlap_ratio(bar: KlineBar, prev: KlineBar) -> float | None:
    high = min(float(bar.high), float(prev.high))
    low = max(float(bar.low), float(prev.low))
    overlap = max(0.0, high - low)
    denominator = max(float(bar.high), float(prev.high)) - min(float(bar.low), float(prev.low))
    if denominator <= 0:
        return None
    return overlap / denominator


def _mean_overlap_ratio(bars: tuple[KlineBar, ...], window: int) -> float | None:
    if len(bars) < 2 or window < 2:
        return None
    vals: list[float] = []
    limit = min(window, len(bars) - 1)
    for idx in range(limit):
        ratio = _overlap_ratio(bars[idx], bars[idx + 1])
        if ratio is not None:
            vals.append(ratio)
    if not vals:
        return None
    return round(sum(vals) / len(vals), 3)


def _doji_inside_ratio(bars: tuple[KlineBar, ...], window: int) -> float | None:
    if not bars:
        return None
    sample = bars[:window]
    if not sample:
        return None
    count = 0
    for idx, bar in enumerate(sample):
        prev = sample[idx + 1] if idx + 1 < len(sample) else None
        full_range = max(float(bar.high), float(bar.low)) - min(float(bar.high), float(bar.low))
        body = abs(float(bar.close) - float(bar.open))
        is_doji = full_range > 0 and body / full_range <= 0.25
        is_inside = False
        if prev is not None:
            is_inside = float(bar.high) <= float(prev.high) and float(bar.low) >= float(prev.low)
        if is_doji or is_inside:
            count += 1
    return round(count / len(sample), 3)


def _barbwire_score(
    overlap_mean: float | None,
    doji_ratio: float | None,
    range_width_atr: float | None,
    bars: tuple[KlineBar, ...],
    atr: float | None,
) -> float:
    score = 0.0
    if overlap_mean is not None and overlap_mean >= _BARBWIRE_OVERLAP_THRESHOLD:
        score += 0.4
    if doji_ratio is not None and doji_ratio >= 0.4:
        score += 0.2
    if range_width_atr is not None and range_width_atr <= _BARBWIRE_WIDTH_ATR_MAX:
        score += 0.2
    if bars and atr and atr > 0:
        avg_bar = sum(float(b.high) - float(b.low) for b in bars[:_OVERLAP_WINDOW]) / min(
            len(bars), _OVERLAP_WINDOW
        )
        rh, rl = _range_envelope(bars[:_OVERLAP_WINDOW])
        if rh is not None and rl is not None and avg_bar > 0:
            if (rh - rl) / avg_bar < 0.3:
                score += 0.2
    return min(score, 1.0)


def _find_swings_with_seq(bars: tuple[KlineBar, ...]) -> list[SwingPivot]:
    """使用 1 根相邻 K 线的局部极点（与 structure_levels 对齐）。"""
    if len(bars) < 3:
        return []
    pivots: list[SwingPivot] = []
    for i in range(len(bars)):
        h = float(bars[i].high)
        lo = float(bars[i].low)
        is_high = True
        is_low = True
        if i > 0:
            if h <= float(bars[i - 1].high):
                is_high = False
            if lo >= float(bars[i - 1].low):
                is_low = False
        if i + 1 < len(bars):
            if h <= float(bars[i + 1].high):
                is_high = False
            if lo >= float(bars[i + 1].low):
                is_low = False
        if is_high:
            pivots.append(SwingPivot(seq=int(bars[i].seq), kind="high", price=round(h, 6)))
        if is_low:
            pivots.append(SwingPivot(seq=int(bars[i].seq), kind="low", price=round(lo, 6)))
    pivots.sort(key=lambda p: p.seq)
    return pivots


def _label_swing_structure(swings: list[SwingPivot]) -> str:
    highs = sorted([p for p in swings if p.kind == "high"], key=lambda p: p.seq)
    lows = sorted([p for p in swings if p.kind == "low"], key=lambda p: p.seq)
    if len(highs) < 2 or len(lows) < 2:
        return "insufficient"
    # seq 升序：索引 0 = 最新枢轴（K1 侧）。
    hh = highs[0].price > highs[1].price
    hl = lows[0].price > lows[1].price
    ll = lows[0].price < lows[1].price
    lh = highs[0].price < highs[1].price
    if hh and hl:
        return "HH+HL"
    if ll and lh:
        return "LL+LH"
    return "mixed"


def _pullback_metrics(
    bars: tuple[KlineBar, ...],
    swings: list[SwingPivot],
    atr: float | None,
    close: float,
) -> tuple[float | None, int | None]:
    if not swings or not atr or atr <= 0:
        return None, None
    highs = [p for p in swings if p.kind == "high"]
    lows = [p for p in swings if p.kind == "low"]
    if not highs and not lows:
        return None, None

    # 使用与当前收盘相对的最新极点。
    if highs and (not lows or highs[-1].seq >= lows[-1].seq):
        pivot_price = highs[-1].price
        depth = max(0.0, pivot_price - close)
    else:
        pivot_price = lows[-1].price
        depth = max(0.0, close - pivot_price)

    pivot_seq = highs[-1].seq if highs and (not lows or highs[-1].seq >= lows[-1].seq) else lows[-1].seq
    bars_since = max(0, pivot_seq - 1)
    return round(depth / atr, 3), bars_since


def _detect_breakout_events(
    bars: tuple[KlineBar, ...],
    range_high: float | None,
    range_low: float | None,
    *,
    tick: float,
    atr: float | None,
) -> list[BreakoutEvent]:
    if not bars:
        return []

    tolerance = (atr or 0.0) * _BREAKOUT_TEST_TOLERANCE_ATR
    if tick <= 0:
        tick = 0.01
    chronological = list(reversed(bars))
    events: list[BreakoutEvent] = []

    running_high: float | None = None
    running_low: float | None = None
    broke_up_seq: int | None = None
    broke_up_level: float | None = None
    broke_down_seq: int | None = None
    broke_down_level: float | None = None

    for bar in chronological:
        seq = int(bar.seq)
        close = float(bar.close)
        low = float(bar.low)
        high = float(bar.high)

        if running_high is not None and running_low is not None:
            if close > running_high + tick:
                broke_up_seq = seq
                broke_up_level = running_high
                events.append(
                    BreakoutEvent(
                        level_price=running_high,
                        level_kind="range_high",
                        event="breakout",
                        trigger_seq=seq,
                        bar_range=f"K{seq}",
                        note="收盘突破当时区间上沿",
                    )
                )
            elif broke_up_seq is not None and broke_up_level is not None:
                bars_after = broke_up_seq - seq if seq < broke_up_seq else 0
                if close < broke_up_level - tick and bars_after <= _BREAKOUT_RECLAIM_BARS:
                    events.append(
                        BreakoutEvent(
                            level_price=broke_up_level,
                            level_kind="range_high",
                            event="failed",
                            trigger_seq=seq,
                            bar_range=f"K{broke_up_seq}-K{seq}",
                            note="突破后收回区间内",
                        )
                    )
                    broke_up_seq = None
                    broke_up_level = None
                elif (
                    low <= broke_up_level + tolerance
                    and close > broke_up_level
                    and bars_after <= _BREAKOUT_RECLAIM_BARS
                ):
                    events.append(
                        BreakoutEvent(
                            level_price=broke_up_level,
                            level_kind="range_high",
                            event="test",
                            trigger_seq=seq,
                            bar_range=f"K{broke_up_seq}-K{seq}",
                            note="回测上沿后仍收上沿之上",
                        )
                    )

            if running_low is not None and close < running_low - tick:
                broke_down_seq = seq
                broke_down_level = running_low
                events.append(
                    BreakoutEvent(
                        level_price=running_low,
                        level_kind="range_low",
                        event="breakout",
                        trigger_seq=seq,
                        bar_range=f"K{seq}",
                        note="收盘跌破当时区间下沿",
                    )
                )
            elif broke_down_seq is not None and broke_down_level is not None:
                bars_after = broke_down_seq - seq if seq < broke_down_seq else 0
                if close > broke_down_level + tick and bars_after <= _BREAKOUT_RECLAIM_BARS:
                    events.append(
                        BreakoutEvent(
                            level_price=broke_down_level,
                            level_kind="range_low",
                            event="failed",
                            trigger_seq=seq,
                            bar_range=f"K{broke_down_seq}-K{seq}",
                            note="跌破后收回区间内",
                        )
                    )
                    broke_down_seq = None
                    broke_down_level = None
                elif (
                    high >= broke_down_level - tolerance
                    and close < broke_down_level
                    and bars_after <= _BREAKOUT_RECLAIM_BARS
                ):
                    events.append(
                        BreakoutEvent(
                            level_price=broke_down_level,
                            level_kind="range_low",
                            event="test",
                            trigger_seq=seq,
                            bar_range=f"K{broke_down_seq}-K{seq}",
                            note="回测下沿后仍收下沿之下",
                        )
                    )

        running_high = high if running_high is None else max(running_high, high)
        running_low = low if running_low is None else min(running_low, low)

    return events


def _compute_hl_count(bars: tuple[KlineBar, ...], atr: float | None) -> HLCountState:
    if len(bars) < 2:
        return HLCountState(0, 0, None, None, "none", "none", "不适用")

    bull = 0
    bear = 0
    last_bull: int | None = None
    last_bear: int | None = None
    newest = int(bars[0].seq)
    oldest = int(bars[-1].seq)
    reset_range = (atr or 0.0) * 1.2

    for older_idx in range(len(bars) - 1, 0, -1):
        newer = bars[older_idx - 1]
        older = bars[older_idx]
        newer_range = float(newer.high) - float(newer.low)

        if float(newer.high) > float(older.high):
            bull += 1
            last_bull = int(newer.seq)
        elif (
            float(newer.close) < float(older.low)
            and reset_range > 0
            and newer_range >= reset_range
        ):
            bull = 0

        if float(newer.low) < float(older.low):
            bear += 1
            last_bear = int(newer.seq)
        elif (
            float(newer.close) > float(older.high)
            and reset_range > 0
            and newer_range >= reset_range
        ):
            bear = 0

    def _tag(count: int, prefix: str) -> str:
        if count <= 0:
            return "none"
        if count == 1:
            return f"{prefix}1"
        if count == 2:
            return f"{prefix}2"
        return f"{prefix}3"

    return HLCountState(
        bull_count=bull,
        bear_count=bear,
        last_bull_trigger_seq=last_bull,
        last_bear_trigger_seq=last_bear,
        bull_candidate=_tag(bull, "h"),
        bear_candidate=_tag(bear, "l"),
        bar_range=f"K{newest}-K{oldest}" if newest != oldest else f"K{newest}",
    )


def _structure_levels(
    bars: tuple[KlineBar, ...],
    close: float,
    swings: list[SwingPivot],
) -> tuple[list[float], list[float]]:
    supports: list[float] = []
    resistances: list[float] = []
    seen: set[float] = set()
    for pivot in reversed(swings):
        key = round(pivot.price, 8)
        if key in seen:
            continue
        seen.add(key)
        if pivot.kind == "low" and pivot.price < close:
            supports.append(pivot.price)
        elif pivot.kind == "high" and pivot.price > close:
            resistances.append(pivot.price)
    supports.sort(reverse=True)
    resistances.sort()
    return supports[:3], resistances[:3]


def _measured_move_candidates(
    range_high: float | None,
    range_low: float | None,
    swings: list[SwingPivot],
    close: float,
    *,
    lookback: int,
) -> list[MeasuredMoveCandidate]:
    out: list[MeasuredMoveCandidate] = []
    if range_high is not None and range_low is not None and range_high > range_low:
        height = round(range_high - range_low, 6)
        out.append(
            MeasuredMoveCandidate(
                kind="range_up",
                reference="区间高度向上翻测",
                height=height,
                target_price=round(range_high + height, 6),
                bar_range=f"K{lookback}-K1",
            )
        )
        out.append(
            MeasuredMoveCandidate(
                kind="range_down",
                reference="区间高度向下翻测",
                height=height,
                target_price=round(range_low - height, 6),
                bar_range=f"K{lookback}-K1",
            )
        )

    highs = sorted([p for p in swings if p.kind == "high"], key=lambda p: p.seq)
    lows = sorted([p for p in swings if p.kind == "low"], key=lambda p: p.seq)
    if len(highs) >= 1 and len(lows) >= 1:
        leg_up = round(highs[0].price - lows[0].price, 6)
        if leg_up > 0:
            out.append(
                MeasuredMoveCandidate(
                    kind="leg_up",
                    reference=f"最近leg K{lows[0].seq}-K{highs[0].seq}",
                    height=leg_up,
                    target_price=round(close + leg_up, 6),
                    bar_range=f"K{highs[0].seq}-K{lows[0].seq}",
                )
            )
        leg_down = round(highs[0].price - lows[0].price, 6)
        if leg_down > 0:
            out.append(
                MeasuredMoveCandidate(
                    kind="leg_down",
                    reference=f"最近leg K{highs[0].seq}-K{lows[0].seq}",
                    height=leg_down,
                    target_price=round(close - leg_down, 6),
                    bar_range=f"K{highs[0].seq}-K{lows[0].seq}",
                )
            )
    return out
