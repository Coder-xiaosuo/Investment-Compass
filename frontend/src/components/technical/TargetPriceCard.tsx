import { useEffect, useMemo, useRef, useState } from 'react'
import {
  createChart,
  LineSeries,
  LineStyle,
  type BusinessDay,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
} from 'lightweight-charts'
import { Loader2 } from 'lucide-react'
import { useKlineApi } from '@/hooks/useKlineApi'
import type { DecisionCardData } from '@/types'
import type { KlineBar } from '@/types/kline'
import { AiInterpretSection } from './AiInterpretSection'
import type { CardType } from '@/lib/cardPrompts'

interface TargetPriceCardProps {
  symbol: string
  /** 主控台最近一次该股 composite_decision 的 card_data（可能为 null） */
  cardData: DecisionCardData | null
  /** 点击「AI 分析」→ 右侧对话发起预设提问 */
  onAiAnalyze: (type: CardType) => void
}

/** AI 蓝（目标价/趋势元素）+ 红涨绿跌 */
const AI_BLUE = '#3b82f6'
const UP = '#dc2626'
const DOWN = '#16a34a'

interface ParsedResult {
  resistance?: number
  entry_price?: number
  estimated_win_rate?: number
  support?: number
  direction?: string
  confidence?: number
}

/** 从 card_data.result（TechnicalResult）解析目标价所需字段 */
function parseResult(cardData: DecisionCardData | null): ParsedResult | null {
  const result = cardData?.result
  if (!result || typeof result !== 'object') return null
  const p: ParsedResult = {}
  if (typeof result.resistance === 'number') p.resistance = result.resistance
  if (typeof result.entry_price === 'number') p.entry_price = result.entry_price
  if (typeof result.estimated_win_rate === 'number') p.estimated_win_rate = result.estimated_win_rate
  if (typeof result.support === 'number') p.support = result.support
  if (typeof result.direction === 'string') p.direction = result.direction
  if (typeof result.confidence === 'number') p.confidence = result.confidence
  return p
}

/** 方向标签（TechnicalResult.direction: buy/sell/neutral） */
function directionLabel(direction?: string): { text: string; color: string } {
  if (direction === 'buy') return { text: '看多', color: UP }
  if (direction === 'sell') return { text: '看空', color: DOWN }
  return { text: '中性', color: '#6b7280' }
}

/** 预测目标价卡（spec R6，AI）：主控台最近 composite_decision 的 TechnicalResult */
export function TargetPriceCard({ symbol, cardData, onAiAnalyze }: TargetPriceCardProps) {
  const parsed = useMemo(() => parseResult(cardData), [cardData])

  // 无记录 / 无 resistance → 占位
  if (!parsed || parsed.resistance == null) {
    return (
      <div className="relative flex h-full min-h-0 flex-col gap-2">
        <div className="flex items-center justify-between">
          <h3 className="text-xl font-medium text-[var(--color-text-primary)]">预测目标价</h3>
          <AiInterpretSection onAnalyze={() => onAiAnalyze('target')} />
        </div>
        <div className="flex flex-1 items-center justify-center">
          <span className="text-xs text-[var(--color-text-tertiary)]">暂无 AI 预测</span>
        </div>
      </div>
    )
  }

  return <TargetView symbol={symbol} parsed={parsed} analyzedAt={cardData?.['_analyzed_at'] as string | undefined} onAiAnalyze={onAiAnalyze} />
}

