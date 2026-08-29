import { AiInterpretSection } from '@/components/technical/AiInterpretSection'
import type { IndexItem, BreadthData } from '@/hooks/useMarketApi'
import type { CardType } from '@/lib/cardPrompts'

interface IndexCardProps {
  indices: IndexItem[]
  breadth: BreadthData
  onAiAnalyze: (type: CardType) => void
}

const RED = '#dc2626'
const GREEN = '#16a34a'

/** 大盘指数卡（左列上，2fr 大卡）：指数行情表 + 市场强度摘要 */
export function IndexCard({ indices, breadth, onAiAnalyze }: IndexCardProps) {
  const totalAmount = indices.reduce((s, i) => s + i.amount, 0)
  const avgChange = indices.length > 0
    ? indices.reduce((s, i) => s + i.changePct, 0) / indices.length
    : 0
  const upDownRatio = breadth.down > 0
    ? (breadth.up / breadth.down).toFixed(2)
    : '--'
  const sentiment = avgChange > 0.5 ? '偏多' : avgChange < -0.5 ? '偏空' : '震荡'

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      {/* 标题 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-xl font-medium text-[var(--color-text-primary)]">大盘指数</h3>
          <span className="text-xs text-[var(--color-text-tertiary)]">
            {indices.length > 0 ? new Date().toLocaleDateString('zh-CN') : ''}
          </span>
        </div>
        <AiInterpretSection onAnalyze={() => onAiAnalyze('indices')} />
      </div>

      {/* 指数行情表 */}
      <div className="min-h-0 overflow-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-[var(--color-border)] text-xs text-[var(--color-text-tertiary)]">
              <th className="py-2 text-left font-normal">指数</th>
              <th className="py-2 text-right font-normal">最新价</th>
              <th className="py-2 text-right font-normal">涨跌幅</th>
              <th className="py-2 text-right font-normal">涨跌额</th>
              <th className="py-2 text-right font-normal">成交额</th>
            </tr>
          </thead>
          <tbody>
            {indices.map((item) => {
              const isUp = item.changePct >= 0
              const color = isUp ? RED : GREEN
              return (
                <tr key={item.code} className="border-b border-[var(--color-border-light)] hover:bg-[var(--color-bg-subtle)]">
                  <td className="py-2.5 text-left">
                    <span className="font-medium text-[var(--color-text-primary)]">{item.name}</span>
                    <span className="ml-1.5 text-xs text-[var(--color-text-tertiary)]">{item.code}</span>
                  </td>
                  <td className="py-2.5 text-right">
                    <span className="text-base font-semibold tabular-nums text-[var(--color-text-primary)]">
                      {item.price > 0 ? item.price.toFixed(2) : '----'}
                    </span>
                  </td>
                  <td className="py-2.5 text-right">
                    <span className="inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-semibold tabular-nums"
                      style={{ backgroundColor: isUp ? 'rgba(220,38,38,0.08)' : 'rgba(22,163,74,0.08)', color }}>
                      {isUp ? '+' : ''}{item.changePct.toFixed(2)}%
                    </span>
                  </td>
                  <td className="py-2.5 text-right">
                    <span className="text-sm tabular-nums" style={{ color }}>
                      {isUp ? '+' : ''}{item.change.toFixed(2)}
                    </span>
                  </td>
                  <td className="py-2.5 text-right">
                    <span className="text-sm tabular-nums text-[var(--color-text-secondary)]">
                      {item.amount > 0 ? fmtAmount(item.amount) : '--'}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* 底部：市场强度摘要 */}
      <div className="grid shrink-0 grid-cols-4 gap-3 rounded-lg bg-[var(--color-bg-subtle)] px-4 py-3">
        <SummaryCell
          label="全市场成交"
          value={fmtAmount(totalAmount)}
          color="var(--color-text-primary)"
        />
        <SummaryCell
          label="全市场涨跌比"
          value={upDownRatio}
          color="var(--color-text-primary)"
        />
        <SummaryCell
          label="指数均涨幅"
          value={`${avgChange >= 0 ? '+' : ''}${avgChange.toFixed(2)}%`}
          color={avgChange >= 0 ? RED : GREEN}
        />
        <SummaryCell
          label="市场情绪"
          value={sentiment}
          color={sentiment === '偏多' ? RED : sentiment === '偏空' ? GREEN : 'var(--color-text-primary)'}
        />
      </div>
    </div>
  )
}

/** 摘要指标格 */
function SummaryCell({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="flex flex-col items-center gap-0.5">
      <span className="text-xs text-[var(--color-text-secondary)]">{label}</span>
      <span className="text-base font-semibold tabular-nums" style={{ color }}>{value}</span>
    </div>
  )
}

function fmtAmount(v: number): string {
  if (v >= 1e12) return `${(v / 1e12).toFixed(1)}万亿`
  if (v >= 1e8) return `${(v / 1e8).toFixed(0)}亿`
  if (v >= 1e4) return `${(v / 1e4).toFixed(0)}万`
  return v.toFixed(0)
}
