import { useRef, useState, useEffect } from 'react'
import type { AppMode, Citation, Conversation, ChatMessage, Decision, DecisionCardData, MainTab, SourceTab, StreamDisplay } from '@/types'
import type { CardType } from '@/lib/cardPrompts'
import type { RadarProfile } from '@/hooks/useStyleProfile'
import type { PreferencesData } from '@/hooks/usePreferences'
import { Sidebar } from './Sidebar'
import { MainArea } from './MainArea'
import { RightPanel } from './RightPanel'
import { RightChatPanel } from '@/components/panel/RightChatPanel'
import { cn } from '@/lib/utils'

/** 卡片宽度百分比参数（中间/右侧卡片共用同一最小值，随容器宽度自适应） */
const MIN_PANEL_PCT = 30
/** 中间/右侧 1:1 布局（分析模式来源内嵌阅读体验最佳） */
const DEFAULT_RIGHT_PCT = 50
/** 拖拽分隔条宽度 + 容器 p-1 左右留边（换算可用宽度用） */
const RESIZER_WIDTH = 6
const EDGE_PADDING = 8

interface AppLayoutProps {
  mode: AppMode
  onModeChange: (mode: AppMode) => void
  activeTab: MainTab
  onTabChange: (tab: MainTab) => void
  symbol: string
  onSymbolChange: (symbol: string) => void
  /** 右侧卡片开关（分析模式=复盘面板；操盘模式=AI 对话栏），关闭后中间卡片拉伸填满 */
  panelOpen: boolean
  onPanelToggle: () => void
  /** 待发送到右侧对话的预设提示词（卡片「AI 分析」触发），发送完成后回调清空 */
  panelPrompt: string | null
  onPromptConsumed: () => void
  /** 卡片「AI 分析」→ 右侧对话发起预设提问 */
  onAiAnalyze: (type: CardType) => void
  conversations: Conversation[]
  selectedConversationId: string | null
  onSelectConversation: (id: string) => void
  onNewConversation: () => void
  /** 侧栏会话操作：归档 / 删除 */
  onArchiveConversation: (id: string) => void
  onDeleteConversation: (id: string) => void
  messages: ChatMessage[]
  streaming: StreamDisplay | null
  onSendMessage: (content: string) => void
  /** HITL 中断后提交用户决策（resume 续流） */
  onResume: (decisions: Decision[]) => void
  latestCardData: DecisionCardData | null
  /** 投资画像（分析模式右侧栏模块） */
  profile: RadarProfile | null
  profileLoading: boolean
  onStartQuiz: () => void
  onRetakeQuiz: () => void
  preferences: PreferencesData | null
  /** 来源内嵌 Tab（点击信息来源后新建） */
  sourceTabs: SourceTab[]
  activeSourceId: string | null
  onOpenSource: (citation: Citation) => void
  onSelectSourceTab: (id: string) => void
  onCloseSourceTab: (id: string) => void
  onOpenSettings?: () => void
}

