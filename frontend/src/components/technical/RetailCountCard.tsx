import { useEffect, useMemo, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { useDemoApi, type ShareholderRow } from '@/hooks/useDemoApi'
import { AiInterpretSection } from './AiInterpretSection'
import type { CardType } from '@/lib/cardPrompts'

interface RetailCountCardProps {
  symbol: string
  /** 点击「AI 分析」→ 右侧对话发起预设提问 */
  onAiAnalyze: (type: CardType) => void
}

/** 增户绿 / 减户红（户数增=筹码分散偏空=绿；户数减=筹码集中偏多=红，符合中国市场红涨绿跌直觉） */
const GAIN = '#16a34a'
const LOSS = '#dc2626'
const FLAT = '#9ca3af'

/** 散户数量卡（spec R3）：股东户数周期柱状图，DEMO 数据源 */
export function RetailCountCard({ symbol, onAiAnalyze }: RetailCountCardProps) {
  const { fetchShareholders } = useDemoApi()
  const [rows, setRows] = useState<ShareholderRow[]>([])
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [hover, setHover] = useState<number | null>(null)
  // 失败后手动重试：自增触发重新请求
  const [retryTick, setRetryTick] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setFailed(false)
    setRows([])
    setHover(null)
    if (!symbol) {
      setLoading(false)
      return
    }
    fetchShareholders(symbol)
      .then((data) => {
        if (cancelled) return
        if (!data || data.rows.length === 0) setFailed(true)
        else setRows(data.rows)
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
  }, [symbol, fetchShareholders, retryTick])

  // 柱高归一化（相对 count 区间），保留最小可见高度
  const { minCount, maxCount } = useMemo(() => {
    if (rows.length === 0) return { minCount: 0, maxCount: 0 }
    const counts = rows.map((r) => r.count)
    return { minCount: Math.min(...counts), maxCount: Math.max(...counts) }
  }, [rows])

  const heightPct = (count: number) => {
    if (maxCount === minCount) return 60
    return 12 + ((count - minCount) / (maxCount - minCount)) * 78
  }

  const latest = rows[rows.length - 1]
  const prev = rows[rows.length - 2]
  const latestChangePct = latest && prev ? ((latest.count - prev.count) / prev.count) * 100 : null

  const fmtCount = (v: number) => (v >= 1e4 ? `${(v / 1e4).toFixed(1)}万` : String(Math.round(v)))

  return (
    <div className="relative flex h-full min-h-0 flex-col gap-2">
      {/* 标题 + DEMO 徽标 */}
      <div className="flex items-center justify-between">
        <h3 className="text-xl font-medium text-[var(--color-text-primary)]">散户数量</h3>
        <AiInterpretSection onAnalyze={() => onAiAnalyze('shareholder')} />
      </div>

      {/* 最新一期概览 */}
      <div className="flex items-baseline gap-2">
        <span className="text-xl font-semibold tabular-nums text-[var(--color-text-primary)]">
          {latest ? fmtCount(latest.count) : '--'}
        </span>
        {latestChangePct != null && (
          <span className="text-xs tabular-nums" style={{ color: latestChangePct >= 0 ? GAIN : LOSS }}>
            {latestChangePct >= 0 ? '↑' : '↓'} {Math.abs(latestChangePct).toFixed(2)}%
          </span>
        )}
        <span className="text-xs text-[var(--color-text-tertiary)]">户 · {latest?.date ?? ''}</span>
      </div>

      {/* 柱状图区 */}
      <div className="relative min-h-0 flex-1">
        {loading ? (
          <div className="flex h-full items-center justify-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin text-[var(--color-text-tertiary)]" />
            <span className="text-xs text-[var(--color-text-tertiary)]">数据源较慢，正在加载…</span>
          </div>
        ) : failed || rows.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2">
            <span className="text-xs text-[var(--color-text-tertiary)]">数据源加载失败</span>
            <button
              onClick={() => setRetryTick((t) => t + 1)}
              className="rounded-full bg-[var(--color-accent-soft)] px-3 py-1 text-xs font-medium text-[var(--color-accent)] transition-colors hover:bg-[var(--color-accent)] hover:text-white"
            >
              重试
            </button>
          </div>
        ) : (
          <div className="flex h-full min-w-0 items-end gap-[2px]">
            {rows.map((r, i) => {
              const barColor = r.change > 0 ? GAIN : r.change < 0 ? LOSS : FLAT
              const isHover = hover === i
              return (
                <div
                  key={`${r.date}-${i}`}
                  className="relative flex h-full min-w-0 flex-1 flex-col justify-end"
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover(null)}
                >
                  <div
                    className="w-full rounded-t-sm transition-opacity"
                    style={{ height: `${heightPct(r.count)}%`, backgroundColor: barColor, opacity: isHover ? 1 : 0.75 }}
                  />
                  {isHover && (
                    <div className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1 -translate-x-1/2 whitespace-nowrap rounded-md border border-[var(--color-border)] bg-white px-2 py-1 shadow-md">
                      <p className="text-xs text-[var(--color-text-secondary)]">{r.date}</p>
                      <p className="text-xs font-medium tabular-nums text-[var(--color-text-primary)]">
                        {fmtCount(r.count)} 户
                      </p>
                      <p className="text-xs tabular-nums" style={{ color: barColor }}>
                        {r.change == null
                          ? '--'
                          : `${r.change >= 0 ? '+' : ''}${Math.round(r.change)} 户${
                              r.change_pct != null
                                ? ` (${r.change_pct >= 0 ? '+' : ''}${r.change_pct.toFixed(2)}%)`
                                : ''
                            }`}
                      </p>
                    </div>
                  )}
                  {/* 日期标签：每根柱均显示 MM-DD；柱宽不足时截断而非撑破卡片 */}
                  <span className="mt-0.5 block w-full truncate text-center text-xs text-[var(--color-text-tertiary)]">
                    {r.date.slice(5)}
                  </span>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
