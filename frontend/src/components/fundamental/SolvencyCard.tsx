import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { AiInterpretSection } from '@/components/technical/AiInterpretSection'
import { useFundamentalApi, type FinancialReport } from '@/hooks/useFundamentalApi'
import type { CardType } from '@/lib/cardPrompts'

interface SolvencyCardProps {
  symbol: string
  /** 点击「AI 分析」→ 右侧对话发起预设提问 */
  onAiAnalyze: (type: CardType) => void
}

/** 偿债指标颜色编码：好=绿 / 中=黄 / 差=红 */
const GOOD = '#16a34a'
const MID = '#f59e0b'
const BAD = '#dc2626'

/** 偿债 & 运营卡（spec，真实数据 + 失败回退 mock）：偿债指标 + 期间费用率趋势 */
export function SolvencyCard({ symbol, onAiAnalyze }: SolvencyCardProps) {
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

  // 偿债指标：最新一期；期间费用率趋势：4 期
  const debtRatio = latest ? (latest.debt_ratio ?? 18.5) : 18.5
  const currentRatio = latest ? (latest.current_ratio ?? 3.2) : 3.2
  const quickRatio = latest ? (latest.quick_ratio ?? 2.8) : 2.8
  const expenseRate = latest ? (latest.cost_ratio ?? 8.5) : 8.5
  const expenseTrend = sortedAsc.length > 0
    ? sortedAsc.map((r) => r.cost_ratio ?? 0)
    : [9.2, 8.8, 8.5, 8.5]

  return (
    <div className="relative flex h-full min-h-0 flex-col gap-2">
      {/* 标题 + DEMO 徽标 + AI 分析 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-xl font-medium text-[var(--color-text-primary)]">偿债 & 运营</h3>
          {(failed || !realData) && (
            <span className="rounded bg-[var(--color-bg-subtle)] px-1.5 py-0.5 text-xs font-mono text-[var(--color-text-tertiary)]">DEMO</span>
          )}
        </div>
        <AiInterpretSection onAnalyze={() => onAiAnalyze('solvency')} />
      </div>

      {loading ? (
        <div className="flex flex-1 items-center justify-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin text-[var(--color-text-tertiary)]" />
          <span className="text-xs text-[var(--color-text-tertiary)]">加载中...</span>
        </div>
      ) : (
        <>
          {/* 3 偿债指标卡（大字数字 + 警示色） */}
          <div className="grid grid-cols-3 gap-2">
            <SolvencyMetric label="资产负债率" value={`${debtRatio.toFixed(1)}%`} color={debtRatioColor(debtRatio)} />
            <SolvencyMetric label="流动比率" value={currentRatio.toFixed(1)} color={currentRatioColor(currentRatio)} />
            <SolvencyMetric label="速动比率" value={quickRatio.toFixed(1)} color={quickRatioColor(quickRatio)} />
          </div>

          {/* 期间费用率趋势小柱状图（4期，CSS div 模拟） */}
          <div className="flex min-h-0 flex-1 flex-col gap-1">
            <div className="flex items-center justify-between text-xs">
              <span className="text-[var(--color-text-secondary)]">期间费用率趋势</span>
              <span className="font-medium tabular-nums text-[var(--color-text-primary)]">{expenseRate.toFixed(1)}%</span>
            </div>
            <ExpenseTrendChart data={expenseTrend} />
          </div>
        </>
      )}
    </div>
  )
}

/** 偿债指标数字卡 */
function SolvencyMetric({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-[var(--color-text-secondary)]">{label}</span>
      <span className="text-lg font-semibold tabular-nums" style={{ color }}>
        {value}
      </span>
    </div>
  )
}

/** 期间费用率趋势柱状图（CSS div 模拟，4期） */
function ExpenseTrendChart({ data }: { data: number[] }) {
  const max = Math.max(...data)
  const min = Math.min(...data) * 0.8 // 放大差异，让下降趋势更直观
  const range = max - min || 1
  return (
    <div className="flex min-h-0 flex-1 items-stretch gap-1.5">
      {data.map((v, i) => {
        const heightPct = Math.max(((v - min) / range) * 95, 8)
        return (
          <div key={i} className="relative flex-1">
            <span className="absolute left-1/2 top-0 -translate-x-1/2 text-xs tabular-nums text-[var(--color-text-tertiary)]">
              {v}
            </span>
            <div
              className="absolute bottom-0 left-1/2 w-2/3 -translate-x-1/2 rounded-t-sm bg-[#3b82f6]"
              style={{ height: `${heightPct}%` }}
            />
          </div>
        )
      })}
    </div>
  )
}

/** 资产负债率颜色：<50% 好，<70% 中，≥70% 差 */
function debtRatioColor(ratio: number): string {
  if (ratio < 50) return GOOD
  if (ratio < 70) return MID
  return BAD
}

/** 流动比率颜色：≥2 好，≥1 中，<1 差 */
function currentRatioColor(ratio: number): string {
  if (ratio >= 2) return GOOD
  if (ratio >= 1) return MID
  return BAD
}

/** 速动比率颜色：≥1 好，≥0.5 中，<0.5 差 */
function quickRatioColor(ratio: number): string {
  if (ratio >= 1) return GOOD
  if (ratio >= 0.5) return MID
  return BAD
}
