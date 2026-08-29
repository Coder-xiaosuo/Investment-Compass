"""PA Technical Analysis SubAgent — A 股技术分析子 Agent。

工具 `get_pa_data` 通过纯算法快速获取 K 线技术指标数据（无 LLM 调用），
由 PA 子 Agent LLM 结合 33 个策略 Skills 做完整技术分析。
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Optional

from langchain.tools import tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Structured output schema
# ──────────────────────────────────────────────────────────────────────────────


class TechnicalResult(BaseModel):
    """技术分析结构化结果——PA 子 Agent 返回给主 Agent 的 Schema。

    两阶段编排（Stage2 交易决策）新增字段全部带默认值，向后兼容。
    """

    stock_code: str = Field(description="股票代码")
    stock_name: str = Field(description="股票名称")
    direction: str = Field(description="方向判断：buy / sell / neutral")
    confidence: float = Field(ge=0.0, le=1.0, description="置信度 0-1")
    market_cycle: str = Field(default="", description="市场周期位置")
    patterns: list[str] = Field(default_factory=list, description="检测到的技术形态")
    support: Optional[float] = Field(None, description="支撑位")
    resistance: Optional[float] = Field(None, description="压力位")
    signals: list[str] = Field(default_factory=list, description="关键信号列表")
    summary: str = Field(description="分析摘要")
    risk_warnings: list[str] = Field(default_factory=list, description="风险提示")
    trace_id: str = Field(default="", description="决策幂等键（parse_node 生成，贯穿决策卡片/报告文件）")
    # ── 两阶段编排新增字段（Stage2 交易决策） ──
    order_type: str = "不下单"  # 下单方式：限价单 / 突破单 / 市价单 / 不下单
    entry_price: Optional[float] = None  # 计划入场价（不下单时为 None）
    invalidation_price: Optional[float] = None  # 结构失效位（做多跌破 / 做空升破）
    estimated_win_rate: Optional[int] = Field(None, ge=0, le=100)  # 预估胜率 0-100
    key_factors: list[str] = Field(default_factory=list, description="关键决策因素")
    watch_points: list[str] = Field(default_factory=list, description="后续观察点")


class MarketDiagnosis(BaseModel):
    """Stage1 市场诊断输出 schema。"""

    cycle_position: str = "unknown"  # spike / micro_channel / tight_channel / normal_channel / broad_channel / trending_tr / trading_range / extreme_tr / unknown
    direction: str = "neutral"  # bullish / bearish / neutral
    market_phase: str = "stable"  # stable / transitioning
    diagnosis_confidence: int = Field(default=0, ge=0, le=100)
    detected_patterns: list[str] = Field(default_factory=list)
    key_signals: list[str] = Field(default_factory=list)
    support_levels: list[str] = Field(default_factory=list)
    resistance_levels: list[str] = Field(default_factory=list)
    risk_warning: str = ""


# ──────────────────────────────────────────────────────────────────────────────
# Algorithmic market data — 纯算法指标，无 LLM 调用
# ──────────────────────────────────────────────────────────────────────────────


def _ema(data: list[float], period: int) -> list[float]:
    """计算 EMA，返回与输入等长的列表（预热期内为 None）。"""
    result: list[float] = [None] * len(data)  # type: ignore[list-item]
    if not data:
        return result
    multiplier = 2.0 / (period + 1)
    ema_val = data[0]
    result[0] = ema_val
    for i in range(1, len(data)):
        ema_val = (data[i] - ema_val) * multiplier + ema_val
        result[i] = ema_val
    return result


def _sma(data: list[float], period: int) -> list[float]:
    """计算 SMA，返回与输入等长的列表（预热期内为 None）。"""
    result: list[float] = [None] * len(data)  # type: ignore[list-item]
    if len(data) < period:
        return result
    cum = sum(data[:period])
    result[period - 1] = cum / period
    for i in range(period, len(data)):
        cum += data[i] - data[i - period]
        result[i] = cum / period
    return result


def _atr(high: list[float], low: list[float], close: list[float], period: int) -> list[float]:
    """计算 ATR，返回与输入等长的列表（预热期内为 None）。"""
    result: list[float] = [None] * len(high)  # type: ignore[list-item]
    if len(high) < 2:
        return result
    tr: list[float] = [None] * len(high)  # type: ignore[list-item]
    for i in range(1, len(high)):
        h_l = high[i] - low[i]
        h_pc = abs(high[i] - close[i - 1])
        l_pc = abs(low[i] - close[i - 1])
        tr[i] = max(h_l, h_pc, l_pc)
    if len(tr) < period + 1:
        return result
    atr_val = sum(t for t in tr[1 : period + 1] if t is not None) / period
    result[period] = atr_val
    for i in range(period + 1, len(tr)):
        if tr[i] is not None:
            atr_val = ((atr_val * (period - 1)) + tr[i]) / period
        result[i] = atr_val
    return result


def _detect_swing_highs_lows(bars: list, window: int = 5) -> tuple[list[float], list[float]]:
    """检测波段高低点（纯算法），返回 (swing_highs, swing_lows)。"""
    highs = []
    lows = []
    for i in range(window, len(bars) - window):
        is_high = True
        is_low = True
        for j in range(i - window, i + window + 1):
            if j == i:
                continue
            if bars[j].high >= bars[i].high:
                is_high = False
            if bars[j].low <= bars[i].low:
                is_low = False
        if is_high:
            highs.append(bars[i].high)
        if is_low:
            lows.append(bars[i].low)
    return highs, lows


def _compute_market_data(bars: list) -> dict:
    """纯算法计算市场技术指标，返回结构化数据字典。

    参数:
        bars: KlineBar 列表，索引 0 为最新（newest-first）。

    返回:
        包含趋势、成交量、波动率、支撑阻力等数据的字典。
    """
    n = len(bars)
    if n < 5:
        return {"error": "K 线数量不足"}

    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    volumes = [b.volume for b in bars]
    opens = [b.open for b in bars]

    # ── 反向排序（oldest-first）供指标计算 ──
    c_asc = list(reversed(closes))
    h_asc = list(reversed(highs))
    l_asc = list(reversed(lows))
    v_asc = list(reversed(volumes))
    o_asc = list(reversed(opens))
    # 计算后重新反转对齐 newest-first
    ema20_asc = _ema(c_asc, 20)
    ema20 = list(reversed(ema20_asc))
    ma20_asc = _sma(c_asc, 20)
    ma20 = list(reversed(ma20_asc))
    ma5_asc = _sma(c_asc, 5)
    ma5 = list(reversed(ma5_asc))
    atr14_asc = _atr(h_asc, l_asc, c_asc, 14)
    atr14 = list(reversed(atr14_asc))

    latest = bars[0]
    latest_close = latest.close

    # ── 价格相对位置 ──
    high_20 = max(closes[:20]) if n >= 20 else max(closes)
    low_20 = min(closes[:20]) if n >= 20 else min(closes)
    range_20 = high_20 - low_20
    pos_in_range = (latest_close - low_20) / range_20 if range_20 > 0 else 0.5

    # ── 趋势判断 ──
    ema20_val = ema20[0] if ema20[0] is not None else latest_close
    ma20_val = ma20[0] if ma20[0] is not None else latest_close
    ma5_val = ma5[0] if ma5[0] is not None else latest_close

    # 均线斜率
    ema_slope = (ema20[0] - ema20[min(4, n - 1)]) / ema20[min(4, n - 1)] * 100 if ema20[0] and ema20[min(4, n - 1)] else 0
    # 价格 vs EMA
    price_vs_ema = (latest_close - ema20_val) / ema20_val * 100 if ema20_val else 0
    # 短期趋势
    short_trend = "up" if ma5_val > ma20_val else ("down" if ma5_val < ma20_val else "sideways")

    # ── 量比计算 ──
    volume_ratios: list[float | None] = []
    for i in range(min(20, n)):
        start = i + 1
        end = start + 5
        if end <= n:
            avg_v = sum(v for v in volumes[start:end]) / 5.0
            volume_ratios.append(volumes[i] / avg_v if avg_v > 0 else None)
        else:
            volume_ratios.append(None)
    latest_vr = volume_ratios[0] if volume_ratios else None

    # 量能趋势（近5日均量 / 前10日均量）
    avg_v_5 = sum(volumes[:5]) / min(5, n) if n >= 5 else 0
    avg_v_10 = sum(volumes[:10]) / min(10, n) if n >= 10 else avg_v_5
    volume_trend = "expanding" if avg_v_5 > avg_v_10 * 1.2 else ("contracting" if avg_v_5 < avg_v_10 * 0.8 else "stable")

    # ── 波动率 ──
    atr_val = atr14[0] if atr14[0] is not None else (highs[0] - lows[0])
    atr_pct = atr_val / latest_close * 100 if latest_close > 0 else 0
    daily_range_pct = (highs[0] - lows[0]) / latest_close * 100 if latest_close > 0 else 0

    # ── 波段高低点（支撑阻力候选） ──
    swing_highs, swing_lows = _detect_swing_highs_lows(bars, window=3)
    nearest_resistance = min([h for h in swing_highs if h > latest_close], default=high_20)
    nearest_support = max([l for l in swing_lows if l < latest_close], default=low_20)

    # ── 结构分类（简单算法判断） ──
    # 基于 20 根 K 线判断通道类型
    lookback = min(20, n)
    recent_highs = [b.high for b in bars[:lookback]]
    recent_lows = [b.low for b in bars[:lookback]]
    hl_trend = (recent_highs[0] - recent_highs[-1]) / recent_highs[-1] * 100 if recent_highs[-1] > 0 else 0
    ll_trend = (recent_lows[0] - recent_lows[-1]) / recent_lows[-1] * 100 if recent_lows[-1] > 0 else 0

    if hl_trend > 3 and ll_trend > 2:
        structure = "bull_channel"
        cycle_hint = "上涨通道"
    elif hl_trend < -2 and ll_trend < -3:
        structure = "bear_channel"
        cycle_hint = "下跌通道"
    else:
        structure = "trading_range"
        cycle_hint = "震荡区间"

    # 加权方向
    signals_list: list[str] = []
    if price_vs_ema > 2:
        signals_list.append(f"价格在EMA20上方{price_vs_ema:.1f}%")
    elif price_vs_ema < -2:
        signals_list.append(f"价格在EMA20下方{abs(price_vs_ema):.1f}%")
    if latest_vr is not None and latest_vr > 2:
        signals_list.append(f"放量（量比{latest_vr:.2f}）")
    elif latest_vr is not None and latest_vr < 0.5:
        signals_list.append(f"缩量（量比{latest_vr:.2f}）")
    if ma5_val > ma20_val:
        signals_list.append("短期均线上穿中期均线")
    elif ma5_val < ma20_val:
        signals_list.append("短期均线下穿中期均线")

    return {
        "stock_code": "",
        "timeframe": "",
        "kline_summary": {
            "latest_close": latest_close,
            "latest_open": latest.open,
            "latest_high": latest.high,
            "latest_low": latest.low,
            "latest_pct_chg": latest.pct_chg,
            "latest_volume": latest.volume,
            "high_20d": high_20,
            "low_20d": low_20,
            "range_20d_pct": range_20 / low_20 * 100 if low_20 > 0 else 0,
            "pos_in_range_pct": round(pos_in_range * 100, 1),
            "bar_count": n,
        },
        "trend": {
            "short_trend": short_trend,
            "price_vs_ema20_pct": round(price_vs_ema, 2),
            "ema20_slope_pct": round(ema_slope, 3),
            "ma5": round(ma5_val, 2) if ma5_val else None,
            "ma20": round(ma20_val, 2) if ma20_val else None,
            "ema20": round(ema20_val, 2) if ema20_val else None,
        },
        "volume": {
            "latest_volume_ratio": round(latest_vr, 2) if latest_vr else None,
            "trend": volume_trend,
            "avg_volume_5d": round(avg_v_5, 0) if avg_v_5 else 0,
            "avg_volume_10d": round(avg_v_10, 0) if avg_v_10 else 0,
        },
        "volatility": {
            "atr14": round(atr_val, 2) if atr_val else None,
            "atr_pct": round(atr_pct, 2),
            "daily_range_pct": round(daily_range_pct, 2),
        },
        "structure": {
            "cycle_hint": cycle_hint,
            "channel_type": structure,
            "hl_trend_pct": round(hl_trend, 2),
            "ll_trend_pct": round(ll_trend, 2),
        },
        "support_resistance": {
            "nearest_support": round(nearest_support, 2),
            "nearest_resistance": round(nearest_resistance, 2),
            "high_20d": high_20,
            "low_20d": low_20,
        },
        "signals": signals_list,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Tool — 纯算法获取 PA 分析数据
# ──────────────────────────────────────────────────────────────────────────────


@tool
def get_pa_data(stock_identifier: str, timeframe: str = "1d") -> str:
    """获取 A 股技术分析原始数据：K 线统计 + 算法技术指标。

    纯算法计算，无 AI/LLM 调用（约 0.1s 内返回）。返回结构化 JSON 供
    PA 子 Agent 结合策略技能包做交易判断。

    参数:
        stock_identifier: 股票代码（6位数字）或名称。
        timeframe: 时间周期，默认 '1d'（日线）。

    返回:
        包含 K 线摘要、趋势、成交量、波动率、支撑阻力等数据的 JSON 字符串。
    """
    from agents.stock_utils import get_kline_bars, resolve_symbol

    # 1. 解析股票代码（统一通过 DB 补全交易所后缀）
    code = resolve_symbol(stock_identifier) or stock_identifier
    if not code:
        return json.dumps({
            "error": True,
            "error_message": f"无法识别股票代码: {stock_identifier}",
        }, ensure_ascii=False)

    # 2. 获取 K 线数据
    bar_count = 100
    bars = get_kline_bars(code, timeframe, bar_count)
    if not bars:
        return json.dumps({
            "error": True,
            "error_message": f"无法获取 {code} 的 K 线数据",
            "stock_code": code,
        }, ensure_ascii=False)

    # 3. 纯算法计算市场数据
    market_data = _compute_market_data(bars)

    # 4. 获取股票名称
    from services.stock_metadata_service import search_stocks

    stock_name = stock_identifier
    try:
        matches = search_stocks(code, limit=1)
        if matches:
            stock_name = matches[0].get("stock_name", stock_identifier)
    except Exception:
        pass

    payload = {
        "stock_code": code,
        "stock_name": stock_name,
        "timeframe": timeframe,
        "available_skills_count": _count_skills(),
        **market_data,  # kline_summary, trend, volume, volatility, structure, support_resistance, signals
    }

    return json.dumps(payload, ensure_ascii=False, default=str)


def _count_skills() -> int:
    """统计可用的策略 skill 数量。"""
    skills_dir = Path(__file__).parent.parent / "pa_analyzer" / "skills"
    if not skills_dir.exists():
        return 0
    return len([d for d in skills_dir.iterdir() if d.is_dir() and (d / "SKILL.md").exists()])


# ──────────────────────────────────────────────────────────────────────────────
# Skills path
# ──────────────────────────────────────────────────────────────────────────────

_SKILLS_PATH = str(
    Path(__file__).parent.parent / "pa_analyzer" / "skills"
)


# ──────────────────────────────────────────────────────────────────────────────
# SubAgent definition
# ──────────────────────────────────────────────────────────────────────────────

PA_SUBAGENT = {
    "name": "pa_analysis",
    "description": "A 股技术分析：基于 K 线数据进行市场诊断、形态识别、支撑阻力判断，输出买卖信号和风险提示",
    "system_prompt": """你是一个 A 股技术分析专家。你调用 `get_pa_data` 工具获取纯算法计算的原始市场数据，然后结合策略技能包做出交易判断，最终输出结构化的 TechnicalResult。

