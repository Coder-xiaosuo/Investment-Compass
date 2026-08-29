import { AiInterpretSection } from '@/components/technical/AiInterpretSection'
import type { VolumeData } from '@/hooks/useMarketApi'
import type { CardType } from '@/lib/cardPrompts'

interface VolumeCardProps {
  volume: VolumeData
  onAiAnalyze: (type: CardType) => void
}

const RED = '#dc2626'
const GREEN = '#16a34a'

/** 成交量卡（右列下）：当日成交额大数 + 近10日成交量柱状迷你图 */
export function VolumeCard({ volume, onAiAnalyze }: VolumeCardProps) {
  const isUp = volume.amountChange >= 0
  const chgColor = isUp ? RED : GREEN

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <div className="flex items-center justify-between">
        <h3 className="text-xl font-medium text-[var(--color-text-primary)]">大盘成交</h3>
        <AiInterpretSection onAnalyze={() => onAiAnalyze('mkvolume')} />
      </div>

      {/* 当日成交额大数 */}
      <div className="flex items-baseline gap-1.5">
        <span className="text-xl font-semibold tabular-nums text-[var(--color-text-primary)]">
          {fmtAmount(volume.todayAmount)}
        </span>
        <span className="text-xs" style={{ color: chgColor }}>
          {isUp ? '+' : ''}{volume.amountChange.toFixed(1)}%
        </span>
      </div>

      {/* 当日成交量 */}
      <div className="text-xs text-[var(--color-text-secondary)]">
        成交量 <span className="font-medium tabular-nums text-[var(--color-text-primary)]">{fmtVolume(volume.todayVolume)}</span>
      </div>

      {/* 近10日成交额趋势迷你图 */}
      {volume.daily.length > 0 && (
        <div className="min-h-0 flex-1">
          <div className="mb-1 text-xs text-[var(--color-text-tertiary)]">近10日成交额</div>
          <VolumeMiniChart daily={volume.daily} />
        </div>
      )}
    </div>
  )
}

/** 成交额迷你折线图（SVG） */
function VolumeMiniChart({ daily }: { daily: { date: string; amount: number }[] }) {
  const W = 100
  const H = 36
  const padX = 4
  const padY = 3

  const max = Math.max(...daily.map((d) => d.amount))
  const min = Math.min(...daily.map((d) => d.amount))
  const range = max - min || 1

  const points = daily
    .map((d, i) => {
      const x = padX + (i / (daily.length - 1)) * (W - padX * 2)
      const y = H - padY - ((d.amount - min) / range) * (H - padY * 2)
      return `${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(' ')

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-full w-full" preserveAspectRatio="none">
      <polyline
        points={points}
        fill="none"
        stroke="#3b82f6"
        strokeWidth={1.5}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}

function fmtAmount(v: number): string {
  if (v >= 1e12) return `${(v / 1e12).toFixed(1)}万亿`
  if (v >= 1e8) return `${(v / 1e8).toFixed(0)}亿`
  if (v >= 1e4) return `${(v / 1e4).toFixed(0)}万`
  return v.toFixed(0)
}

function fmtVolume(v: number): string {
  if (v >= 1e8) return `${(v / 1e8).toFixed(1)}亿手`
  if (v >= 1e4) return `${(v / 1e4).toFixed(0)}万手`
  return v.toFixed(0)
}
