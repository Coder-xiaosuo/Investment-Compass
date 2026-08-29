import { useEffect, useRef, useCallback, useState, useMemo } from 'react'
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type HistogramData,
  type LineData,
} from 'lightweight-charts'
import type { KlineBar, MAConfig } from '@/types/kline'
import { cn } from '@/lib/utils'

interface KlineChartProps {
  data: KlineBar[]
  className?: string
}

/** 均线配置 */
const DEFAULT_MAS: MAConfig[] = [
  { period: 5, color: '#f59e0b', label: 'MA5' },
  { period: 10, color: '#2e86ab', label: 'MA10' },
  { period: 20, color: '#8b5cf6', label: 'MA20' },
]

function calcMA(bars: CandlestickData[], period: number): LineData[] {
  const result: LineData[] = []
  for (let i = period - 1; i < bars.length; i++) {
    let sum = 0
    for (let j = i - period + 1; j <= i; j++) {
      sum += bars[j].close
    }
    result.push({ time: bars[i].time, value: Number((sum / period).toFixed(2)) })
  }
  return result
}

/** 'YYYY-MM-DD' → BusinessDay { year, month, day } */
function toBusinessDay(dateStr: string): { year: number; month: number; day: number } | null {
  if (!dateStr || typeof dateStr !== 'string') return null
  const parts = dateStr.split('-')
  if (parts.length !== 3) return null
  const [y, m, d] = parts.map(Number)
  if (isNaN(y) || isNaN(m) || isNaN(d)) return null
  return { year: y, month: m, day: d }
}

function toCandleData(bars: KlineBar[]): CandlestickData[] {
  return bars
    .filter((b) => b && typeof b.trade_date === 'string')
    .map((b) => ({
      time: toBusinessDay(b.trade_date)!,
      open: b.open,
      high: b.high,
      low: b.low,
      close: b.close,
    }))
}

function toVolumeData(bars: KlineBar[]): HistogramData[] {
  return bars
    .filter((b) => b && typeof b.trade_date === 'string')
    .map((b) => {
      const isUp = b.close >= b.open
      return {
        time: toBusinessDay(b.trade_date)!,
        value: b.volume,
        color: isUp ? 'rgba(22, 163, 74, 0.4)' : 'rgba(220, 38, 38, 0.4)',
      }
    })
}

