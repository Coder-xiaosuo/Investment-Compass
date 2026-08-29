import type { AppMode, ChatMessage, Citation, Decision, DecisionCardData, MainTab, StreamDisplay } from '@/types'
import type { CardType } from '@/lib/cardPrompts'
import { Bot } from 'lucide-react'
import { ChatView } from '@/components/chat/ChatView'
import { TechnicalDashboard } from '@/components/technical/TechnicalDashboard'
import { FundamentalDashboard } from '@/components/fundamental/FundamentalDashboard'
import { MarketDashboard } from '@/components/market/MarketDashboard'
import { cn } from '@/lib/utils'

interface MainAreaProps {
  mode: AppMode
  activeTab: MainTab
  onTabChange: (tab: MainTab) => void
  symbol: string
  onSymbolChange: (symbol: string) => void
  /** 操盘模式右侧 AI 对话栏开关（关闭时导航栏 AI 图标为恢复入口） */
  panelOpen: boolean
  onPanelToggle: () => void
  conversationTitle: string | null
  messages: ChatMessage[]
  streaming: StreamDisplay | null
  onSendMessage: (content: string) => void
  /** HITL 中断后提交用户决策（resume 续流） */
  onResume: (decisions: Decision[]) => void
  /** 主控台最近一次 composite_decision 的 card_data（目标价卡数据源） */
  latestCardData: DecisionCardData | null
  /** 卡片「AI 分析」→ 右侧对话发起预设提问 */
  onAiAnalyze: (type: CardType) => void
  /** 点击信息来源 → 右侧新建内嵌 tab（仅分析模式生效） */
  onOpenSource: (citation: Citation) => void
}

/** 操盘模式顶部导航（spec R1）：技术面分析 / 基本面分析 / 市场概览 */
const TRADING_TABS: { key: MainTab; label: string }[] = [
  { key: 'technical', label: '技术面分析' },
  { key: 'fundamental', label: '基本面分析' },
  { key: 'market', label: '市场概览' },
]

const PLACEHOLDER_TITLES: Partial<Record<MainTab, string>> = {
  market: '市场概览',
}

export function MainArea({
  mode,
  activeTab,
  onTabChange,
  symbol,
  onSymbolChange,
  panelOpen,
  onPanelToggle,
  conversationTitle,
  messages,
  streaming,
  onSendMessage,
  onResume,
  latestCardData,
  onAiAnalyze,
  onOpenSource,
}: MainAreaProps) {
  // 分析模式（主控台）：中间直接是 AI 对话板，无 Tab 导航
  if (mode === 'analysis') {
    return (
      <main className="flex flex-1 min-w-0">
        <ChatView
          conversationTitle={conversationTitle}
          messages={messages}
          streaming={streaming}
          onSendMessage={onSendMessage}
          onResume={onResume}
          panelOpen={panelOpen}
          onPanelToggle={onPanelToggle}
          onOpenSource={onOpenSource}
        />
      </main>
    )
  }

  // 操盘模式：顶部四 Tab + 视图切换（技术面/基本面/市场概览为看板）
  return (
    <main className="flex flex-1 min-w-0">
      <div className="flex flex-1 min-w-0 flex-col">
        {/* 三 Tab 导航 + 右侧 AI 对话入口 */}
        <nav className="flex h-11 shrink-0 items-end gap-1 border-b border-[var(--color-border)] bg-[var(--color-bg-surface)] px-3">
          <div className="flex min-w-0 flex-1 items-end gap-1">
            {TRADING_TABS.map((tab) => (
              <button
                key={tab.key}
                onClick={() => onTabChange(tab.key)}
                className={cn(
                  'relative h-full px-4 text-base transition-colors',
                  activeTab === tab.key
                    ? 'font-medium text-[var(--color-accent)]'
                    : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]',
                )}
              >
                {tab.label}
                {activeTab === tab.key && (
                  <span className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-[var(--color-accent)]" />
                )}
              </button>
            ))}
          </div>

          {/* 靠右：AI 对话栏开关（关闭后作为恢复入口） */}
          <button
            onClick={onPanelToggle}
            className={cn(
              'mb-1 flex h-7 items-center gap-1.5 rounded-full px-3 text-xs font-medium transition-all',
              panelOpen
                ? 'bg-[var(--color-accent)] text-white'
                : 'bg-[var(--color-accent-soft)] text-[var(--color-accent)] hover:bg-[var(--color-accent)] hover:text-white',
            )}
            title={panelOpen ? '关闭 AI 对话栏' : '打开 AI 对话栏'}
          >
            <Bot className="h-3.5 w-3.5" />
            AI 对话
          </button>
        </nav>

        {/* 视图映射：技术面/基本面/市场概览 → 五卡看板 */}
        {activeTab === 'technical' ? (
          <TechnicalDashboard symbol={symbol} onSymbolChange={onSymbolChange} latestCardData={latestCardData} onAiAnalyze={onAiAnalyze} />
        ) : activeTab === 'fundamental' ? (
          <FundamentalDashboard symbol={symbol} onSymbolChange={onSymbolChange} onAiAnalyze={onAiAnalyze} />
        ) : activeTab === 'market' ? (
          <MarketDashboard onAiAnalyze={onAiAnalyze} />
        ) : (
          <PlaceholderTab title={PLACEHOLDER_TITLES[activeTab] ?? '规划中'} />
        )}
      </div>
    </main>
  )
}

/** 未落地 Tab 的占位页（基本面 / 市场概览） */
function PlaceholderTab({ title }: { title: string }) {
  return (
    <div className="flex flex-1 items-center justify-center bg-transparent">
      <div className="text-center">
        <p className="text-xl font-medium text-[var(--color-text-primary)]">{title}</p>
        <p className="mt-1 text-base text-gray-500">功能规划中，敬请期待</p>
      </div>
    </div>
  )
}
