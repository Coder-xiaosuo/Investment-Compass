import { AiInterpretSection } from '@/components/technical/AiInterpretSection'
import type { SectorItem } from '@/hooks/useMarketApi'
import type { CardType } from '@/lib/cardPrompts'

interface SectorHeatCardProps {
  sectors: SectorItem[]
  onAiAnalyze: (type: CardType) => void
}

const RED = '#dc2626'
const GREEN = '#16a34a'

/** 热点板块卡（右列上）：板块排名 + 资金流向（垂直列表 + 强度条） */
export function SectorHeatCard({ sectors, onAiAnalyze }: SectorHeatCardProps) {
  const maxAbs = Math.max(...sectors.map((s) => Math.abs(s.changePct)), 1)

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <div className="flex items-center justify-between">
        <h3 className="text-xl font-medium text-[var(--color-text-primary)]">热点板块</h3>
        <AiInterpretSection onAnalyze={() => onAiAnalyze('sectors')} />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="flex flex-col gap-1.5">
          {sectors.map((s) => {
            const isUp = s.changePct >= 0
            const barWidth = (Math.abs(s.changePct) / maxAbs) * 100
            return (
              <div key={s.name} className="flex items-center gap-2">
                <span className="w-20 shrink-0 truncate text-sm text-[var(--color-text-primary)]" title={s.name}>
                  {s.name}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="h-2 w-full rounded-full bg-[var(--color-bg-subtle)]">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${barWidth}%`,
                        backgroundColor: isUp ? RED : GREEN,
                      }}
                    />
                  </div>
                </div>
                <span className="w-16 shrink-0 text-right text-sm font-medium tabular-nums" style={{ color: isUp ? RED : GREEN }}>
                  {isUp ? '+' : ''}{s.changePct.toFixed(2)}%
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
