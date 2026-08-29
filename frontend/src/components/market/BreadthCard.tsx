import { AiInterpretSection } from '@/components/technical/AiInterpretSection'
import type { BreadthData } from '@/hooks/useMarketApi'
import type { CardType } from '@/lib/cardPrompts'

interface BreadthCardProps {
  breadth: BreadthData
  onAiAnalyze: (type: CardType) => void
}

const RED = '#dc2626'
const GREEN = '#16a34a'
const GRAY = '#9ca3af'

/** 市场宽度卡（左列下）：涨跌家数比例条 + 涨跌停家数 */
export function BreadthCard({ breadth, onAiAnalyze }: BreadthCardProps) {
  const total = breadth.total || 1
  const upPct = (breadth.up / total * 100).toFixed(1)
  const downPct = (breadth.down / total * 100).toFixed(1)
  const flatPct = (breadth.flat / total * 100).toFixed(1)
  const upDominant = breadth.up >= breadth.down

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <div className="flex items-center justify-between">
        <h3 className="text-xl font-medium text-[var(--color-text-primary)]">市场宽度</h3>
        <AiInterpretSection onAnalyze={() => onAiAnalyze('breadth')} />
      </div>

      {/* 涨跌比例条 */}
      <div className="flex flex-col gap-1.5">
        <div className="flex h-4 w-full overflow-hidden rounded-full">
          <div
            className="h-full transition-all"
            style={{ width: `${upPct}%`, backgroundColor: RED }}
          />
          <div
            className="h-full transition-all"
            style={{ width: `${flatPct}%`, backgroundColor: GRAY }}
          />
          <div
            className="h-full transition-all"
            style={{ width: `${downPct}%`, backgroundColor: GREEN }}
          />
        </div>
        <div className="flex items-center justify-between text-xs">
          <span style={{ color: RED }}>涨 {breadth.up} ({upPct}%)</span>
          <span style={{ color: GRAY }}>平 {breadth.flat} ({flatPct}%)</span>
          <span style={{ color: GREEN }}>跌 {breadth.down} ({downPct}%)</span>
        </div>
      </div>

      {/* 涨跌停家数 */}
      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col items-center gap-0.5 rounded-lg bg-[var(--color-bg-subtle)] py-2">
          <span className="text-xs text-[var(--color-text-secondary)]">涨停</span>
          <span className="text-xl font-semibold tabular-nums" style={{ color: RED }}>
            {breadth.limitUp}
          </span>
        </div>
        <div className="flex flex-col items-center gap-0.5 rounded-lg bg-[var(--color-bg-subtle)] py-2">
          <span className="text-xs text-[var(--color-text-secondary)]">跌停</span>
          <span className="text-xl font-semibold tabular-nums" style={{ color: GREEN }}>
            {breadth.limitDown}
          </span>
        </div>
      </div>

      {/* 情绪一句话 */}
      <div className="mt-auto text-center text-sm font-medium" style={{ color: upDominant ? RED : breadth.up === breadth.down ? GRAY : GREEN }}>
        {upDominant ? '市场偏多，赚钱效应较好' : breadth.up === breadth.down ? '市场平衡，方向不明朗' : '市场偏空，谨慎观望'}
      </div>
    </div>
  )
}
