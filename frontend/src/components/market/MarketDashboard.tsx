import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import type { CardType } from '@/lib/cardPrompts'
import type { MarketOverviewData } from '@/hooks/useMarketApi'
import { useMarketApi } from '@/hooks/useMarketApi'
import { IndexCard } from './IndexCard'
import { BreadthCard } from './BreadthCard'
import { SectorHeatCard } from './SectorHeatCard'
import { NorthFlowCard } from './NorthFlowCard'
import { VolumeCard } from './VolumeCard'

interface MarketDashboardProps {
  /** 卡片「AI 分析」→ 右侧对话发起预设提问 */
  onAiAnalyze: (type: CardType) => void
}

/**
 * 市场概览看板 — 五卡网格容器（操盘模式"市场概览" Tab）。
 *
 * 布局复用 TechnicalDashboard / FundamentalDashboard 模式：
 * 左列大卡(2fr)+小卡(1fr)，右列三卡均分。
 * 数据为市场级别（非个股），一次请求聚合返回。
 */
export function MarketDashboard({ onAiAnalyze }: MarketDashboardProps) {
  const { fetchMarketOverview } = useMarketApi()
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [data, setData] = useState<MarketOverviewData | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setFailed(false)
    setData(null)
    fetchMarketOverview()
      .then((d) => {
        if (cancelled) return
        if (d) setData(d)
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
  }, [fetchMarketOverview])

  return (
    <div className="flex flex-1 min-w-0 flex-col overflow-auto p-4">
      {loading ? (
        <div className="flex flex-1 items-center justify-center gap-2">
          <Loader2 className="h-5 w-5 animate-spin text-[var(--color-text-tertiary)]" />
          <span className="text-base text-[var(--color-text-tertiary)]">正在拉取市场数据...</span>
        </div>
      ) : failed || !data ? (
        <div className="flex flex-1 items-center justify-center">
          <div className="text-center">
            <p className="text-xl font-medium text-[var(--color-text-primary)]">数据加载失败</p>
            <p className="mt-2 text-base text-gray-500">市场数据源暂不可用，请稍后重试</p>
            <button
              onClick={() => {
                setLoading(true)
                setFailed(false)
                fetchMarketOverview()
                  .then((d) => {
                    if (d) setData(d)
                    else setFailed(true)
                  })
                  .catch(() => setFailed(true))
                  .finally(() => setLoading(false))
              }}
              className="mt-3 rounded-full bg-[var(--color-accent-soft)] px-4 py-1.5 text-sm font-medium text-[var(--color-accent)] transition-colors hover:bg-[var(--color-accent)] hover:text-white"
            >
              重试
            </button>
          </div>
        </div>
      ) : (
        /* 五卡网格：左列 指数大卡(2fr)+宽度(1fr)，右列三卡均分 */
        <div className="grid min-h-0 flex-1 grid-cols-[1.7fr_1fr] grid-rows-1 gap-4">
          <div className="grid min-h-0 min-w-0 grid-rows-[2fr_1fr] gap-4">
            <div className="min-w-0 rounded-xl border border-[var(--color-border)] bg-white p-4">
              <IndexCard indices={data.indices} breadth={data.breadth} onAiAnalyze={onAiAnalyze} />
            </div>
            <div className="min-w-0 rounded-xl border border-[var(--color-border)] bg-white p-4">
              <BreadthCard breadth={data.breadth} onAiAnalyze={onAiAnalyze} />
            </div>
          </div>
          <div className="grid min-h-0 min-w-0 grid-rows-3 gap-4">
            <div className="min-w-0 rounded-xl border border-[var(--color-border)] bg-white p-4">
              <SectorHeatCard sectors={data.sectors} onAiAnalyze={onAiAnalyze} />
            </div>
            <div className="min-w-0 rounded-xl border border-[var(--color-border)] bg-white p-4">
              <NorthFlowCard northFlow={data.northFlow} onAiAnalyze={onAiAnalyze} />
            </div>
            <div className="min-w-0 rounded-xl border border-[var(--color-border)] bg-white p-4">
              <VolumeCard volume={data.volume} onAiAnalyze={onAiAnalyze} />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