export function KlineChart({ data, className }: KlineChartProps) {
  const chartWrapperRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const volumeChartRef = useRef<IChartApi | null>(null)
  const volContainerRef = useRef<HTMLDivElement | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const maSeriesRef = useRef<ISeriesApi<'Line'>[]>([])
  const [activeMas, setActiveMas] = useState<MAConfig[]>(DEFAULT_MAS)
  const [_hoveredData, setHoveredData] = useState<CandlestickData | null>(null)
  const candleDataRef = useRef<CandlestickData[]>([])

  interface TooltipState {
    x: number
    y: number
    bar: KlineBar | null
  }
  const [tooltip, setTooltip] = useState<TooltipState>({ x: 0, y: 0, bar: null })
  const dataRef = useRef<KlineBar[]>([])
  const [_selectedIndex, setSelectedIndex] = useState<number>(-1)

  const candleData = useMemo(() => toCandleData(data), [data])
  const volumeData = useMemo(() => toVolumeData(data), [data])
  candleDataRef.current = candleData
  dataRef.current = data

  // 创建图表实例
  useEffect(() => {
    if (!containerRef.current || !chartWrapperRef.current) return

    const container = containerRef.current
    const availableHeight = container.clientHeight
    const chartWidth = container.clientWidth
    const topHeight = Math.floor(availableHeight * 0.75)
    const bottomHeight = availableHeight - topHeight - 4

    // ── 主图表 ──
    const chart = createChart(container, {
      layout: {
        background: { color: '#ffffff' },
        textColor: '#5B6170',
        fontSize: 10,
        fontFamily: "'Inter', -apple-system, sans-serif",
      },
      grid: {
        vertLines: { color: '#f0f2f5', style: 1 },
        horzLines: { color: '#f0f2f5', style: 1 },
      },
      width: chartWidth,
      height: topHeight,
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: '#e2e5ea', scaleMargins: { top: 0.08, bottom: 0.06 } },
      timeScale: {
        borderColor: '#e2e5ea',
        timeVisible: false,
      },
      handleScroll: true,
      handleScale: true,
    })
    chartRef.current = chart

    chart.subscribeCrosshairMove((param) => {
      if (param.time && param.point) {
        // 找到 candleData 中的匹配项
        const found = candleDataRef.current.find((d) => {
          if (typeof d.time === 'object' && typeof param.time === 'object') {
            const t = d.time as { year: number; month: number; day: number }
            const p = param.time as { year: number; month: number; day: number }
            return t.year === p.year && t.month === p.month && t.day === p.day
          }
          return false
        })
        setHoveredData(found || null)

        // 找到原始 KlineBar 数据（用于 tooltip 显示日期/涨跌幅/成交量）
        let matchedBar: KlineBar | null = null
        if (typeof param.time === 'object') {
          const p = param.time as { year: number; month: number; day: number }
          const dateStr = `${p.year}-${String(p.month).padStart(2, '0')}-${String(p.day).padStart(2, '0')}`
          matchedBar = dataRef.current.find(b => b.trade_date === dateStr) || null
        }
        setTooltip({
          x: param.point.x,
          y: param.point.y,
          bar: matchedBar,
        })
      } else {
        setHoveredData(null)
        setTooltip({ x: 0, y: 0, bar: null })
      }
    })

    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width } = entry.contentRect
        chart.applyOptions({ width })
        if (volumeChartRef.current) {
          volumeChartRef.current.applyOptions({ width })
        }
      }
    })
    ro.observe(container)

    // ── 成交量图表 ──
    const vcEl = document.createElement('div')
    vcEl.style.height = `${bottomHeight}px`
    vcEl.style.width = '100%'
    container.appendChild(vcEl)
    volContainerRef.current = vcEl

    const volChart = createChart(vcEl, {
      layout: {
        background: { color: '#ffffff' },
        textColor: '#5B6170',
        fontSize: 10,
      },
      grid: {
        vertLines: { color: '#f0f2f5', style: 1 },
        horzLines: { color: '#f0f2f5', style: 1 },
      },
      width: chartWidth,
      height: bottomHeight,
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: {
        borderColor: '#e2e5ea',
        scaleMargins: { top: 0.08, bottom: 0.15 },
        visible: false,
      },
      timeScale: {
        borderColor: '#e2e5ea',
        visible: false,
      },
      handleScroll: true,
      handleScale: true,
    })
    volumeChartRef.current = volChart

    // 时间轴同步（成交量图数据就绪后才同步）
    chart.timeScale().subscribeVisibleTimeRangeChange(() => {
      if (!volumeSeriesRef.current) return
      const range = chart.timeScale().getVisibleRange()
      if (range) {
        volChart.timeScale().setVisibleRange(range)
      }
    })

    return () => {
      ro.disconnect()
      chart.remove()
      volChart.remove()
      if (volContainerRef.current && container.contains(volContainerRef.current)) {
        container.removeChild(volContainerRef.current)
      }
      chartRef.current = null
      volumeChartRef.current = null
      volContainerRef.current = null
      candleSeriesRef.current = null
      volumeSeriesRef.current = null
      maSeriesRef.current = []
    }
  }, [])

  // 更新蜡烛图 + 均线
  useEffect(() => {
    if (!chartRef.current) return
    const chart = chartRef.current

    // 清除旧 series
    if (candleSeriesRef.current) {
      chart.removeSeries(candleSeriesRef.current)
    }
    maSeriesRef.current.forEach((s) => chart.removeSeries(s))
    maSeriesRef.current = []

    // 蜡烛图
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#16a34a',
      downColor: '#dc2626',
      borderUpColor: '#16a34a',
      borderDownColor: '#dc2626',
      wickUpColor: '#16a34a',
      wickDownColor: '#dc2626',
    })
    candleSeries.setData(candleData)
    candleSeriesRef.current = candleSeries

    // 均线
    activeMas.forEach((ma) => {
      const maData = calcMA(candleData, ma.period)
      const series = chart.addSeries(LineSeries, {
        color: ma.color,
        lineWidth: 1,
        lastValueVisible: true,
        priceLineVisible: false,
        title: ma.label,
      })
      series.setData(maData)
      maSeriesRef.current.push(series)
    })

    chart.timeScale().fitContent()
  }, [candleData, activeMas])

  // 更新成交量
  useEffect(() => {
    if (!volumeChartRef.current) return
    const chart = volumeChartRef.current

    if (volumeSeriesRef.current) {
      chart.removeSeries(volumeSeriesRef.current)
    }

    const volSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: '',
    })
    volSeries.setData(volumeData)
    volumeSeriesRef.current = volSeries

    chart.timeScale().fitContent()
  }, [volumeData])

  const toggleMA = useCallback((ma: MAConfig) => {
    setActiveMas((prev) => {
      const exists = prev.find((m) => m.period === ma.period)
      if (exists) return prev.filter((m) => m.period !== ma.period)
      return [...prev, ma]
    })
  }, [])

  // 键盘导航
  useEffect(() => {
    const wrapper = chartWrapperRef.current
    if (!wrapper) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (data.length === 0) return
      const chart = chartRef.current
      if (!chart) return

      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        e.preventDefault()
        setSelectedIndex((prev) => {
          const next = e.key === 'ArrowLeft'
            ? Math.max(0, prev === -1 ? data.length - 1 : prev - 1)
            : Math.min(data.length - 1, prev === -1 ? 0 : prev + 1)

          // 更新 tooltip 显示选中 bar 的数据
          const bar = data[next]
          if (bar) {
            setTooltip({
              x: 50, // 固定在左侧
              y: 80, // 固定在顶部偏下
              bar,
            })
            setHoveredData(candleData[next] || null)
          }

          // 滚动到选中位置
          // 计算偏移: 让选中的 bar 居中显示
          const totalBars = candleData.length
          const visibleBars = Math.floor((chartWrapperRef.current?.clientWidth ?? 400) / 8)
          const scrollOffset = totalBars - next - Math.floor(visibleBars / 2)
          chart.timeScale().scrollToPosition(scrollOffset, false)

          return next
        })
      } else if (e.key === 'Escape') {
        setSelectedIndex(-1)
        setTooltip({ x: 0, y: 0, bar: null })
        setHoveredData(null)
        chart.timeScale().fitContent()
      }
    }

    // wrapper 需要 tabIndex 才能接收键盘事件
    wrapper.tabIndex = -1
    wrapper.addEventListener('keydown', handleKeyDown)
    // 自动聚焦
    wrapper.focus()

    return () => {
      wrapper.removeEventListener('keydown', handleKeyDown)
    }
  }, [data, candleData])

  // Legend 数据
  const lastBar = data[data.length - 1]
  const latestPrice = lastBar?.close ?? 0
  const pctChg = lastBar?.pct_chg ?? 0
  const pctColor = pctChg >= 0 ? '#16a34a' : '#dc2626'
  const maValues = activeMas.map((ma) => {
    const values = calcMA(candleData, ma.period)
    const last = values[values.length - 1]
    return last?.value ?? 0
  })

  return (
    <div className={cn('flex flex-col flex-1 min-w-0', className)}>
      <div ref={chartWrapperRef} className="flex-1 min-h-0 p-1.5 relative outline-none focus:outline-none">
        {/* Legend */}
        <div className="absolute left-2 top-2 flex items-center gap-3 pointer-events-none z-10">
          {/* 价格和涨跌幅 */}
          <div className="flex items-baseline gap-1.5">
            <span className="text-base font-semibold tabular-nums" style={{ color: pctColor }}>
              {latestPrice}
            </span>
            <span className="text-xs font-medium" style={{ color: pctColor }}>
              {pctChg}%
            </span>
          </div>
          {/* MA 值 */}
          {activeMas.map((ma, idx) => (
            <span key={ma.period} className="text-xs tabular-nums" style={{ color: ma.color }}>
              {ma.label} {maValues[idx]}
            </span>
          ))}
        </div>
        {/* OHLC Tooltip */}
        {tooltip.bar && (() => {
          const bar = tooltip.bar
          const isUp = bar.close >= bar.open
          const color = isUp ? '#16a34a' : '#dc2626'
          const change = bar.pct_chg ?? 0
          // 计算 tooltip 位置，避免超出图表边界
          const wrapperRect = chartWrapperRef.current?.getBoundingClientRect()
          const tooltipWidth = 160 // 估算 tooltip 宽度
          const tooltipHeight = 110 // 估算 tooltip 高度
          let left = tooltip.x + 15 // 默认在鼠标右侧
          let top = tooltip.y - tooltipHeight - 10 // 默认在鼠标上方
          if (left + tooltipWidth > (wrapperRect?.width ?? 300)) {
            left = tooltip.x - tooltipWidth - 15 // 超出右边界则显示在鼠标左侧
          }
          if (top < 0) {
            top = tooltip.y + 15 // 超出上边界则显示在鼠标下方
          }
          return (
            <div
              className="absolute z-20 pointer-events-none rounded-lg bg-white px-3 py-2 shadow-lg border border-[#e2e5ea]"
              style={{ left, top }}
            >
              <div className="text-xs text-[#5B6170] mb-1">{bar.trade_date}</div>
              <div className="space-y-0.5">
                <div className="flex items-center gap-3 text-xs">
                  <span className="font-semibold tabular-nums" style={{ color }}>{bar.close}</span>
                  <span className="text-xs" style={{ color: change >= 0 ? '#16a34a' : '#dc2626' }}>
                    {change >= 0 ? '+' : ''}{change}%
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs text-[#5B6170]">
                  <span>开 {bar.open}</span>
                  <span>高 {bar.high}</span>
                  <span>收 {bar.close}</span>
                  <span>低 {bar.low}</span>
                </div>
                <div className="text-xs text-[#8B909A]">
                  成交量 {(bar.volume / 10000).toFixed(0)}万
                </div>
              </div>
            </div>
          )
        })()}
        <div ref={containerRef} className="w-full h-full" />
      </div>
      <div className="flex items-center gap-2 border-t border-[var(--color-border-light)] bg-[var(--color-bg-surface)] px-3 py-1.5">
        {DEFAULT_MAS.map((ma) => {
          const isActive = activeMas.some((m) => m.period === ma.period)
          return (
            <button
              key={ma.period}
              onClick={() => toggleMA(ma)}
              className="flex items-center gap-1 rounded px-1.5 py-0.5 text-xs transition-colors"
              style={{
                color: isActive ? ma.color : 'var(--color-text-tertiary)',
                backgroundColor: isActive ? `${ma.color}15` : 'transparent',
              }}
            >
              <span
                className="h-2 w-2 rounded-full"
                style={{ backgroundColor: ma.color, opacity: isActive ? 1 : 0.3 }}
              />
              {ma.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}
