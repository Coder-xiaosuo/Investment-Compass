import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { AiInterpretSection } from '@/components/technical/AiInterpretSection'
import { useFundamentalApi, type FinancialReport } from '@/hooks/useFundamentalApi'
import type { CardType } from '@/lib/cardPrompts'

interface GrowthCardProps {
  symbol: string
  /** 点击「AI 分析」→ 右侧对话发起预设提问 */
  onAiAnalyze: (type: CardType) => void
}

/** 营收增速=红 / 利润增速=绿，符合中国市场红涨绿跌 */
const REV_COLOR = '#dc2626'
const PROFIT_COLOR = '#16a34a'

/** Mock：8 季度 YoY（百分比） */
const MOCK_REV_YOY = [10.5, 12.3, 15.1, 18.2, 16.5, 14.8, 11.2, 9.5]
const MOCK_PROFIT_YOY = [13.2, 15.6, 19.4, 22.1, 20.3, 17.5, 13.8, 11.0]

/** CAGR 计算：首末期对比，years 由日期差推算。无效返回 null。 */
function calcCAGR(
  firstVal: number | null,
  lastVal: number | null,
  firstDate: string,
  lastDate: string,
): number | null {
  if (firstVal == null || lastVal == null || firstVal <= 0 || lastVal <= 0) return null
  const days = (Date.parse(lastDate) - Date.parse(firstDate)) / 86_400_000
  if (days <= 0) return null
  const years = days / 365.25
  return (Math.pow(lastVal / firstVal, 1 / years) - 1) * 100
}

/** 成长能力卡（spec，真实数据 + 失败回退 mock）：营收/利润 YoY 双折线 + CAGR */
export function GrowthCard({ symbol, onAiAnalyze }: GrowthCardProps) {
  const { fetchFinancialReport } = useFundamentalApi()
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [realData, setRealData] = useState<FinancialReport | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setFailed(false)
    setRealData(null)
    if (!symbol) {
      setLoading(false)
      return
    }
    fetchFinancialReport(symbol)
      .then((data) => {
        if (cancelled) return
        if (data) setRealData(data)
        else setFailed(true)
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
  }, [symbol, fetchFinancialReport])

  // 真实数据：按 report_date ASC 排序，后端返回 DESC
  const reports = realData?.reports ?? []
  const sortedAsc = [...reports].sort((a, b) => a.report_date.localeCompare(b.report_date))

  const revenueYoY = sortedAsc.length > 0
    ? sortedAsc.map((r) => r.revenue_growth ?? 0)
    : MOCK_REV_YOY
  const profitYoY = sortedAsc.length > 0
    ? sortedAsc.map((r) => r.profit_growth ?? 0)
    : MOCK_PROFIT_YOY

  // CAGR：用 4 期营收/净利润首末期对比计算，失败回退 mock
  const revCagr = sortedAsc.length >= 2
    ? (calcCAGR(
        sortedAsc[0].revenue,
        sortedAsc[sortedAsc.length - 1].revenue,
        sortedAsc[0].report_date,
        sortedAsc[sortedAsc.length - 1].report_date,
      ) ?? 15.3)
    : 15.3
  const profitCagr = sortedAsc.length >= 2
    ? (calcCAGR(
        sortedAsc[0].net_profit,
        sortedAsc[sortedAsc.length - 1].net_profit,
        sortedAsc[0].report_date,
        sortedAsc[sortedAsc.length - 1].report_date,
      ) ?? 18.7)
    : 18.7

  return (
    <div className="relative flex h-full min-h-0 flex-col gap-2">
      {/* 标题 + DEMO 徽标 + AI 分析 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-xl font-medium text-[var(--color-text-primary)]">成长能力</h3>
          {(failed || !realData) && (
            <span className="rounded bg-[var(--color-bg-subtle)] px-1.5 py-0.5 text-xs font-mono text-[var(--color-text-tertiary)]">DEMO</span>
          )}
        </div>
        <AiInterpretSection onAnalyze={() => onAiAnalyze('growth')} />
      </div>

      {loading ? (
        <div className="flex flex-1 items-center justify-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin text-[var(--color-text-tertiary)]" />
          <span className="text-xs text-[var(--color-text-tertiary)]">加载中...</span>
        </div>
      ) : (
        <>
          {/* 顶部 2 个 CAGR 指标卡 */}
          <div className="grid grid-cols-2 gap-4">
            <CagrCell label="营收2年CAGR" value={revCagr} color={REV_COLOR} />
            <CagrCell label="利润2年CAGR" value={profitCagr} color={PROFIT_COLOR} />
          </div>

          {/* 双折线图 */}
          <div className="flex min-h-0 flex-1 flex-col gap-1">
            <div className="flex items-center gap-3 text-xs">
              <span className="flex items-center gap-1">
                <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: REV_COLOR }} />
                <span className="text-[var(--color-text-secondary)]">营收YoY</span>
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: PROFIT_COLOR }} />
                <span className="text-[var(--color-text-secondary)]">利润YoY</span>
              </span>
            </div>
            <div className="min-h-0 flex-1">
              <MiniLineChart revenue={revenueYoY} profit={profitYoY} />
            </div>
          </div>
        </>
      )}
    </div>
  )
}

/** CAGR 指标卡 */
function CagrCell({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-[var(--color-text-secondary)]">{label}</span>
      <span className="text-lg font-semibold tabular-nums" style={{ color }}>
        {value.toFixed(1)}%
      </span>
    </div>
  )
}

/** SVG 双折线迷你图：营收/利润 YoY 趋势 */
function MiniLineChart({ revenue, profit }: { revenue: number[]; profit: number[] }) {
  const W = 100
  const H = 40
  const padX = 4
  const padY = 4

  const all = [...revenue, ...profit]
  const max = Math.max(...all)
  const min = Math.min(...all, 0)
  const range = max - min || 1

  const toPoints = (data: number[]) =>
    data
      .map((v, i) => {
        const x = padX + (i / (data.length - 1)) * (W - padX * 2)
        const y = H - padY - ((v - min) / range) * (H - padY * 2)
        return `${x.toFixed(2)},${y.toFixed(2)}`
      })
      .join(' ')

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-full w-full" preserveAspectRatio="none">
      <polyline
        points={toPoints(revenue)}
        fill="none"
        stroke={REV_COLOR}
        strokeWidth={1.5}
        vectorEffect="non-scaling-stroke"
      />
      <polyline
        points={toPoints(profit)}
        fill="none"
        stroke={PROFIT_COLOR}
        strokeWidth={1.5}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}
