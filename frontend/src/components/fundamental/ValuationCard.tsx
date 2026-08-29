import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { AiInterpretSection } from '@/components/technical/AiInterpretSection'
import { useFundamentalApi, type ValuationData } from '@/hooks/useFundamentalApi'
import type { CardType } from '@/lib/cardPrompts'

interface ValuationCardProps {
  symbol: string
  /** 点击「AI 分析」→ 右侧对话发起预设提问 */
  onAiAnalyze: (type: CardType) => void
}

/** 估值水平卡（spec，真实数据 + 失败回退 mock）：PE/PB/PS + 历史分位色阶 + 市值标签 */
export function ValuationCard({ symbol, onAiAnalyze }: ValuationCardProps) {
  const { fetchValuation } = useFundamentalApi()
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [realData, setRealData] = useState<ValuationData | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setFailed(false)
    setRealData(null)
    if (!symbol) {
      setLoading(false)
      return
    }
    fetchValuation(symbol)
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
  }, [symbol, fetchValuation])

  // 真实数据：直接使用后端字段（null → "--"）；失败时回退 mock
  const peTtm = realData ? realData.pe_ttm : 35.2
  const peStatic = realData ? realData.pe_static : 38.1
  const pb = realData ? realData.pb : 8.5
  const ps = realData ? realData.ps_ttm : 12.3
  // 分位值：后端暂无历史分位数据，保留 mock
  const pePercentile = 75
  const pbPercentile = 60
  const totalMv = realData
    ? (realData.market_cap != null ? `${(realData.market_cap / 1e12).toFixed(2)}万亿` : '--')
    : '2.1万亿'
  const circMv = realData
    ? (realData.float_market_cap != null ? `${(realData.float_market_cap / 1e12).toFixed(2)}万亿` : '--')
    : '2.0万亿'

  return (
    <div className="relative flex h-full min-h-0 flex-col gap-2">
      {/* 标题 + DEMO 徽标 + AI 分析 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-xl font-medium text-[var(--color-text-primary)]">估值水平</h3>
          {(failed || !realData) && (
            <span className="rounded bg-[var(--color-bg-subtle)] px-1.5 py-0.5 text-xs font-mono text-[var(--color-text-tertiary)]">DEMO</span>
          )}
        </div>
        <AiInterpretSection onAnalyze={() => onAiAnalyze('valuation')} />
      </div>

      {loading ? (
        <div className="flex flex-1 items-center justify-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin text-[var(--color-text-tertiary)]" />
          <span className="text-xs text-[var(--color-text-tertiary)]">加载中...</span>
        </div>
      ) : (
        <>
          {/* 2x2 网格：PE(TTM) / PE(静态) / PB / PS 大字展示 */}
          <div className="grid grid-cols-2 gap-x-4 gap-y-2">
            <MetricCell label="PE(TTM)" value={peTtm} />
            <MetricCell label="PE(静态)" value={peStatic} />
            <MetricCell label="PB" value={pb} />
            <MetricCell label="PS" value={ps} />
          </div>

          {/* 分位色阶条（div 宽度模拟，偏高用 warning 色） */}
          <div className="flex flex-col gap-1.5">
            <PercentileBar label="PE 分位" percentile={pePercentile} />
            <PercentileBar label="PB 分位" percentile={pbPercentile} />
          </div>

          {/* 市值标签（底部） */}
          <div className="mt-auto flex items-center justify-between border-t border-[var(--color-border-light)] pt-1.5 text-xs">
            <span className="text-[var(--color-text-secondary)]">
              总市值 <span className="font-medium tabular-nums text-[var(--color-text-primary)]">{totalMv}</span>
            </span>
            <span className="text-[var(--color-text-secondary)]">
              流通 <span className="font-medium tabular-nums text-[var(--color-text-primary)]">{circMv}</span>
            </span>
          </div>
        </>
      )}
    </div>
  )
}

/** 指标数字大字展示（null → "--"） */
function MetricCell({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-[var(--color-text-secondary)]">{label}</span>
      <span className="text-lg font-semibold tabular-nums text-[var(--color-text-primary)]">
        {value != null ? value.toFixed(1) : '--'}
      </span>
    </div>
  )
}

/** 分位色阶条：div 宽度模拟，偏高用 warning 色 */
function PercentileBar({ label, percentile }: { label: string; percentile: number }) {
  return (
    <div>
      <div className="mb-0.5 flex items-center justify-between text-xs">
        <span className="text-[var(--color-text-secondary)]">{label}</span>
        <span className="font-medium tabular-nums text-[var(--color-warning)]">{percentile}%</span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-[var(--color-bg-subtle)]">
        <div className="h-full rounded-full bg-[var(--color-warning)]" style={{ width: `${percentile}%` }} />
      </div>
    </div>
  )
}