/** 有分析结果：数值区 + 趋势线 */
function TargetView({ symbol, parsed, analyzedAt, onAiAnalyze }: { symbol: string; parsed: ParsedResult; analyzedAt?: string; onAiAnalyze: (type: CardType) => void }) {
  const { fetchKlineHistory } = useKlineApi()
  const [bars, setBars] = useState<KlineBar[]>([])
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setFailed(false)
    setBars([])
    if (!symbol) {
      setLoading(false)
      return
    }
    fetchKlineHistory(symbol, '1d', 60)
      .then((data) => {
        if (cancelled) return
        if (data.length === 0) setFailed(true)
        else setBars(data)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [symbol, fetchKlineHistory])

  const { resistance, entry_price, estimated_win_rate, direction } = parsed
  const target = resistance as number
  const entry = entry_price ?? parsed.support ?? NaN
  const dir = directionLabel(direction)
  const analyzedLabel = useMemo(() => {
    if (!analyzedAt) return null
    const d = new Date(analyzedAt)
    if (isNaN(d.getTime())) return null
    return `${d.getMonth() + 1}/${d.getDate()}`
  }, [analyzedAt])

  return (
    <div className="relative flex h-full min-h-0 flex-col gap-2">
      <div className="flex items-center justify-between">
        <h3 className="text-xl font-medium text-[var(--color-text-primary)]">预测目标价</h3>
        <AiInterpretSection onAnalyze={() => onAiAnalyze('target')} />
      </div>

      {loading ? (
        <div className="flex flex-1 items-center justify-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin text-[var(--color-text-tertiary)]" />
          <span className="text-xs text-[var(--color-text-tertiary)]">加载中...</span>
        </div>
      ) : failed || bars.length === 0 ? (
        /* K线取不到时降级：仅显示目标价/区间数值 */
        <NumericView target={target} entry={entry} winRate={estimated_win_rate} dir={dir} analyzedLabel={analyzedLabel} />
      ) : (
        <div className="flex min-h-0 flex-1 gap-3">
          <div className="flex w-[42%] shrink-0 flex-col justify-center gap-2">
            <NumericView target={target} entry={entry} winRate={estimated_win_rate} dir={dir} analyzedLabel={analyzedLabel} />
          </div>
          <div className="min-w-0 flex-1">
            <TrendChart bars={bars} target={target} entry={Number.isFinite(entry) ? entry : null} />
          </div>
        </div>
      )}
    </div>
  )
}

/** 数值区：目标价 / 区间 / 预估胜率 / 方向 */
function NumericView({
  target,
  entry,
  winRate,
  dir,
  analyzedLabel,
}: {
  target: number
  entry: number
  winRate?: number
  dir: { text: string; color: string }
  analyzedLabel: string | null
}) {
  const hasEntry = Number.isFinite(entry)
  return (
    <div className="flex flex-col justify-center gap-2">
      <div className="flex items-baseline gap-2">
        <span className="text-xl font-semibold tabular-nums" style={{ color: AI_BLUE }}>
          {target.toFixed(2)}
        </span>
        <span className="text-xs text-[var(--color-text-secondary)]">目标价</span>
      </div>
      <div className="text-xs text-[var(--color-text-secondary)]">
        {hasEntry ? (
          <>
            区间 <span className="font-medium tabular-nums text-[var(--color-text-primary)]">{entry.toFixed(2)}</span> ~{' '}
            <span className="font-medium tabular-nums text-[var(--color-text-primary)]">{target.toFixed(2)}</span>
          </>
        ) : (
          '无入场参考'
        )}
      </div>
      <div className="flex items-center gap-2 text-xs">
        <span className="rounded-full px-2 py-0.5 text-xs font-medium" style={{ color: dir.color, backgroundColor: `${dir.color}1a` }}>
          {dir.text}
        </span>
        {winRate != null && (
          <span className="text-[var(--color-text-secondary)]">
            胜率 <span className="font-medium tabular-nums text-[var(--color-text-primary)]">{winRate}%</span>
          </span>
        )}
      </div>
      {analyzedLabel && <p className="text-xs text-[var(--color-text-tertiary)]">预测节点 · {analyzedLabel}</p>}
    </div>
  )
}

/** 趋势线：最近 K 线收盘序列 + 目标价虚线延伸（标注最高/最低/目标价） */
function TrendChart({ bars, target, entry }: { bars: KlineBar[]; target: number; entry: number | null }) {
  const elRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const linesRef = useRef<IPriceLine[]>([])

  // 创建图表
  useEffect(() => {
    const el = elRef.current
    if (!el) return
    try {
      el.innerHTML = ''
      const chart = createChart(el, {
        autoSize: true,
        layout: {
          background: { color: 'transparent' },
          textColor: '#6b7280',
          fontSize: 9,
          fontFamily: "'Inter', -apple-system, sans-serif",
        },
        grid: { vertLines: { visible: false }, horzLines: { visible: false } },
        rightPriceScale: { borderVisible: false },
        timeScale: { borderVisible: false, visible: false },
        handleScroll: false,
        handleScale: false,
      })
      chartRef.current = chart
      const line = chart.addSeries(LineSeries, {
        color: AI_BLUE,
        lineWidth: 1,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
      })
      seriesRef.current = line
      chart.timeScale().fitContent()
      return () => {
        chart.remove()
        chartRef.current = null
        seriesRef.current = null
        linesRef.current = []
      }
    } catch {
      /* 静默 */
    }
  }, [])

  // 数据 + 虚线更新
  useEffect(() => {
    const chart = chartRef.current
    const series = seriesRef.current
    if (!chart || !series) return
    try {
      const data = bars
        .filter((b) => b && b.trade_date)
        .map((b) => ({ time: toBD(b.trade_date), value: b.close }))
      series.setData(data as never)

      // 移除旧虚线
      linesRef.current.forEach((l) => {
        try {
          series.removePriceLine(l)
        } catch {
          /* ignore */
        }
      })
      linesRef.current = []

      const hi = Math.max(...bars.map((b) => b.high))
      const lo = Math.min(...bars.map((b) => b.low))
      const mk = (price: number, color: string, title: string) => {
        if (!Number.isFinite(price) || price <= 0) return
        linesRef.current.push(
          series.createPriceLine({
            price,
            color,
            lineStyle: LineStyle.Dashed,
            lineWidth: 1,
            axisLabelVisible: false,
            title,
          }),
        )
      }
      mk(hi, UP, '最高')
      mk(lo, DOWN, '最低')
      mk(target, AI_BLUE, '目标价')
      if (entry != null) mk(entry, '#6b7280', '入场')

      chart.timeScale().fitContent()
    } catch {
      /* ignore */
    }
  }, [bars, target, entry])

  return <div ref={elRef} className="h-full w-full" />
}

/** 'YYYY-MM-DD' → BusinessDay */
function toBD(dateStr: string): BusinessDay {
  const [y, m, d] = dateStr.split('-').map(Number)
  return { year: y, month: m, day: d }
}
