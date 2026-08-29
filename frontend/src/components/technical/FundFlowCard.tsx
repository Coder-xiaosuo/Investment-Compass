import { useEffect, useMemo, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { useDemoApi, type FundFlowDailyRow } from '@/hooks/useDemoApi'
import { AiInterpretSection } from './AiInterpretSection'
import type { CardType } from '@/lib/cardPrompts'

interface FundFlowCardProps {
  symbol: string
  /** 点击「AI 分析」→ 右侧对话发起预设提问 */
  onAiAnalyze: (type: CardType) => void
}

/** 红入（主力净流入）/ 绿出（净流出），符合中国市场红涨绿跌 */
const INFLOW = '#dc2626'
const OUTFLOW = '#16a34a'
const FLAT = '#9ca3af'

/** 大单资金流向卡（spec R5，DEMO）：daily 完整模式 / snapshot 降级显当日 */
export function FundFlowCard({ symbol, onAiAnalyze }: FundFlowCardProps) {
  const { fetchFundFlow } = useDemoApi()
  const [data, setData] = useState<Awaited<ReturnType<typeof fetchFundFlow>>>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  // 失败后手动重试：自增触发重新请求
  const [retryTick, setRetryTick] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setFailed(false)
    setData(null)
    if (!symbol) {
      setLoading(false)
      return
    }
    fetchFundFlow(symbol, 10)
      .then((d) => {
        if (cancelled) return
        if (!d) setFailed(true)
        else setData(d)
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
  }, [symbol, fetchFundFlow, retryTick])

  const mode = data?.mode ?? null

  return (
    <div className="relative flex h-full min-h-0 flex-col gap-2">
      {/* 标题 + AI 分析按钮 */}
      <div className="flex items-center justify-between">
        <h3 className="text-xl font-medium text-[var(--color-text-primary)]">大单资金流向</h3>
        <AiInterpretSection onAnalyze={() => onAiAnalyze('fundflow')} />
      </div>

      {loading ? (
        <div className="flex flex-1 items-center justify-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin text-[var(--color-text-tertiary)]" />
          <span className="text-xs text-[var(--color-text-tertiary)]">数据源较慢，正在加载…</span>
        </div>
      ) : failed || !data ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2">
          <span className="text-xs text-[var(--color-text-tertiary)]">数据源加载失败</span>
          <button
            onClick={() => setRetryTick((t) => t + 1)}
            className="rounded-full bg-[var(--color-accent-soft)] px-3 py-1 text-xs font-medium text-[var(--color-accent)] transition-colors hover:bg-[var(--color-accent)] hover:text-white"
          >
            重试
          </button>
        </div>
      ) : mode === 'daily' ? (
        <DailyView rows={data.daily ?? []} summary={data.summary} />
      ) : (
        <SnapshotView snapshot={data.snapshot} />
      )}
    </div>
  )
}