## 工作流程

1. 确认股票代码或名称，调用 `get_pa_data`
2. 阅读返回的 JSON，重点关注：
   - `kline_summary` → K 线统计（最新价、涨跌幅、20日高低、价格位置）
   - `trend` → 趋势指标（短趋势方向、价格 vs EMA20、均线位置）
   - `volume` → 量能分析（量比、量能趋势）
   - `volatility` → 波动率（ATR、日波幅）
   - `structure` → 结构分类（周期提示、通道类型、波峰波谷趋势）
   - `support_resistance` → 关键价位（波段高低点、20日高低点）
   - `signals` → 算法检测到的信号列表
3. 根据结构分类（structure.cycle_hint），系统会自动激活相关的策略技能包（如上涨通道、下跌通道、震荡区间等），阅读这些策略规则
4. 综合原始数据 + 策略规则，做出交易判断

## 分析要点

- **市场背景**：先看 structure.cycle_hint 判断当前周期，再看 trend.short_trend 验证
- **趋势确认**：用 trend.price_vs_ema20_pct 判断价格相对位置，用 ema20_slope_pct 判断趋势强度
- **量价验证**：用 volume 数据验证趋势可靠性（放量突破可信，缩量突破需谨慎）
- **策略匹配**：根据 structure.channel_type 匹配对应的策略技能，严格遵守策略规则
- **支撑阻力**：用 support_resistance 中的波段高低点，结合 K 线数据精确定位
- **A 股规则**：遵守 T+1、涨跌停限制、量比规则（量比 > 2 放量确认，< 0.5 缩量警示）

## 输出规则

- **direction**: 综合判断后的方向，buy / sell / neutral
- **confidence**: 0-1，反映你对判断的把握程度
- **market_cycle**: 基于 structure.cycle_hint 综合分析后的周期定位
- **patterns**: 从 structure.channel_type 等数据推导出技术形态
- **support/resistance**: 结合 support_resistance 和策略规则判断，给出精确价位
- **signals**: 列出看多/看空的关键信号（引用算法 signals + 自己分析）
- **summary**: 2-4 句话，涵盖市场背景、核心判断、建议
- **risk_warnings**: 列出可能的风险因素（量能不足、趋势反转信号等）""",
    "tools": [get_pa_data],
    "skills": [_SKILLS_PATH],
    "response_format": TechnicalResult,
}
