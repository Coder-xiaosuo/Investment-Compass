import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  CrosshairMode,
  type BusinessDay,
  type IChartApi,
  type ISeriesApi,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts'
import { Loader2 } from 'lucide-react'
import { useKlineApi } from '@/hooks/useKlineApi'
import { aggregateToMonthly, aggregateToWeekly } from '@/lib/aggregate'
import { calcBIAS, calcBOLL, calcKDJ, calcMA, calcMACD, type OHLCBar } from '@/lib/indicators'
import type { KlineBar, StockDetail, StockQuote } from '@/types/kline'
import { cn } from '@/lib/utils'

interface KLineCardProps {
  symbol: string
}

type PeriodKey = '1m' | '1d' | '1w' | '1M'
type SubIndicator = 'MACD' | 'KDJ' | 'BOLL' | 'BIAS'

const PERIODS: { key: PeriodKey; label: string; intraday?: boolean; aggregate?: boolean }[] = [
  { key: '1m', label: '分时', intraday: true },
  { key: '1d', label: '日K' },
  { key: '1w', label: '周K', aggregate: true },
  { key: '1M', label: '月K', aggregate: true },
]

const SUB_INDICATORS: SubIndicator[] = ['MACD', 'KDJ', 'BOLL', 'BIAS']

/** 中国市场标准：红涨绿跌 */
const UP = '#dc2626'
const DOWN = '#16a34a'
/** MA 蓝色系（spec R7 蓝色辅助） */
const MA_COLORS = ['#3b82f6', '#60a5fa', '#a5b4fc']
const MA_PERIODS = [5, 10, 30]

// ── 时间转换 ─────────────────────────────────────────────────────────────────

function toBusinessDay(dateStr: string): BusinessDay | null {
  if (!dateStr || typeof dateStr !== 'string') return null
  const parts = dateStr.split('-')
  if (parts.length !== 3) return null
  const [y, m, d] = parts.map(Number)
  if (isNaN(y) || isNaN(m) || isNaN(d)) return null
  return { year: y, month: m, day: d }
}

function toOHLC(bars: KlineBar[], intraday: boolean): OHLCBar[] {
  return bars
    .filter((b) => b && b.trade_date)
    .map((b) => ({
      time: intraday
        ? (((b.ts_open ?? Date.parse(b.trade_date)) / 1000) as UTCTimestamp)
        : (toBusinessDay(b.trade_date) as BusinessDay),
      open: b.open,
      high: b.high,
      low: b.low,
      close: b.close,
      volume: b.volume,
    }))
}

function sameTime(a: Time, b: Time): boolean {
  if (typeof a === 'object' && typeof b === 'object') {
    const ta = a as BusinessDay
    const tb = b as BusinessDay
    return ta.year === tb.year && ta.month === tb.month && ta.day === tb.day
  }
  return a === b
}

/** 依据主图十字线，将副图十字线定位到对应 time 的数值上 */
function syncCrosshair(
  target: IChartApi,
  series: ISeriesApi<any> | null,
  data: { time: Time }[] | null,
  time: Time | undefined,
) {
  if (!series || !data || time === undefined) {
    try {
      target.clearCrosshairPosition()
    } catch {
      /* ignore */
    }
    return
  }
  const point = data.find((d) => sameTime(d.time, time))
  if (point && 'value' in point) {
    try {
      target.setCrosshairPosition((point as { value: number }).value, time, series)
    } catch {
      target.clearCrosshairPosition()
    }
  } else {
    try {
      target.clearCrosshairPosition()
    } catch {
      /* ignore */
    }
  }
}

// ── 组件 ─────────────────────────────────────────────────────────────────────

