import { useEffect, useMemo, useRef, useState } from 'react'
import {
  createChart,
  CandlestickSeries,
  CrosshairMode,
  LineStyle,
  type BusinessDay,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
} from 'lightweight-charts'
import { Loader2 } from 'lucide-react'
import { useKlineApi } from '@/hooks/useKlineApi'
import { calcCostDistribution } from '@/lib/cost-distribution'
import type { KlineBar } from '@/types/kline'
import { AiInterpretSection } from './AiInterpretSection'
import type { CardType } from '@/lib/cardPrompts'

interface ChipCostCardProps {
  symbol: string
  /** 点击「AI 分析」→ 右侧对话发起预设提问 */
  onAiAnalyze: (type: CardType) => void
}

/** 获利=红（多）/ 套牢=绿（空），符合中国市场红涨绿跌 */
const PROFIT = '#dc2626'
const TRAPPED = '#16a34a'

/** 收盘获利 & 主力持仓成本双拼卡（spec R4，成交密集区替代算法 DEMO） */
export function ChipCostCard({ symbol, onAiAnalyze }: ChipCostCardProps) {
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

  const dist = useMemo(() => {
    if (bars.length === 0) return null
    return calcCostDistribution(bars, bars[bars.length - 1].close)
  }, [bars])

  const currentPrice = bars[bars.length - 1]?.close

  return (
    <div className="relative flex h-full min-h-0 flex-col gap-2">
      {/* 标题 + DEMO 徽标 */}
      <div className="flex items-center justify-between">
        <h3 className="text-xl font-medium text-[var(--color-text-primary)]">收盘获利 · 主力持仓成本</h3>
        <AiInterpretSection onAnalyze={() => onAiAnalyze('chip')} />
      </div>

      {loading ? (
        <div className="flex flex-1 items-center justify-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin text-[var(--color-text-tertiary)]" />
          <span className="text-xs text-[var(--color-text-tertiary)]">加载中...</span>
        </div>
      ) : failed || !dist ? (
        <div className="flex flex-1 items-center justify-center">
          <span className="text-xs text-[var(--color-text-tertiary)]">暂无数据</span>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 gap-3">
          {/* 左半：获利/套牢占比 + 平均成本 */}
          <div className="flex w-[46%] shrink-0 flex-col justify-center gap-2.5">
            <div>
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className="text-[var(--color-text-secondary)]">获利盘</span>
                <span className="font-medium tabular-nums" style={{ color: PROFIT }}>
                  {dist.profitRatio.toFixed(1)}%
                </span>
              </div>
              <div className="flex h-2 w-full overflow-hidden rounded-full bg-[var(--color-bg-hover)]">
                <div style={{ width: `${dist.profitRatio}%`, backgroundColor: PROFIT }} />
                <div style={{ width: `${dist.trappedRatio}%`, backgroundColor: TRAPPED }} />
              </div>
              <div className="mt-1 flex items-center justify-between text-xs">
                <span className="text-[var(--color-text-secondary)]">套牢盘</span>
                <span className="font-medium tabular-nums" style={{ color: TRAPPED }}>
                  {dist.trappedRatio.toFixed(1)}%
                </span>
              </div>
            </div>
            <div className="flex flex-col gap-1 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-[var(--color-text-secondary)]">现价</span>
                <span className="font-medium tabular-nums text-[var(--color-text-primary)]">
                  {currentPrice?.toFixed(2) ?? '--'}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[var(--color-text-secondary)]">平均成本</span>
                <span className="font-medium tabular-nums text-[var(--color-text-primary)]">
                  {dist.avgCost.toFixed(2)}
                </span>
              </div>
            </div>
          </div>

          {/* 右半：K线叠加主力成本线 */}
          <div className="min-w-0 flex-1">
            <MiniKline bars={bars} costLine={dist.mainCost} />
          </div>
        </div>
      )}
    </div>
  )
}

/** 迷你 K 线（最近 60 日）叠加主力成本虚线 */
function MiniKline({ bars, costLine }: { bars: KlineBar[]; costLine: number }) {
  const elRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const priceLinesRef = useRef<IPriceLine[]>([])

  // 创建图表（StrictMode/HMR 防护：清空容器 + try/catch）
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
        crosshair: { mode: CrosshairMode.Normal },
        rightPriceScale: { visible: false },
        timeScale: { visible: false, borderVisible: false },
        handleScroll: false,
        handleScale: false,
      })
      chartRef.current = chart
      const candle = chart.addSeries(CandlestickSeries, {
        upColor: PROFIT,
        downColor: TRAPPED,
        borderUpColor: PROFIT,
        borderDownColor: TRAPPED,
        wickUpColor: PROFIT,
        wickDownColor: TRAPPED,
        priceLineVisible: false,
      })
      seriesRef.current = candle
      chart.timeScale().fitContent()
      return () => {
        chart.remove()
        chartRef.current = null
        seriesRef.current = null
        priceLinesRef.current = []
      }
    } catch {
      /* 图表初始化失败静默，卡片保留左半信息 */
    }
  }, [])

  // 数据 + 成本线更新
  useEffect(() => {
    const chart = chartRef.current
    const series = seriesRef.current
    if (!chart || !series) return
    try {
      const data = bars
        .filter((b) => b && b.trade_date)
        .map((b) => ({
          time: toBD(b.trade_date),
          open: b.open,
          high: b.high,
          low: b.low,
          close: b.close,
        }))
      series.setData(data as never)

      // 主力成本虚线（移除旧线后重建）
      priceLinesRef.current.forEach((l) => {
        try {
          series.removePriceLine(l)
        } catch {
          /* ignore */
        }
      })
      priceLinesRef.current = []
      if (costLine > 0) {
        priceLinesRef.current.push(
          series.createPriceLine({
            price: costLine,
            color: '#3b82f6',
            lineStyle: LineStyle.Dashed,
            lineWidth: 1,
            axisLabelVisible: false,
            title: '主力成本',
          }),
        )
      }
      chart.timeScale().fitContent()
    } catch {
      /* ignore */
    }
  }, [bars, costLine])

  return <div ref={elRef} className="h-full w-full" />
}

/** 'YYYY-MM-DD' → BusinessDay */
function toBD(dateStr: string): BusinessDay {
  const [y, m, d] = dateStr.split('-').map(Number)
  return { year: y, month: m, day: d }
}
