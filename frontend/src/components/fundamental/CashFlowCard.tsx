import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { AiInterpretSection } from '@/components/technical/AiInterpretSection'
import { useFundamentalApi, type FinancialReport } from '@/hooks/useFundamentalApi'
import type { CardType } from '@/lib/cardPrompts'

interface CashFlowCardProps {
  symbol: string
  /** 点击「AI 分析」→ 右侧对话发起预设提问 */
  onAiAnalyze: (type: CardType) => void
}

/** 三类现金流配色：经营红、投资蓝、筹资灰 */
const OPERATING_COLOR = '#dc2626'
const INVESTING_COLOR = '#3b82f6'
const FINANCING_COLOR = '#9ca3af'

/** Mock：8 季度经营/投资/筹资三类现金流（单位：亿元） */
const CASHFLOW_DATA = [
  { quarter: '2023Q1', operating: 210, investing: -80, financing: -50 },
  { quarter: '2023Q2', operating: 225, investing: -95, financing: -40 },
  { quarter: '2023Q3', operating: 240, investing: -70, financing: -60 },
  { quarter: '2023Q4', operating: 270, investing: -110, financing: -45 },
  { quarter: '2024Q1', operating: 230, investing: -85, financing: -55 },
  { quarter: '2024Q2', operating: 255, investing: -100, financing: -35 },
  { quarter: '2024Q3', operating: 280, investing: -90, financing: -65 },
  { quarter: '2024Q4', operating: 300, investing: -120, financing: -50 },
] as const

/** "YYYY-MM-DD" → "YYYYQn" */
function dateToQuarter(dateStr: string): string {
  const [y, m] = dateStr.split('-')
  return `${y}Q${Math.ceil(Number(m) / 3)}`
}

/** 现金流结构卡（spec：基本面左列下，真实数据 + 失败回退 mock） */
export function CashFlowCard({ symbol, onAiAnalyze }: CashFlowCardProps) {
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
  const latest = sortedAsc.length > 0 ? sortedAsc[sortedAsc.length - 1] : null

  // 后端 abstract 仅有 cash_flow_op，投资/筹资现金流暂无字段，用 0 填充
  const chartData = sortedAsc.length > 0
    ? sortedAsc.map((r) => ({
        quarter: dateToQuarter(r.report_date),
        operating: (r.cash_flow_op ?? 0) / 1e8,
        investing: 0,
        financing: 0,
      }))
    : CASHFLOW_DATA

  const cashRatioValue = latest ? (latest.cash_ratio ?? 0).toFixed(2) : '0.85'
  const opProfitRatioValue = latest ? (latest.cash_ratio ?? 0).toFixed(2) : '1.15'

  return (
    <div className="relative flex h-full min-h-0 flex-col gap-2">
      {/* 标题 + DEMO 徽标 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-xl font-medium text-[var(--color-text-primary)]">现金流结构</h3>
          {(failed || !realData) && (
            <span className="rounded bg-[var(--color-bg-subtle)] px-1.5 py-0.5 text-xs font-mono text-[var(--color-text-tertiary)]">DEMO</span>
          )}
        </div>
        <AiInterpretSection onAnalyze={() => onAiAnalyze('cashflow')} />
      </div>

      {loading ? (
        <div className="flex flex-1 items-center justify-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin text-[var(--color-text-tertiary)]" />
          <span className="text-xs text-[var(--color-text-tertiary)]">加载中...</span>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-2.5">
          {/* 顶部：现金比率 / 经营现金流与净利润比 两个指标卡 */}
          <div className="grid shrink-0 grid-cols-2 gap-2">
            <MetricCard label="现金比率" value={cashRatioValue} color={OPERATING_COLOR} />
            <MetricCard label="经营/净利比" value={opProfitRatioValue} color={INVESTING_COLOR} />
          </div>

          {/* 中部：三类现金流堆叠柱状图 */}
          <div className="min-h-0 flex-1">
            <StackedCashFlowChart data={chartData} />
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

/** 三类现金流堆叠柱状图（HTML/CSS 实现，绝对值堆叠） */
function StackedCashFlowChart({
  data,
}: {
  data: readonly { quarter: string; operating: number; investing: number; financing: number }[]
}) {
  const maxValue = Math.max(
    ...data.map((d) => d.operating + Math.abs(d.investing) + Math.abs(d.financing)),
  )
  return (
    <div className="flex h-full flex-col">
      {/* 图例 */}
      <div className="mb-1.5 flex items-center gap-3 text-xs">
        <span className="flex items-center gap-1 text-[var(--color-text-secondary)]">
          <span className="inline-block h-2 w-2 rounded-sm" style={{ backgroundColor: OPERATING_COLOR }} />
          经营
        </span>
        <span className="flex items-center gap-1 text-[var(--color-text-secondary)]">
          <span className="inline-block h-2 w-2 rounded-sm" style={{ backgroundColor: INVESTING_COLOR }} />
          投资
        </span>
        <span className="flex items-center gap-1 text-[var(--color-text-secondary)]">
          <span className="inline-block h-2 w-2 rounded-sm" style={{ backgroundColor: FINANCING_COLOR }} />
          筹资
        </span>
        <span className="ml-auto text-[var(--color-text-tertiary)]">亿元</span>
      </div>
      {/* 柱体区 */}
      <div className="flex min-h-0 flex-1 items-end gap-1">
        {data.map((d) => {
          const operatingH = (d.operating / maxValue) * 100
          const investingH = (Math.abs(d.investing) / maxValue) * 100
          const financingH = (Math.abs(d.financing) / maxValue) * 100
          return (
            <div key={d.quarter} className="flex h-full flex-1 flex-col">
              <div className="flex h-full flex-col-reverse justify-start overflow-hidden rounded-t-sm">
                <div
                  className="w-full"
                  style={{ height: `${operatingH}%`, backgroundColor: OPERATING_COLOR }}
                  title={`${d.quarter} 经营现金流 ${d.operating}亿`}
                />
                <div
                  className="w-full"
                  style={{ height: `${investingH}%`, backgroundColor: INVESTING_COLOR }}
                  title={`${d.quarter} 投资现金流 ${d.investing}亿`}
                />
                <div
                  className="w-full"
                  style={{ height: `${financingH}%`, backgroundColor: FINANCING_COLOR }}
                  title={`${d.quarter} 筹资现金流 ${d.financing}亿`}
                />
              </div>
              <span className="mt-1 text-center text-[10px] leading-none text-[var(--color-text-tertiary)]">{d.quarter}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