/** daily 模式：左 3/5/10 日净流入 + 右每日主力净流入柱状图 */
function DailyView({ rows, summary }: { rows: FundFlowDailyRow[]; summary?: { '3d'?: number; '5d'?: number; '10d'?: number } }) {
  const [hover, setHover] = useState<number | null>(null)
  const { maxAbs } = useMemo(() => {
    const nets = rows.map((r) => Math.abs(r.main_net ?? 0))
    return { maxAbs: nets.length ? Math.max(...nets, 1) : 1 }
  }, [rows])

  const fmtAmount = (v: number | undefined) => {
    if (v == null || isNaN(v)) return '--'
    const abs = Math.abs(v)
    const sign = v >= 0 ? '+' : '-'
    if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(2)}亿`
    if (abs >= 1e4) return `${sign}${(abs / 1e4).toFixed(0)}万`
    return `${sign}${abs.toFixed(0)}`
  }

  const summaryItems: { label: string; value: number | undefined }[] = [
    { label: '近3日', value: summary?.['3d'] },
    { label: '近5日', value: summary?.['5d'] },
    { label: '近10日', value: summary?.['10d'] },
  ]

  return (
    <div className="flex min-h-0 flex-1 gap-3">
      {/* 左：3/5/10 日净流入 */}
      <div className="flex w-[42%] shrink-0 flex-col justify-center gap-2">
        {summaryItems.map((item) => (
          <div key={item.label} className="flex items-center justify-between text-xs">
            <span className="text-[var(--color-text-secondary)]">{item.label}</span>
            <span
              className="font-medium tabular-nums"
              style={{ color: item.value == null ? FLAT : item.value >= 0 ? INFLOW : OUTFLOW }}
            >
              {item.value == null ? '--' : fmtAmount(item.value)}
            </span>
          </div>
        ))}
      </div>

      {/* 右：每日主力净流入双向柱（红入绿出） */}
      <div className="min-w-0 flex-1">
        <div className="relative h-full">
          {/* 中线 */}
          <div className="absolute inset-x-0 top-1/2 border-t border-[var(--color-border-light)]" />
          <div className="flex h-full items-stretch">
            {rows.map((r, i) => {
              const net = r.main_net ?? 0
              const barColor = net > 0 ? INFLOW : net < 0 ? OUTFLOW : FLAT
              const heightPct = Math.max((Math.abs(net) / maxAbs) * 44, 3)
              const isHover = hover === i
              return (
                <div
                  key={r.date}
                  className="relative flex-1"
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover(null)}
                >
                  <div
                    className="absolute left-1/2 w-[70%] -translate-x-1/2 rounded-sm transition-opacity"
                    style={{
                      backgroundColor: barColor,
                      opacity: isHover ? 1 : 0.75,
                      ...(net >= 0 ? { bottom: '50%', height: `${heightPct}%` } : { top: '50%', height: `${heightPct}%` }),
                    }}
                  />
                  {isHover && (
                    <div className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1 -translate-x-1/2 whitespace-nowrap rounded-md border border-[var(--color-border)] bg-white px-2 py-1 shadow-md">
                      <p className="text-xs text-[var(--color-text-secondary)]">{r.date}</p>
                      <p className="text-xs font-medium tabular-nums" style={{ color: barColor }}>
                        主力净流入 {fmtAmount(net)}
                      </p>
                      <p className="text-xs text-[var(--color-text-secondary)]">
                        净占比 {r.main_net_pct != null ? `${r.main_net_pct.toFixed(2)}%` : '--'}
                      </p>
                    </div>
                  )}
                  <span className="absolute inset-x-0 bottom-0 text-center text-xs text-[var(--color-text-tertiary)]">
                    {r.date.slice(5)}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}

/** snapshot 模式：降级显当日净额/流入/流出，历史汇总标"—" + 降级提示 */
function SnapshotView({ snapshot }: { snapshot?: { name?: string; price?: string; change_pct?: string; inflow?: string; outflow?: string; net?: string; amount?: string } }) {
  const net = snapshot?.net ?? '--'
  const netIsInflow = typeof net === 'string' && !net.startsWith('-')

  return (
    <div className="flex min-h-0 flex-1 flex-col justify-center gap-2.5">
      {/* 降级提示 */}
      <div className="rounded-md bg-amber-50 px-2 py-1 text-xs text-amber-700">
        数据源降级 · 同花顺当日快照（东财逐日不可用）
      </div>
      {/* 当日净额 */}
      <div className="flex items-baseline gap-1.5">
        <span className="text-xl font-semibold tabular-nums" style={{ color: netIsInflow ? INFLOW : OUTFLOW }}>
          {snapshot?.net ?? '--'}
        </span>
        <span className="text-xs text-[var(--color-text-secondary)]">当日主力净额</span>
      </div>
      {/* 流入 / 流出 */}
      <div className="flex gap-3 text-xs">
        <div className="flex items-center gap-1">
          <span className="text-[var(--color-text-secondary)]">流入</span>
          <span className="font-medium tabular-nums" style={{ color: INFLOW }}>{snapshot?.inflow ?? '--'}</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="text-[var(--color-text-secondary)]">流出</span>
          <span className="font-medium tabular-nums" style={{ color: OUTFLOW }}>{snapshot?.outflow ?? '--'}</span>
        </div>
      </div>
      <div className="flex items-center gap-1 text-xs">
        <span className="text-[var(--color-text-secondary)]">成交额</span>
        <span className="font-medium tabular-nums text-[var(--color-text-primary)]">{snapshot?.amount ?? '--'}</span>
      </div>
      {/* 历史汇总降级 */}
      <div className="mt-1 flex gap-3 border-t border-[var(--color-border-light)] pt-2 text-xs">
        {['近3日', '近5日', '近10日'].map((label) => (
          <div key={label} className="flex items-center gap-1">
            <span className="text-[var(--color-text-secondary)]">{label}</span>
            <span className="font-medium tabular-nums text-[var(--color-text-tertiary)]">—</span>
          </div>
        ))}
      </div>
    </div>
  )
}
