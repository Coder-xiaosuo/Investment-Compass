import type { CardType } from '@/lib/cardPrompts'
import { FinancialSummaryCard } from './FinancialSummaryCard'
import { CashFlowCard } from './CashFlowCard'
import { ValuationCard } from './ValuationCard'
import { GrowthCard } from './GrowthCard'
import { SolvencyCard } from './SolvencyCard'

interface FundamentalDashboardProps {
  symbol: string
  onSymbolChange: (symbol: string) => void
  /** 卡片「AI 分析」→ 右侧对话发起预设提问 */
  onAiAnalyze: (type: CardType) => void
}

/**
 * 基本面分析看板 — 五卡网格容器（操盘模式"基本面分析" Tab）。
 *
 * 布局复用 TechnicalDashboard 模式：左列大卡(2fr)+小卡(1fr)，右列三卡均分。
 * 当前为 mock 占位阶段，后续逐张替换为真实后端接口。
 */
export function FundamentalDashboard({ symbol, onSymbolChange, onAiAnalyze }: FundamentalDashboardProps) {
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
        <span className="text-xs text-gray-400">五卡联动当前标的 · 操盘模式 · 基本面分析</span>
      </div>

      {/* 五卡网格：左列 财务综合大卡(2fr)+现金流(1fr)，右列三卡均分。
          子项统一 min-w-0 防止横向溢出 */}
      <div className="grid min-h-0 flex-1 grid-cols-[1.7fr_1fr] grid-rows-1 gap-4">
        <div className="grid min-h-0 min-w-0 grid-rows-[2fr_1fr] gap-4">
          {/* 左列上：财务综合大卡 */}
          <div className="min-w-0 rounded-xl border border-[var(--color-border)] bg-white p-4">
            <FinancialSummaryCard symbol={symbol} onAiAnalyze={onAiAnalyze} />
          </div>
          {/* 左列下：现金流卡 */}
          <div className="min-w-0 rounded-xl border border-[var(--color-border)] bg-white p-4">
            <CashFlowCard symbol={symbol} onAiAnalyze={onAiAnalyze} />
          </div>
        </div>
        <div className="grid min-h-0 min-w-0 grid-rows-3 gap-4">
          {/* 右列上：估值水平卡 */}
          <div className="min-w-0 rounded-xl border border-[var(--color-border)] bg-white p-4">
            <ValuationCard symbol={symbol} onAiAnalyze={onAiAnalyze} />
          </div>
          {/* 右列中：成长能力卡 */}
          <div className="min-w-0 rounded-xl border border-[var(--color-border)] bg-white p-4">
            <GrowthCard symbol={symbol} onAiAnalyze={onAiAnalyze} />
          </div>
          {/* 右列下：偿债&运营卡 */}
          <div className="min-w-0 rounded-xl border border-[var(--color-border)] bg-white p-4">
            <SolvencyCard symbol={symbol} onAiAnalyze={onAiAnalyze} />
          </div>
        </div>
      </div>
    </div>
  )
}
