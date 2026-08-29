import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { AiInterpretSection } from '@/components/technical/AiInterpretSection'
import { useFundamentalApi, type FinancialReport } from '@/hooks/useFundamentalApi'
import type { CardType } from '@/lib/cardPrompts'

interface FinancialSummaryCardProps {
  symbol: string
  /** 点击「AI 分析」→ 右侧对话发起预设提问 */
  onAiAnalyze: (type: CardType) => void
}

/** 红涨绿跌配色（中国市场标准）：营收红、净利润绿 */
const REVENUE_COLOR = '#dc2626'
const PROFIT_COLOR = '#16a34a'

/** Mock：8 季度营收/净利润（单位：亿元） */
const QUARTERLY_DATA = [
  { quarter: '2023Q1', revenue: 380, profit: 180 },
  { quarter: '2023Q2', revenue: 410, profit: 195 },
  { quarter: '2023Q3', revenue: 425, profit: 205 },
  { quarter: '2023Q4', revenue: 460, profit: 230 },
  { quarter: '2024Q1', revenue: 400, profit: 200 },
  { quarter: '2024Q2', revenue: 445, profit: 220 },
  { quarter: '2024Q3', revenue: 480, profit: 245 },
  { quarter: '2024Q4', revenue: 510, profit: 265 },
] as const

/** Mock：4 期财务指标表（含 ROE/营收/净利润/毛利率/净利率/EPS） */
const TABLE_PERIODS = ['2023Q4', '2024Q2', '2024Q3', '2024Q4'] as const
const TABLE_ROWS = [
  { label: 'ROE', values: ['15.2%', '16.8%', '17.5%', '18.5%'] },
  { label: '营收(亿)', values: ['460', '445', '480', '510'] },
  { label: '净利润(亿)', values: ['230', '220', '245', '265'] },
  { label: '毛利率', values: ['63.5%', '64.0%', '64.8%', '65.2%'] },
  { label: '净利率', values: ['50.0%', '49.4%', '51.0%', '52.0%'] },
  { label: 'EPS(元)', values: ['1.82', '1.74', '1.94', '2.10'] },
] as const

/** "YYYY-MM-DD" → "YYYYQn" */
function dateToQuarter(dateStr: string): string {
  const [y, m] = dateStr.split('-')
  return `${y}Q${Math.ceil(Number(m) / 3)}`
}

/** 财务综合卡（spec：基本面左列上，真实数据 + 失败回退 mock） */
export function FinancialSummaryCard({ symbol, onAiAnalyze }: FinancialSummaryCardProps) {
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

  // 真实数据：按 report_date ASC 排序（最早→最新），后端返回 DESC
  const reports = realData?.reports ?? []
  const sortedAsc = [...reports].sort((a, b) => a.report_date.localeCompare(b.report_date))
  const latest = sortedAsc.length > 0 ? sortedAsc[sortedAsc.length - 1] : null

  const chartData = sortedAsc.length > 0
    ? sortedAsc.map((r) => ({
        quarter: dateToQuarter(r.report_date),
        revenue: (r.revenue ?? 0) / 1e8,
        profit: (r.net_profit ?? 0) / 1e8,
      }))
    : QUARTERLY_DATA

  const tablePeriods = sortedAsc.length > 0
    ? sortedAsc.map((r) => dateToQuarter(r.report_date))
    : TABLE_PERIODS

  const tableRows = sortedAsc.length > 0
    ? [
        { label: 'ROE', values: sortedAsc.map((r) => `${(r.roe ?? 0).toFixed(1)}%`) },
        { label: '营收(亿)', values: sortedAsc.map((r) => ((r.revenue ?? 0) / 1e8).toFixed(1)) },
        { label: '净利润(亿)', values: sortedAsc.map((r) => ((r.net_profit ?? 0) / 1e8).toFixed(1)) },
        { label: '毛利率', values: sortedAsc.map((r) => `${(r.gross_margin ?? 0).toFixed(1)}%`) },
        { label: '净利率', values: sortedAsc.map((r) => `${(r.net_margin ?? 0).toFixed(1)}%`) },
        { label: 'EPS(元)', values: sortedAsc.map((r) => (r.eps ?? 0).toFixed(2)) },
      ]
    : TABLE_ROWS

  const roeValue = latest ? `${(latest.roe ?? 0).toFixed(1)}%` : '18.5%'
  const grossMarginValue = latest ? `${(latest.gross_margin ?? 0).toFixed(1)}%` : '65.2%'
  const netMarginValue = latest ? `${(latest.net_margin ?? 0).toFixed(1)}%` : '52.0%'

  return (
    <div className="relative flex h-full min-h-0 flex-col gap-2">
      {/* 标题 + DEMO 徽标 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-xl font-medium text-[var(--color-text-primary)]">财务综合</h3>
          {(failed || !realData) && (
            <span className="rounded bg-[var(--color-bg-subtle)] px-1.5 py-0.5 text-xs font-mono text-[var(--color-text-tertiary)]">DEMO</span>
          )}
        </div>
        <AiInterpretSection onAnalyze={() => onAiAnalyze('financial')} />
      </div>

      {loading ? (
        <div className="flex flex-1 items-center justify-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin text-[var(--color-text-tertiary)]" />
          <span className="text-xs text-[var(--color-text-tertiary)]">加载中...</span>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-2.5">
          {/* 顶部：ROE / 毛利率 / 净利率 三个关键指标卡 */}
          <div className="grid shrink-0 grid-cols-3 gap-2">
            <MetricCard label="ROE" value={roeValue} color={REVENUE_COLOR} />
            <MetricCard label="毛利率" value={grossMarginValue} color={PROFIT_COLOR} />
            <MetricCard label="净利率" value={netMarginValue} color={REVENUE_COLOR} />
          </div>

          {/* 中部：营收/净利润双柱状图 */}
          <div className="min-h-0 flex-1">
            <DualBarChart data={chartData} />
          </div>

          {/* 底部：4 期财务指标表 */}
          <div className="shrink-0 overflow-x-auto">
            <FinancialTable periods={tablePeriods} rows={tableRows} />
          </div>
        </div>
      )}
    </div>
  )
}