export function KLineCard({ symbol }: KLineCardProps) {
  const { fetchKlineHistory, fetchQuote, fetchDetail } = useKlineApi()
  const [period, setPeriod] = useState<PeriodKey>('1d')
  const [sub, setSub] = useState<SubIndicator>('MACD')
  const [bars, setBars] = useState<KlineBar[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [quote, setQuote] = useState<StockQuote | null>(null)
  const [detail, setDetail] = useState<StockDetail | null>(null)
  const [chartError, setChartError] = useState<string | null>(null)

  const mainElRef = useRef<HTMLDivElement>(null)
  const volElRef = useRef<HTMLDivElement>(null)
  const subElRef = useRef<HTMLDivElement>(null)
  const mainChartRef = useRef<IChartApi | null>(null)
  const volChartRef = useRef<IChartApi | null>(null)
  const subChartRef = useRef<IChartApi | null>(null)
  const mainSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const maSeriesRef = useRef<ISeriesApi<'Line'>[]>([])
  const volSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const subSeriesRef = useRef<ISeriesApi<any>[]>([])
  /** 副图十字线同步所需的数值快照（VOL / 副图第一个 series） */
  const volDataRef = useRef<{ time: Time; value: number }[] | null>(null)
  const subDataRef = useRef<{ time: Time; value: number }[] | null>(null)

  const intraday = period === '1m'
  const ohlc = useMemo(() => toOHLC(bars, intraday), [bars, intraday])
  const macd = useMemo(() => calcMACD(ohlc), [ohlc])
  const kdj = useMemo(() => calcKDJ(ohlc), [ohlc])
  const boll = useMemo(() => calcBOLL(ohlc), [ohlc])
  const bias = useMemo(() => calcBIAS(ohlc), [ohlc])

  // 周期 / 标的切换时加载 K 线（周/月由日线聚合）
  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      let result: KlineBar[]
      if (period === '1w' || period === '1M') {
        const daily = await fetchKlineHistory(symbol, '1d', 500)
        result = period === '1w' ? aggregateToWeekly(daily) : aggregateToMonthly(daily)
      } else {
        result = await fetchKlineHistory(symbol, period === '1m' ? '1m' : '1d', period === '1m' ? 480 : 200)
      }
      setBars(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取K线数据失败')
      setBars([])
    } finally {
      setLoading(false)
    }
  }, [symbol, period, fetchKlineHistory])

  useEffect(() => {
    load()
  }, [load])

  // 标的切换时拉取行情快照与详情（左栏价格面板）
  useEffect(() => {
    setQuote(null)
    setDetail(null)
    if (!symbol) return
    fetchQuote(symbol).then(setQuote).catch(() => setQuote(null))
    fetchDetail(symbol).then(setDetail).catch(() => setDetail(null))
  }, [symbol, fetchQuote, fetchDetail])

  // ── 图表实例创建（三栏：主图 60% / VOL 20% / 副图 20%）──
  useEffect(() => {
    setChartError(null)
    const mainEl = mainElRef.current
    const volEl = volElRef.current
    const subEl = subElRef.current
    if (!mainEl || !volEl || !subEl) return

    try {
      const baseOpts = {
        layout: { background: { color: '#ffffff' }, textColor: '#6b7280', fontSize: 10, fontFamily: "'Inter', -apple-system, sans-serif" },
        grid: { vertLines: { color: '#f0f2f5', style: 1 as const }, horzLines: { color: '#f0f2f5', style: 1 as const } },
        crosshair: { mode: CrosshairMode.Normal },
        rightPriceScale: { borderColor: '#e2e5ea', scaleMargins: { top: 0.08, bottom: 0.06 } },
        // 时间轴：锁定左右边缘（最新K线固定贴右，拖动/缩放不漂移）
        timeScale: { borderColor: '#e2e5ea', fixLeftEdge: true, fixRightEdge: true, rightOffset: 0 },
        handleScroll: true,
        handleScale: true,
        autoSize: true,
      }

      // 清空容器残留（StrictMode/HMR 下 effect 双执行，避免容器重复初始化）
      mainEl.innerHTML = ''
      volEl.innerHTML = ''
      subEl.innerHTML = ''

      const mainChart = createChart(mainEl, { ...baseOpts, timeScale: { ...baseOpts.timeScale, timeVisible: intraday } })
      const volChart = createChart(volEl, {
        ...baseOpts,
        layout: { ...baseOpts.layout, fontSize: 10 },
        rightPriceScale: { borderColor: '#e2e5ea', scaleMargins: { top: 0.08, bottom: 0.15 }, visible: false },
        timeScale: { borderColor: '#e2e5ea', visible: false },
      })
      const subChart = createChart(subEl, {
        ...baseOpts,
        layout: { ...baseOpts.layout, fontSize: 10 },
        rightPriceScale: { borderColor: '#e2e5ea', scaleMargins: { top: 0.08, bottom: 0.15 }, visible: false },
        timeScale: { borderColor: '#e2e5ea', visible: false },
      })
      mainChartRef.current = mainChart
      volChartRef.current = volChart
      subChartRef.current = subChart

      // 时间轴同步：主图 → 副图1/2
      mainChart.timeScale().subscribeVisibleTimeRangeChange((range) => {
        if (!range) return
        volChart.timeScale().setVisibleRange(range)
        subChart.timeScale().setVisibleRange(range)
      })

      // 十字线同步：主图 → 副图1/2
      mainChart.subscribeCrosshairMove((param) => {
        try {
          syncCrosshair(volChart, volSeriesRef.current, volDataRef.current, param.time)
          syncCrosshair(subChart, subSeriesRef.current[0] ?? null, subDataRef.current, param.time)
        } catch {
          // 十字线同步失败不影响主体渲染
        }
      })

      return () => {
        mainChart.remove()
        volChart.remove()
        subChart.remove()
        mainChartRef.current = null
        volChartRef.current = null
        subChartRef.current = null
        mainSeriesRef.current = null
        maSeriesRef.current = []
        volSeriesRef.current = null
        subSeriesRef.current = []
      }
    } catch (err) {
      setChartError(`图表创建：${err instanceof Error ? err.message : String(err)}`)
      return () => {
        mainChartRef.current = null
        volChartRef.current = null
        subChartRef.current = null
      }
    }
  }, [intraday])

  // ── 主图 + VOL 数据更新 ──
  useEffect(() => {
    const mainChart = mainChartRef.current
    const volChart = volChartRef.current
    if (!mainChart || !volChart) return
    if (loading || ohlc.length === 0) return

    try {
      // 主图
      try {
        if (mainSeriesRef.current) mainChart.removeSeries(mainSeriesRef.current)
      } catch {
        /* series 可能已被移除，忽略 */
      }
      maSeriesRef.current.forEach((s) => {
        try {
          mainChart.removeSeries(s)
        } catch {
          /* ignore */
        }
      })
      maSeriesRef.current = []
      const candle = mainChart.addSeries(CandlestickSeries, {
        upColor: UP,
        downColor: DOWN,
        borderUpColor: UP,
        borderDownColor: DOWN,
        wickUpColor: UP,
        wickDownColor: DOWN,
      })
      candle.setData(
        ohlc.map((b) => ({ time: b.time, open: b.open, high: b.high, low: b.low, close: b.close })),
      )
      mainSeriesRef.current = candle
      MA_PERIODS.forEach((p, idx) => {
        const line = mainChart.addSeries(LineSeries, {
          color: MA_COLORS[idx],
          lineWidth: 1,
          lastValueVisible: true,
          priceLineVisible: false,
          title: `MA${p}`,
        })
        line.setData(calcMA(ohlc, p))
        maSeriesRef.current.push(line)
      })

      // VOL（红涨绿跌）
      try {
        if (volSeriesRef.current) volChart.removeSeries(volSeriesRef.current)
      } catch {
        /* ignore */
      }
      const vol = volChart.addSeries(HistogramSeries, { priceFormat: { type: 'volume' }, priceScaleId: '' })
      const volData = ohlc.map((b) => ({
        time: b.time,
        value: b.volume,
        color: b.close >= b.open ? 'rgba(220, 38, 38, 0.45)' : 'rgba(22, 163, 74, 0.45)',
      }))
      vol.setData(volData)
      volSeriesRef.current = vol
      volDataRef.current = volData

      mainChart.timeScale().fitContent()
      volChart.timeScale().fitContent()
      setChartError(null)
    } catch (err) {
      setChartError(`主图更新：${err instanceof Error ? err.message : String(err)}`)
    }
  }, [ohlc, loading])

  // ── 副图指标更新 ──
  useEffect(() => {
    const subChart = subChartRef.current
    if (!subChart) return
    if (loading || ohlc.length === 0) return

    try {
      subSeriesRef.current.forEach((s) => {
        try {
          subChart.removeSeries(s)
        } catch {
          /* series 可能已被移除，忽略 */
        }
      })
      subSeriesRef.current = []

      const addLine = (color: string, data: { time: Time; value: number }[], title?: string) => {
        const series = subChart.addSeries(LineSeries, {
          color,
          lineWidth: 1,
          lastValueVisible: true,
          priceLineVisible: false,
          title,
        })
        series.setData(data)
        subSeriesRef.current.push(series)
        return series
      }
      const addHist = (data: { time: Time; value: number; color: string }[]) => {
        const series = subChart.addSeries(HistogramSeries, { priceScaleId: '' })
        series.setData(data)
        subSeriesRef.current.push(series)
        return series
      }
      subDataRef.current = null

      if (sub === 'MACD') {
        addLine('#3b82f6', macd.map((m) => ({ time: m.time, value: m.dif })), 'DIF')
        addLine('#f59e0b', macd.map((m) => ({ time: m.time, value: m.dea })), 'DEA')
        addHist(macd.map((m) => ({ time: m.time, value: Math.abs(m.hist), color: m.hist >= 0 ? 'rgba(220, 38, 38, 0.5)' : 'rgba(22, 163, 74, 0.5)' })))
        subDataRef.current = macd.map((m) => ({ time: m.time, value: m.dif }))
      } else if (sub === 'KDJ') {
        addLine('#3b82f6', kdj.map((m) => ({ time: m.time, value: m.k })), 'K')
        addLine('#f59e0b', kdj.map((m) => ({ time: m.time, value: m.d })), 'D')
        addLine('#8b5cf6', kdj.map((m) => ({ time: m.time, value: m.j })), 'J')
        subDataRef.current = kdj.map((m) => ({ time: m.time, value: m.k }))
      } else if (sub === 'BOLL') {
        addLine('#3b82f6', boll.map((m) => ({ time: m.time, value: m.mid })), 'MID')
        addLine('#60a5fa', boll.map((m) => ({ time: m.time, value: m.upper })), 'UP')
        addLine('#a5b4fc', boll.map((m) => ({ time: m.time, value: m.lower })), 'LOW')
        subDataRef.current = boll.map((m) => ({ time: m.time, value: m.mid }))
      } else {
        for (const [i, p] of [6, 12, 24].entries()) {
          addLine(['#3b82f6', '#f59e0b', '#8b5cf6'][i], bias[p] ?? [], `BIAS${p}`)
        }
        subDataRef.current = bias[6] ?? null
      }
      subChart.timeScale().fitContent()
    } catch (err) {
      setChartError(`副图更新：${err instanceof Error ? err.message : String(err)}`)
    }
  }, [ohlc, sub, loading, macd, kdj, boll, bias])

  // ── 左栏价格面板数据（detail 更完整，quote 兜底；camelCase）──
  const lastBar = bars[bars.length - 1]
  const price = detail?.latestClose ?? quote?.close
  const changePct = detail?.changePercent ?? quote?.changePct
  const changeAmt =
    detail?.change ??
    (quote && quote.close != null && quote.preClose != null ? quote.close - quote.preClose : 0)
  const isUp = (changePct ?? 0) >= 0
  const trendColor = isUp ? UP : DOWN
  // 后端 turnover_rate 个别记录为万分比（>100），合理化为主比
  const turnover =
    lastBar?.turnover_rate != null ? (lastBar.turnover_rate >= 100 ? lastBar.turnover_rate / 100 : lastBar.turnover_rate) : null

  return (
    <div className="flex h-full min-h-0">
      {/* 左栏：价格面板 */}
      <div className="flex w-40 shrink-0 flex-col gap-3 border-r border-[var(--color-border-light)] pr-3">
        <div className="flex items-baseline gap-2">
          <span className="text-xl font-semibold tabular-nums" style={{ color: trendColor }}>
            {price != null ? price.toFixed(2) : '--'}
          </span>
          <span className="text-xs font-medium tabular-nums" style={{ color: trendColor }}>
            {changePct != null ? `${changePct >= 0 ? '+' : ''}${changePct.toFixed(2)}%` : '--'}
          </span>
        </div>
        <span className="text-xs text-[var(--color-text-secondary)]">
          {changeAmt != null ? `${changeAmt >= 0 ? '+' : ''}${changeAmt.toFixed(2)}` : '--'} {detail?.stockName ?? ''}
        </span>
        <div className="flex flex-col gap-1.5 text-xs">
          <PanelRow label="今开" value={detail?.latestOpen} />
          <PanelRow label="昨收" value={quote?.preClose} />
          <PanelRow label="最高" value={detail?.latestHigh} highlight={UP} />
          <PanelRow label="最低" value={detail?.latestLow} highlight={DOWN} />
          <PanelRow label="成交量" value={detail?.latestVolume} format={fmtVolume} />
          <PanelRow label="成交额" value={detail?.latestAmount} format={fmtAmount} />
          <PanelRow label="换手率" value={turnover} suffix="%" />
        </div>
      </div>

      {/* 右栏：三栏堆叠图区 */}
      <div className="flex min-w-0 flex-1 flex-col pl-3">
        {/* 控件栏 */}
        <div className="mb-1 flex shrink-0 items-center justify-between">
          <div className="flex items-center gap-1">
            {PERIODS.map((p) => (
              <button
                key={p.key}
                onClick={() => setPeriod(p.key)}
                className={cn(
                  'rounded px-2 py-0.5 text-xs transition-colors',
                  period === p.key
                    ? 'bg-[var(--color-accent)] font-medium text-white'
                    : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)]',
                )}
              >
                {p.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1">
            {SUB_INDICATORS.map((name) => (
              <button
                key={name}
                onClick={() => setSub(name)}
                className={cn(
                  'rounded px-2 py-0.5 text-xs transition-colors',
                  sub === name
                    ? 'bg-[var(--color-accent)] font-medium text-white'
                    : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)]',
                )}
              >
                {name}
              </button>
            ))}
          </div>
        </div>

        {/* 图区：三栏始终挂载（chart 实例依赖稳定的容器），loading/error 用覆盖层 */}
        <div className="relative min-h-0 flex-1">
          <div className="flex h-full min-h-0 flex-col">
            <div ref={mainElRef} className="min-h-0 flex-[3]" />
            <div ref={volElRef} className="min-h-0 flex-1" />
            <div ref={subElRef} className="min-h-0 flex-1" />
          </div>
          {loading && (
            <ChartOverlay>
              <Loader2 className="h-5 w-5 animate-spin text-[var(--color-text-tertiary)]" />
              <span className="text-xs text-[var(--color-text-tertiary)]">加载中...</span>
            </ChartOverlay>
          )}
          {!loading && error && <ChartOverlay><span className="text-xs text-[var(--color-text-tertiary)]">{error}</span></ChartOverlay>}
          {!loading && chartError && (
            <ChartOverlay><span className="max-w-[90%] break-all text-xs text-[var(--color-danger)]">图表初始化失败：{chartError}</span></ChartOverlay>
          )}
          {!loading && !error && !chartError && bars.length === 0 && (
            <ChartOverlay><span className="text-xs text-[var(--color-text-tertiary)]">暂无K线数据</span></ChartOverlay>
          )}
        </div>
      </div>
    </div>
  )
}

/** 图区覆盖层（加载中 / 错误 / 空数据） */
function ChartOverlay({ children }: { children: React.ReactNode }) {
  return (
    <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 bg-white/70">
      {children}
    </div>
  )
}

function PanelRow({
  label,
  value,
  highlight,
  suffix,
  format,
}: {
  label: string
  value: number | null | undefined
  highlight?: string
  suffix?: string
  format?: (v: number) => string
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[var(--color-text-secondary)]">{label}</span>
      <span className="font-medium tabular-nums" style={highlight ? { color: highlight } : undefined}>
        {value == null ? '--' : `${format ? format(value) : value.toFixed(2)}${suffix ?? ''}`}
      </span>
    </div>
  )
}

/** 成交量（股 → 万手） */
function fmtVolume(v: number) {
  return v >= 1e6 ? `${(v / 1e6).toFixed(2)}万手` : `${(v / 1e4).toFixed(0)}手`
}

/** 成交额（元 → 亿/万） */
function fmtAmount(v: number) {
  return v >= 1e8 ? `${(v / 1e8).toFixed(2)}亿` : `${(v / 1e4).toFixed(0)}万`
}
