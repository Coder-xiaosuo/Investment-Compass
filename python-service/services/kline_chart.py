"""K 线截图生成模块 — 基于 matplotlib 绘制 A 股日线蜡烛图。

使用 Agg 后端（无 GUI），渲染结果写入内存 buffer 并返回 PNG 字节串，
供飞书交互卡片图片上传（FeishuNotifier.upload_image）使用。

绘制约定（A 股习惯）：
  - 红涨绿跌：close >= open 为阳线（红色），否则阴线（绿色）
  - 主图：蜡烛图 + MA 均线（默认 MA5，橙色）
  - 附图：成交量柱状图（按涨跌与主图同色）
  - 支撑/阻力：绿色 / 红色水平虚线，带价位标签

主要函数：
    render_kline_chart(bars, symbol, stock_name, support, resistance,
                       ma_window, max_bars) -> bytes
"""
from __future__ import annotations

import io
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── 中文字体候选（按可用性优先选择）───────────────────────────────────────────
# macOS 常见中文字体；命中第一个即使用。找不到时回退 matplotlib 默认
# 字体（中文可能显示为方块，但代码不崩）。
_CHINESE_FONT_CANDIDATES = [
    "PingFang SC",
    "Arial Unicode MS",
    "Hiragino Sans GB",
    "Heiti SC",
    "Songti SC",
    "STHeiti",
    "Microsoft YaHei",
    "SimHei",
    "Noto Sans CJK SC",
]

# 进程内缓存已解析的中文字体名（None 表示未找到）
_resolved_font: str | None | bool = False


def _resolve_chinese_font() -> str | None:
    """从 matplotlib 已安装字体中挑选中文字体；找不到返回 None。

    结果缓存到模块级变量，避免重复扫描字体列表。
    """
    global _resolved_font
    if _resolved_font is not False:
        return _resolved_font

    font_name: str | None = None
    try:
        import matplotlib.font_manager as fm

        installed = {f.name for f in fm.fontManager.ttflist}
        for name in _CHINESE_FONT_CANDIDATES:
            if name in installed:
                font_name = name
                break
    except Exception as exc:
        logger.warning("扫描 matplotlib 中文字体失败: %s", exc)

    _resolved_font = font_name
    if font_name is None:
        logger.warning(
            "未找到可用的中文字体，图表中文可能显示异常（已回退默认字体）"
        )
    else:
        logger.debug("K 线图表使用中文字体: %s", font_name)
    return font_name


def _apply_chinese_font(plt: Any) -> None:
    """配置 matplotlib 全局中文字体（含负号显示修正）。"""
    font_name = _resolve_chinese_font()
    if font_name:
        plt.rcParams["font.sans-serif"] = [font_name]
    # 关闭 Unicode 负号，避免中文负号显示为方块
    plt.rcParams["axes.unicode_minus"] = False


def _sma(values: list[float], window: int) -> list[float | None]:
    """简单移动平均（窗口内不足时前置位置为 None），与输入等长。"""
    result: list[float | None] = [None] * len(values)
    if window <= 0 or len(values) < window:
        return result
    cum = sum(values[:window])
    result[window - 1] = cum / window
    for i in range(window, len(values)):
        cum += values[i] - values[i - window]
        result[i] = cum / window
    return result