/** 指标卡：大数字 + 标签 */
function MetricCard({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-0.5 rounded-lg bg-[var(--color-bg-subtle)] px-2 py-1.5">
      <span className="text-xl font-semibold tabular-nums leading-none" style={{ color }}>{value}</span>
      <span className="text-[11px] leading-tight text-[var(--color-text-secondary)]">{label}</span>
    </div>
  )
}

/** 营收/净利润双柱状图（HTML/CSS 实现，红涨绿跌） */
function DualBarChart({ data }: { data: readonly { quarter: string; revenue: number; profit: number }[] }) {
  const maxValue = Math.max(...data.map((d) => Math.max(d.revenue, d.profit)))
  return (
    <div className="flex h-full flex-col">
      {/* 图例 */}
      <div className="mb-1.5 flex items-center gap-3 text-xs">
        <span className="flex items-center gap-1 text-[var(--color-text-secondary)]">
          <span className="inline-block h-2 w-2 rounded-sm" style={{ backgroundColor: REVENUE_COLOR }} />
          营收
        </span>
        <span className="flex items-center gap-1 text-[var(--color-text-secondary)]">
          <span className="inline-block h-2 w-2 rounded-sm" style={{ backgroundColor: PROFIT_COLOR }} />
          净利润
        </span>
        <span className="ml-auto text-[var(--color-text-tertiary)]">亿元</span>
      </div>
      {/* 柱体区 */}
      <div className="flex min-h-0 flex-1 items-end gap-1">
        {data.map((d) => (
          <div key={d.quarter} className="flex h-full flex-1 flex-col">
            <div className="flex h-full items-end justify-center gap-0.5">
              <div
                className="w-[45%] rounded-t-sm"
                style={{ height: `${(d.revenue / maxValue) * 100}%`, backgroundColor: REVENUE_COLOR }}
                title={`${d.quarter} 营收 ${d.revenue}亿`}
              />
              <div
                className="w-[45%] rounded-t-sm"
                style={{ height: `${(d.profit / maxValue) * 100}%`, backgroundColor: PROFIT_COLOR }}
                title={`${d.quarter} 净利润 ${d.profit}亿`}
              />
            </div>
            <span className="mt-1 text-center text-[10px] leading-none text-[var(--color-text-tertiary)]">{d.quarter}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/** 4 期财务指标表 */
function FinancialTable({
  periods,
  rows,
}: {
  periods: readonly string[]
  rows: readonly { label: string; values: readonly string[] }[]
}) {
  return (
    <table className="w-full border-collapse text-xs">
      <thead>
        <tr className="text-[var(--color-text-tertiary)]">
          <th className="py-1 pr-2 text-left font-normal">指标</th>
          {periods.map((p) => (
            <th key={p} className="py-1 text-right font-normal">{p}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.label} className="border-t border-[var(--color-border)]">
            <td className="py-1 pr-2 text-left text-[var(--color-text-primary)]">{row.label}</td>
            {row.values.map((v, i) => (
              <td key={i} className="py-1 text-right tabular-nums text-[var(--color-text-secondary)]">{v}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
