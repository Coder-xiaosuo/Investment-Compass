import { AiInterpretSection } from '@/components/technical/AiInterpretSection'
import type { NorthFlowData, NorthDailyFlow } from '@/hooks/useMarketApi'
import type { CardType } from '@/lib/cardPrompts'

interface NorthFlowCardProps {
  northFlow: NorthFlowData
  onAiAnalyze: (type: CardType) => void
}

const RED = '#dc2626'
const GREEN = '#16a34a'

/** 北向资金卡（右列中）：当日净额大数 + 近5日柱状迷你图 */
export function NorthFlowCard({ northFlow, onAiAnalyze }: NorthFlowCardProps) {
  const isInflow = northFlow.todayNet >= 0
  const netColor = isInflow ? RED : GREEN

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <div className="flex items-center justify-between">
        <h3 className="text-xl font-medium text-[var(--color-text-primary)]">北向资金</h3>
        <AiInterpretSection onAnalyze={() => onAiAnalyze('northflow')} />
      </div>

      {/* 当日净额大数 */}
      <div className="flex items-baseline gap-1.5">
        <span className="text-xl font-semibold tabular-nums" style={{ color: netColor }}>
          {isInflow ? '+' : ''}{fmtAmount(northFlow.todayNet)}
        </span>
        <span className="text-xs text-[var(--color-text-secondary)]">当日净{isInflow ? '流入' : '流出'}</span>
      </div>

      {/* 买入 / 卖出明细 */}
      <div className="flex gap-3 text-xs">
        <span className="text-[var(--color-text-secondary)]">
          买入 <span className="font-medium tabular-nums text-[var(--color-text-primary)]">{fmtAmount(northFlow.todayBuy)}</span>
        </span>
        <span className="text-[var(--color-text-secondary)]">
          卖出 <span className="font-medium tabular-nums text-[var(--color-text-primary)]">{fmtAmount(northFlow.todaySell)}</span>
        </span>
      </div>

      {/* 近5日流向迷你柱状图 */}
      {northFlow.dailyFlow.length > 0 && (
        <div className="min-h-0 flex-1">
          <div className="mb-1 text-xs text-[var(--color-text-tertiary)]">近5日净流向</div>
          <NorthMiniBars flows={northFlow.dailyFlow} />
        </div>
      )}
    </div>
  )
}

/** 北向资金迷你柱状图（双向：红入绿出） */
function NorthMiniBars({ flows }: { flows: NorthDailyFlow[] }) {
  const maxAbs = Math.max(...flows.map((f) => Math.abs(f.netFlow)), 1)
  return (
    <div className="relative flex h-full flex-col">
      <div className="absolute inset-x-0 top-1/2 border-t border-[var(--color-border-light)]" />
      <div className="flex h-full items-stretch">
        {flows.map((f) => {
          const isIn = f.netFlow >= 0
          const heightPct = Math.max((Math.abs(f.netFlow) / maxAbs) * 45, 4)
          return (
            <div key={f.date} className="relative flex flex-1 flex-col items-center justify-center">
              <div
                className="w-[60%] rounded-sm"
                style={{
                  backgroundColor: isIn ? RED : GREEN,
                  height: `${heightPct}%`,
                  opacity: 0.8,
                }}
              />
              <span className="mt-1 text-[9px] leading-none text-[var(--color-text-tertiary)]">
                {f.date.length >= 5 ? f.date.slice(5) : f.date}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function fmtAmount(v: number): string {
  const abs = Math.abs(v)
  if (abs >= 1e8) return `${(v / 1e8).toFixed(1)}亿`
  if (abs >= 1e4) return `${(v / 1e4).toFixed(0)}万`
  return `${v.toFixed(0)}`
}
