import { KLineCard } from './KLineCard'
import { RetailCountCard } from './RetailCountCard'
import { ChipCostCard } from './ChipCostCard'
import { FundFlowCard } from './FundFlowCard'
import { TargetPriceCard } from './TargetPriceCard'
import { AiInterpretSection } from './AiInterpretSection'
import type { DecisionCardData } from '@/types'
import type { CardType } from '@/lib/cardPrompts'

interface TechnicalDashboardProps {
  symbol: string
  onSymbolChange: (symbol: string) => void
  /** 主控台最近一次 composite_decision 的 card_data（目标价卡数据源） */
  latestCardData: DecisionCardData | null
  /** 卡片「AI 分析」→ 右侧对话发起预设提问 */
  onAiAnalyze: (type: CardType) => void
}

/**
 * 技术面分析看板 — 五卡网格容器（spec: technical-dashboard R2-R6，操盘模式"技术面分析" Tab）。
 *
 * ①K线（Task 2）、②散户（Task 3）、③双拼筹码（Task 4）、④资金流（Task 5）、⑤目标价（Task 6）已实现。
 */
export function TechnicalDashboard({ symbol, onSymbolChange, latestCardData, onAiAnalyze }: TechnicalDashboardProps) {
  return (
    <div className="flex flex-1 min-w-0 flex-col overflow-auto p-4">
      {/* 当前标的栏 */}
      <div className="mb-4 flex shrink-0 items-center gap-3">
        <label className="text-base text-gray-500">当前标的</label>
        <input
          value={symbol}
          onChange={(e) => onSymbolChange(e.target.value.trim())}
          placeholder="股票代码，如 600519"
          className="w-[140px] rounded-md border border-[var(--color-border)] bg-white px-3 py-1.5 text-base text-[var(--color-text-primary)] outline-none focus:border-[var(--color-accent)]"
        />
        <span className="text-xs text-gray-400">五卡联动当前标的 · 操盘模式 · 技术面分析</span>
      </div>

      {/* 五卡网格填满剩余高度：左列 K线大卡(2fr)+资金流(1fr)，右列三卡均分。
          grid item 默认 min-width:auto 会被内容（图表/柱状图）撑宽导致横向溢出，
          子项统一 min-w-0 让其随容器动态收缩而非截断 */}
      <div className="grid min-h-0 flex-1 grid-cols-[1.7fr_1fr] grid-rows-1 gap-4">
        <div className="grid min-h-0 min-w-0 grid-rows-[2fr_1fr] gap-4">
          <div className="min-w-0 rounded-xl border border-[var(--color-border)] bg-white p-4">
            <div className="flex h-full min-w-0 flex-col">
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-xl font-medium text-[var(--color-text-primary)]">高阶分时K线图卡</h3>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-400">MA5/10/30 · 三栏同步 · {symbol}</span>
                  <AiInterpretSection onAnalyze={() => onAiAnalyze('technical')} />
                </div>
              </div>
              <div className="min-h-0 min-w-0 flex-1">
                <KLineCard symbol={symbol} />
              </div>
            </div>
          </div>
          <div className="min-w-0 rounded-xl border border-[var(--color-border)] bg-white p-4">
            <FundFlowCard symbol={symbol} onAiAnalyze={onAiAnalyze} />
          </div>
        </div>
        <div className="grid min-h-0 min-w-0 grid-rows-3 gap-4">
          <div className="min-w-0 rounded-xl border border-[var(--color-border)] bg-white p-4">
            <RetailCountCard symbol={symbol} onAiAnalyze={onAiAnalyze} />
          </div>
          <div className="min-w-0 rounded-xl border border-[var(--color-border)] bg-white p-4">
            <ChipCostCard symbol={symbol} onAiAnalyze={onAiAnalyze} />
          </div>
          <div className="min-w-0 rounded-xl border border-[var(--color-border)] bg-white p-4">
            <TargetPriceCard symbol={symbol} cardData={latestCardData} onAiAnalyze={onAiAnalyze} />
          </div>
        </div>
      </div>
    </div>
  )
}