export function AppLayout({
  mode,
  onModeChange,
  activeTab,
  onTabChange,
  symbol,
  onSymbolChange,
  panelOpen,
  onPanelToggle,
  panelPrompt,
  onPromptConsumed,
  onAiAnalyze,
  conversations,
  selectedConversationId,
  onSelectConversation,
  onNewConversation,
  onArchiveConversation,
  onDeleteConversation,
  messages,
  streaming,
  onSendMessage,
  onResume,
  latestCardData,
  profile,
  profileLoading,
  onStartQuiz,
  onRetakeQuiz,
  preferences,
  sourceTabs,
  activeSourceId,
  onOpenSource,
  onSelectSourceTab,
  onCloseSourceTab,
  onOpenSettings,
}: AppLayoutProps) {
  const selectedConv = conversations.find((c) => c.id === selectedConversationId)
  const containerRef = useRef<HTMLDivElement>(null)

  // 右侧卡片宽度（百分比制，随容器宽度自适应；拖拽分隔条调整，双击重置）
  // 分析模式来源内嵌阅读 1:1；操盘模式右侧为对话栏，恢复默认 25%
  const [rightWidthPct, setRightWidthPct] = useState(mode === 'analysis' ? DEFAULT_RIGHT_PCT : 25)
  const [isDragging, setIsDragging] = useState(false)
  const dragStartX = useRef(0)
  const dragStartPct = useRef(mode === 'analysis' ? DEFAULT_RIGHT_PCT : 25)
  const containerWidthRef = useRef(0)

  // 模式切换时按模式重置右侧宽度（分析 1:1 / 操盘默认）
  useEffect(() => {
    setRightWidthPct(mode === 'analysis' ? DEFAULT_RIGHT_PCT : 25)
  }, [mode])

  const handleResizePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault()
    dragStartX.current = e.clientX
    dragStartPct.current = rightWidthPct
    containerWidthRef.current = containerRef.current?.clientWidth ?? 0
    setIsDragging(true)
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const handleResizePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isDragging) return
    const usableWidth = containerWidthRef.current - RESIZER_WIDTH - EDGE_PADDING
    if (usableWidth <= 0) return
    // 以可用宽度为基准换算百分比；两侧卡片各保底 30%
    const deltaPct = ((dragStartX.current - e.clientX) / usableWidth) * 100
    const next = Math.min(Math.max(dragStartPct.current + deltaPct, MIN_PANEL_PCT), 100 - MIN_PANEL_PCT)
    setRightWidthPct(next)
  }
  const handleResizePointerUp = () => setIsDragging(false)

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[var(--color-bg-sidebar)]">
      {/* 底层：左侧栏（左侧一列，铺满高度） */}
      <Sidebar
        mode={mode}
        onModeChange={onModeChange}
        conversations={conversations}
        selectedId={selectedConversationId}
        onSelectConversation={onSelectConversation}
        onNewConversation={onNewConversation}
        onArchiveConversation={onArchiveConversation}
        onDeleteConversation={onDeleteConversation}
        onOpenSettings={onOpenSettings}
      />

      {/* 上层：中间 / 右侧 独立卡片，极紧凑留边 */}
      <div ref={containerRef} className="flex min-w-0 flex-1 gap-0 p-1">
        {/* 中间卡片（模式切换时淡入） */}
        <div
          key={mode}
          className="flex min-w-[30%] flex-1 animate-fade-in overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-surface)] shadow-[0_1px_4px_rgba(0,0,0,0.04)]"
        >
          <MainArea
            mode={mode}
            activeTab={activeTab}
            onTabChange={onTabChange}
            symbol={symbol}
            onSymbolChange={onSymbolChange}
            panelOpen={panelOpen}
            onPanelToggle={onPanelToggle}
            conversationTitle={selectedConv?.title ?? null}
            messages={messages}
            streaming={streaming}
            onSendMessage={onSendMessage}
            onResume={onResume}
            latestCardData={latestCardData}
            onAiAnalyze={onAiAnalyze}
            onOpenSource={onOpenSource}
          />
        </div>

        {/* 右侧卡片：拖拽分隔条 + 可调宽面板（分析=复盘面板 / 操盘=AI 对话栏） */}
        {panelOpen && (
          <>
            {/* 拖拽分隔条 */}
            <div
              onPointerDown={handleResizePointerDown}
              onPointerMove={handleResizePointerMove}
              onPointerUp={handleResizePointerUp}
              onDoubleClick={() => setRightWidthPct(mode === 'analysis' ? DEFAULT_RIGHT_PCT : 25)}
              className={cn(
                'relative w-1.5 shrink-0 cursor-col-resize select-none transition-colors',
                isDragging ? 'bg-[var(--color-accent)]/30' : 'hover:bg-[var(--color-accent)]/15',
              )}
              title="拖拽调整宽度，双击恢复默认"
            >
              <div
                className={cn(
                  'absolute left-1/2 top-1/2 h-10 w-0.5 -translate-x-1/2 -translate-y-1/2 rounded-full transition-colors',
                  isDragging ? 'bg-[var(--color-accent)]' : 'bg-[var(--color-border)]',
                )}
              />
            </div>

            <div
              key={`right-${mode}`}
              className="flex shrink-0 animate-fade-in overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-surface)] shadow-[0_1px_4px_rgba(0,0,0,0.04)]"
              style={{ width: `${rightWidthPct}%` }}
            >
              {mode === 'analysis' ? (
                <RightPanel
                  mode={mode}
                  cardData={latestCardData}
                  profile={profile}
                  profileLoading={profileLoading}
                  onStartQuiz={onStartQuiz}
                  onRetakeQuiz={onRetakeQuiz}
                  preferences={preferences}
                  messages={messages}
                  conversationTokenCount={selectedConv?.tokenCount}
                  contextTokens={streaming?.contextTokens ?? selectedConv?.contextTokens}
                  todos={streaming?.todos}
                  sourceTabs={sourceTabs}
                  activeSourceId={activeSourceId}
                  onSelectSourceTab={onSelectSourceTab}
                  onCloseSourceTab={onCloseSourceTab}
                />
              ) : (
                <RightChatPanel
                  onClose={() => onPanelToggle()}
                  pendingPrompt={panelPrompt}
                  onPromptConsumed={onPromptConsumed}
                />
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