def _to_float(value: Any, field: str) -> float:
    """安全转 float，供 bars 字段取值。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"K 线字段 {field} 不是合法数值: {value!r}")


def render_kline_chart(
    bars: list[dict],
    symbol: str,
    stock_name: str = "",
    support: float | None = None,
    resistance: float | None = None,
    ma_window: int = 5,
    max_bars: int = 60,
) -> bytes:
    """绘制日线蜡烛图并返回 PNG 字节（内存 buffer，Agg 后端）。

    Args:
        bars: 日线 dict 列表，每项含 trade_date/open/high/low/close/volume，
              按时间升序（旧 → 新）。
        symbol: 股票代码（如 600519）。
        stock_name: 股票名称（可选，用于标题）。
        support: 支撑价位（绿色虚线），None 则不画。
        resistance: 阻力价位（红色虚线），None 则不画。
        ma_window: 均线窗口（默认 5 → MA5，橙色）。
        max_bars: 最多绘制的 K 线根数（取最近 N 根）。

    Returns:
        PNG 图片字节。

    Raises:
        ValueError: bars 为空或字段不合法（由调用方决定如何兜底）。
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    if not bars:
        raise ValueError("K 线数据为空，无法绘图")

    # 取最近 max_bars 根（输入升序 → 取尾部）
    if max_bars > 0 and len(bars) > max_bars:
        bars = bars[-max_bars:]

    dates = [str(b.get("trade_date", "")) for b in bars]
    opens = [_to_float(b.get("open"), "open") for b in bars]
    highs = [_to_float(b.get("high"), "high") for b in bars]
    lows = [_to_float(b.get("low"), "low") for b in bars]
    closes = [_to_float(b.get("close"), "close") for b in bars]
    volumes = [_to_float(b.get("volume", 0), "volume") for b in bars]

    _apply_chinese_font(plt)

    n = len(bars)
    x = list(range(n))
    width = 0.6  # 蜡烛实体宽度（x 单位）

    # ── 画布：主图（价格）+ 附图（成交量），共享 x 轴 ──
    fig, (ax_price, ax_vol) = plt.subplots(
        2, 1, sharex=True, figsize=(12, 7),
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0.05},
    )
    fig.patch.set_facecolor("white")

    # ── 主图：蜡烛图（红涨绿跌） ──
    for i in range(n):
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        color = "#e6432e" if c >= o else "#0aa05a"  # A 股：红涨绿跌
        # 影线
        ax_price.vlines(i, l, h, color=color, linewidth=1.0)
        # 实体（十字星时画横线兜底）
        if abs(c - o) < 1e-9:
            ax_price.plot([i - width / 2, i + width / 2], [c, c],
                          color=color, linewidth=1.2)
        else:
            ax_price.add_patch(Rectangle(
                (i - width / 2, min(o, c)), width, abs(c - o),
                facecolor=color, edgecolor=color, linewidth=0.8,
            ))

    # ── 主图：MA 均线（橙色） ──
    ma = _sma(closes, ma_window)
    ma_x = [i for i, v in enumerate(ma) if v is not None]
    ma_y = [v for v in ma if v is not None]  # type: ignore[misc]
    if ma_x:
        ax_price.plot(ma_x, ma_y, color="#f5a623", linewidth=1.4,
                      label=f"MA{ma_window}")

    # ── 主图：支撑 / 阻力水平虚线 ──
    if support is not None:
        ax_price.axhline(support, color="#0aa05a", linestyle="--", linewidth=1.2)
        ax_price.text(0, support, f" 支撑 {support:.2f}", color="#0aa05a",
                      fontsize=9, va="bottom")
    if resistance is not None:
        ax_price.axhline(resistance, color="#e6432e", linestyle="--", linewidth=1.2)
        ax_price.text(0, resistance, f" 阻力 {resistance:.2f}", color="#e6432e",
                      fontsize=9, va="top")

    ax_price.set_title(f"{stock_name}({symbol}) 日线", fontsize=14)
    ax_price.legend(loc="best", fontsize=9)
    ax_price.grid(axis="y", linestyle=":", alpha=0.4)
    ax_price.set_ylabel("价格")

    # ── 附图：成交量柱状图（与主图涨跌同色） ──
    vol_colors = [
        "#e6432e" if closes[i] >= opens[i] else "#0aa05a" for i in range(n)
    ]
    ax_vol.bar(x, volumes, width=width, color=vol_colors, align="center")
    ax_vol.grid(axis="y", linestyle=":", alpha=0.4)
    ax_vol.set_ylabel("成交量")

    # ── x 轴日期刻度格式化（按可见根数自适应） ──
    ax_vol.set_xlim(-1, n)
    tick_step = max(1, n // 8)  # 最多约 9 个刻度
    tick_positions = list(range(0, n, tick_step))
    if tick_positions and tick_positions[-1] != n - 1:
        tick_positions.append(n - 1)
    ax_vol.set_xticks(tick_positions)
    ax_vol.set_xticklabels([dates[i] for i in tick_positions],
                           rotation=45, ha="right", fontsize=9)

    # ── 输出 PNG 字节（内存 buffer） ──
    buf = io.BytesIO()
    try:
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        return buf.getvalue()
    finally:
        buf.close()
        plt.close(fig)
