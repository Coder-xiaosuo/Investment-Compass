import { useState, useRef, useEffect } from 'react'
import type { AppMode, ChatMessage, DecisionCardData, SourceTab, Todo, TodoStatus } from '@/types'
import { DecisionCard } from '@/components/decision/DecisionCard'
import { InvestmentProfile } from '@/components/style/InvestmentProfile'
import { ContextUsage } from '@/components/panel/ContextUsage'
import type { RadarProfile } from '@/hooks/useStyleProfile'
import type { PreferencesData } from '@/hooks/usePreferences'
import { cn } from '@/lib/utils'
import { ExternalLink, Loader2, Plus, X } from 'lucide-react'

interface RightPanelProps {
  mode: AppMode
  cardData: DecisionCardData | null
  /** 投资画像（分析模式右侧栏「投资画像」模块数据） */
  profile: RadarProfile | null
  profileLoading?: boolean
  onStartQuiz: () => void
  onRetakeQuiz: () => void
  /** 偏好数据（已测试时展示） */
  preferences?: PreferencesData | null
  /** 当前会话消息（任务摘要页「上下文」token 用量统计来源） */
  messages: ChatMessage[]
  /** 会话累计 token 用量（后端 conversation.token_count，优先展示） */
  conversationTokenCount?: number
  /** 当前上下文真实占用（后端 conversation.context_tokens；优先于累计值展示） */
  contextTokens?: number
  /** Agent 待办列表（write_todos 实时透传，任务摘要页「待办」模块） */
  todos?: Todo[]
  /** 来源内嵌 Tab（点击信息来源后新建，iframe 展示原文） */
  sourceTabs: SourceTab[]
  /** 当前激活的来源 tab id（null 表示未在来源视图） */
  activeSourceId: string | null
  onSelectSourceTab: (id: string) => void
  onCloseSourceTab: (id: string) => void
}

/** 分析模式右侧栏页面级 Tab：画像（独立）/ 任务摘要（待办+上下文+决策 组合）+ 动态来源 tab */
type AnalysisTab = 'profile' | 'summary'

const ALL_TABS: { key: AnalysisTab; label: string }[] = [
  { key: 'profile', label: '画像' },
  { key: 'summary', label: '任务摘要' },
]

export function RightPanel({ mode, cardData, profile, profileLoading, onStartQuiz, onRetakeQuiz, preferences, messages, conversationTokenCount, contextTokens, todos, sourceTabs, activeSourceId, onSelectSourceTab, onCloseSourceTab }: RightPanelProps) {
  // 浏览器式 Tab：可关闭、可恢复（＋菜单）
  const [openTabs, setOpenTabs] = useState<AnalysisTab[]>(['profile', 'summary'])
  const [activeTab, setActiveTab] = useState<AnalysisTab | 'source' | null>('summary')
  const [closedTabs, setClosedTabs] = useState<AnalysisTab[]>([])
  const [menuOpen, setMenuOpen] = useState(false)

  if (mode === 'analysis') {
    const closeTab = (key: AnalysisTab) => {
      // 任务摘要为默认主页，不可关闭
      if (key === 'summary') return
      setClosedTabs((prev) => (prev.includes(key) ? prev : [...prev, key]))
      setOpenTabs((prev) => {
        const next = prev.filter((t) => t !== key)
        if (activeTab === key) setActiveTab(next[next.length - 1] ?? null)
        return next
      })
    }
    const restoreTab = (key: AnalysisTab) => {
      setClosedTabs((prev) => prev.filter((t) => t !== key))
      setOpenTabs((prev) => (prev.includes(key) ? prev : [...prev, key]))
      setActiveTab(key)
      setMenuOpen(false)
    }
    // 关闭来源 tab：移除由 App 层处理（含 activeSourceId 回退）；这里只同步内部视图状态
    const closeSourceTab = (id: string) => {
      onCloseSourceTab(id)
      if (activeSourceId === id) {
        // 若仍有剩余来源，activeSourceId 由 App 层回退到最后一项；
        // 无剩余来源则回退到任务摘要（内部 activeTab 状态）
        const next = sourceTabs.filter((t) => t.id !== id)
        if (next.length === 0) setActiveTab('summary')
      }
    }
    /** 当前激活的来源 tab（活跃来源视图且存在时非空） */
    const activeSource = activeTab === 'source' ? sourceTabs.find((t) => t.id === activeSourceId) ?? null : null

    return (
      <div className="flex h-full w-full flex-col select-none">
        {/* 浏览器式 Tab 栏：可关闭 + ＋恢复 + 来源 tab（可关闭） */}
        <nav className="flex h-11 shrink-0 items-center gap-0.5 border-b border-[var(--color-border)] pl-2 pr-1">
          <div className="flex min-w-0 flex-1 items-end gap-0.5 overflow-x-auto scrollbar-hide">
            {openTabs.map((t) => {
              const def = ALL_TABS.find((d) => d.key === t)!
              return (
                <div
                  key={t}
                  onClick={() => setActiveTab(t)}
                  className={cn(
                    'group flex h-full shrink-0 cursor-pointer items-center gap-1.5 rounded-t-md px-3 text-xs transition-colors',
                    activeTab === t
                      ? 'bg-[var(--color-bg-subtle)] font-medium text-[var(--color-text-primary)]'
                      : 'text-[var(--color-text-tertiary)] hover:bg-[var(--color-bg-hover)] hover:text-[var(--color-text-secondary)]',
                  )}
                >
                  <span>{def.label}</span>
                  {/* 任务摘要为默认主页，不提供关闭入口 */}
                  {t !== 'summary' && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        closeTab(t)
                      }}
                      className="flex h-4 w-4 items-center justify-center rounded text-[var(--color-text-tertiary)] opacity-0 transition-opacity group-hover:opacity-100 hover:bg-[var(--color-bg-sidebar-hover)] hover:text-[var(--color-text-secondary)]"
                      title={`关闭 ${def.label}`}
                    >
                      <X className="h-3 w-3" />
                    </button>
                  )}
                </div>
              )
            })}

            {/* 来源内嵌 Tab（动态，可关闭） */}
            {sourceTabs.map((tab) => (
              <div
                key={tab.id}
                onClick={() => {
                  onSelectSourceTab(tab.id)
                  setActiveTab('source')
                }}
                className={cn(
                  'group flex h-full shrink-0 cursor-pointer items-center gap-1.5 rounded-t-md px-3 text-xs transition-colors',
                  activeTab === 'source' && activeSourceId === tab.id
                    ? 'bg-[var(--color-bg-subtle)] font-medium text-[var(--color-text-primary)]'
                    : 'text-[var(--color-text-tertiary)] hover:bg-[var(--color-bg-hover)] hover:text-[var(--color-text-secondary)]',
                )}
                title={tab.url}
              >
                <span className="max-w-24 truncate">{tab.title}</span>
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    closeSourceTab(tab.id)
                  }}
                  className="flex h-4 w-4 shrink-0 items-center justify-center rounded text-[var(--color-text-tertiary)] opacity-0 transition-opacity group-hover:opacity-100 hover:bg-[var(--color-bg-sidebar-hover)] hover:text-[var(--color-text-secondary)]"
                  title="关闭来源"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>

          {/* ＋：恢复已关闭 Tab */}
          <div className="relative shrink-0">
            <button
              onClick={() => setMenuOpen((v) => !v)}
              className="flex h-7 w-7 items-center justify-center rounded text-[var(--color-text-tertiary)] hover:bg-[var(--color-bg-sidebar-hover)] hover:text-[var(--color-text-secondary)] transition-colors"
              title="恢复已关闭的 Tab"
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
            {menuOpen && (
              <div className="absolute right-0 top-7 z-20 w-32 rounded-lg border border-[var(--color-border)] bg-white p-1 shadow-lg">
                {closedTabs.length === 0 ? (
                  <p className="px-2 py-1.5 text-xs text-[var(--color-text-placeholder)]">暂无已关闭 Tab</p>
                ) : (
                  closedTabs.map((key) => {
                    const def = ALL_TABS.find((d) => d.key === key)!
                    return (
                      <button
                        key={key}
                        onClick={() => restoreTab(key)}
                        className="flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-subtle)]"
                      >
                        <Plus className="h-3 w-3" />
                        {def.label}
                      </button>
                    )
                  })
                )}
              </div>
            )}
          </div>
        </nav>

        {/* Tab 内容区 */}
        {activeSource ? (
          <SourceEmbed tab={activeSource} />
        ) : activeTab === null ? (
          <div className="flex flex-1 flex-col items-center justify-center px-4 text-center text-xs text-[var(--color-text-tertiary)]">
            <p>所有 Tab 已关闭</p>
            <p className="mt-1">点击右上角 ＋ 恢复</p>
          </div>
        ) : activeTab === 'profile' ? (
          <InvestmentProfile
            profile={profile}
            loading={profileLoading}
            onStartQuiz={onStartQuiz}
            onRetakeQuiz={onRetakeQuiz}
            preferences={preferences}
          />
        ) : (
          /* 任务摘要：待办 / 上下文 / 决策 均分高度，灰色分隔线 */
          <div className="flex min-h-0 flex-1 flex-col">
            {/* 待办 */}
            <div className="flex min-h-0 flex-1 flex-col border-b border-[var(--color-border)]">
              <div className="shrink-0 flex items-center justify-between px-4 py-2">
                <span className="text-xs font-medium text-[var(--color-text-primary)]">待办</span>
                <span className="rounded bg-[var(--color-accent-soft)] px-1.5 py-0.5 text-xs text-[var(--color-accent)]">
                  Agent
                </span>
              </div>
              {todos && todos.length > 0 ? (
                <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-4 pb-3">
                  {/* 完成进度 */}
                  <div className="mb-2 flex items-center gap-2">
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--color-bg-hover)]">
                      <div
                        className="h-full rounded-full bg-[var(--color-accent)] transition-all duration-300"
                        style={{ width: `${donePct(todos)}%` }}
                      />
                    </div>
                    <span className="shrink-0 text-xs text-[var(--color-text-tertiary)]">
                      {todos.filter((t) => t.status === 'completed').length}/{todos.length}
                    </span>
                  </div>
                  {/* 列表 */}
                  <ul className="min-h-0 flex-1 space-y-1 overflow-y-auto">
                    {todos.map((t, i) => (
                      <li key={i} className="flex items-start gap-2 text-xs leading-snug">
                        <TodoIcon status={t.status} />
                        <span
                          className={cn(
                            'min-w-0 flex-1 break-words',
                            t.status === 'completed'
                              ? 'text-[var(--color-text-tertiary)] line-through'
                              : 'text-[var(--color-text-primary)]',
                          )}
                        >
                          {t.content}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                <div className="flex min-h-0 flex-1 flex-col items-center justify-center overflow-y-auto px-4 pb-4 text-center">
                  <div className="rounded-full bg-[var(--color-bg-subtle)] p-2.5 mb-2">
                    <svg className="h-4 w-4 text-[var(--color-text-tertiary)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 6h12M6 12h12M6 18h12" />
                    </svg>
                  </div>
                  <p className="text-xs text-[var(--color-text-tertiary)]">
                    任务规划 Agent 将在此<br />生成待办列表
                  </p>
                  <p className="mt-1 text-xs text-[var(--color-text-placeholder)]">
                    LangChain TODO List Middleware
                  </p>
                </div>
              )}
            </div>

            {/* 上下文：token 用量 */}
            <ContextUsage
              messages={messages}
              conversationTokenCount={conversationTokenCount}
              contextTokens={contextTokens}
            />

            {/* 决策：完整卡片 */}
            <div className="flex min-h-0 flex-1 flex-col">
              <div className="shrink-0 flex items-center gap-1.5 px-4 py-2">
                <span className="text-xs font-medium text-[var(--color-text-primary)]">决策</span>
                <span className="rounded bg-[var(--color-accent-soft)] px-1.5 py-0.5 text-xs text-[var(--color-accent)]">
                  分析仅供参考
                </span>
              </div>
              <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
                <DecisionCard data={cardData} />
              </div>
            </div>
          </div>
        )}
      </div>
    )
  }

  return (
    <aside className="flex h-full w-full flex-col select-none">
      {/* 实时行情 */}
      <div className="flex flex-col border-b border-[var(--color-border)]">
        <div className="flex items-center justify-between px-4 py-2">
          <span className="text-xs font-medium text-[var(--color-text-primary)]">
            实时行情
          </span>
          <span className="text-xs text-[var(--color-text-tertiary)]">
            延时 • 模拟
          </span>
        </div>

        <div className="px-4 pb-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-base font-medium text-[var(--color-text-primary)]">
                请选择股票
              </p>
              <p className="text-xs text-[var(--color-text-tertiary)] mt-0.5">
                在对话或搜索中选择
              </p>
            </div>
          </div>

          <div className="mt-3 rounded-lg bg-[var(--color-bg-subtle)] p-3">
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-semibold text-[var(--color-text-tertiary)]">
                ---
              </span>
              <span className="text-xs text-[var(--color-text-tertiary)]">
                --%
              </span>
            </div>
            <div className="mt-2 grid grid-cols-4 gap-2 text-xs text-[var(--color-text-tertiary)]">
              <div>
                <span className="block">开</span>
                <span className="block mt-0.5 font-medium text-[var(--color-text-secondary)]">--</span>
              </div>
              <div>
                <span className="block">高</span>
                <span className="block mt-0.5 font-medium text-[var(--color-text-secondary)]">--</span>
              </div>
              <div>
                <span className="block">低</span>
                <span className="block mt-0.5 font-medium text-[var(--color-text-secondary)]">--</span>
              </div>
              <div>
                <span className="block">昨收</span>
                <span className="block mt-0.5 font-medium text-[var(--color-text-secondary)]">--</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* AI 交易决策 */}
      <div className="flex flex-col flex-1">
        <div className="flex items-center gap-1.5 px-4 py-3">
          <span className="text-xs font-medium text-[var(--color-text-primary)]">
            AI 交易决策
          </span>
          <span className="rounded bg-[var(--color-accent-soft)] px-1.5 py-0.5 text-xs text-[var(--color-accent)]">
            分析仅供参考
          </span>
        </div>

        <div className="flex flex-col flex-1 overflow-y-auto">
          <DecisionCard data={cardData} />
        </div>
      </div>
    </aside>
  )
}

/** 待办项状态图标 */
function TodoIcon({ status }: { status: TodoStatus }) {
  if (status === 'completed') {
    return (
      <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-[var(--color-success)]/10 text-[var(--color-success)]">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </span>
    )
  }
  if (status === 'in_progress') {
    return (
      <span className="mt-0.5 h-4 w-4 shrink-0 rounded-full border-2 border-[var(--color-accent)] border-t-transparent animate-spin" />
    )
  }
  return <span className="mt-0.5 h-4 w-4 shrink-0 rounded-full bg-[var(--color-bg-subtle)]" />
}

/** 完成进度百分比 */
function donePct(todos: Todo[]): number {
  if (todos.length === 0) return 0
  return Math.round((todos.filter((t) => t.status === 'completed').length / todos.length) * 100)
}

// ── 来源内嵌（iframe） ────────────────────────────────────────────────────────

/** 可直嵌的数据源（实测无 X-Frame-Options，iframe 正常展示）；其余来源用阅读器兜底 */
const IFRAME_SAFE_SOURCES = new Set(['em_news', 'cls_telegraph', 'em_global', 'research_reports'])

function SourceEmbed({ tab }: { tab: SourceTab }) {
  const [state, setState] = useState<'loading' | 'loaded' | 'failed'>('loading')
  // iframe 加载超时（X-Frame-Options 拒绝时 onLoad 不触发，用超时判定兜底）
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const reset = () => {
    setState('loading')
    if (timeoutRef.current) clearTimeout(timeoutRef.current)
    // 12s 未触发 onLoad → 判定加载失败（多为目标站禁止内嵌）
    timeoutRef.current = setTimeout(() => {
      setState((s) => (s === 'loading' ? 'failed' : s))
    }, 12000)
  }
  useEffect(() => {
    reset()
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
    }
  }, [tab.id])

  const canEmbed = IFRAME_SAFE_SOURCES.has(tab.source)
  const host = (() => {
    try {
      return new URL(tab.url).hostname
    } catch {
      return tab.url
    }
  })()

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* 工具栏：来源域名 + 加载状态 + 浏览器打开 */}
      <div className="flex shrink-0 items-center gap-2 border-b border-[var(--color-border-light)] px-3 py-1.5">
        <span className="min-w-0 flex-1 truncate text-xs text-[var(--color-text-tertiary)]">{host}</span>
        {state === 'loading' && (
          <span className="flex shrink-0 items-center gap-1 text-xs text-[var(--color-text-tertiary)]">
            <Loader2 className="h-3 w-3 animate-spin" />
            加载中
          </span>
        )}
        {state === 'failed' && (
          <span className="shrink-0 text-xs text-[var(--color-warning)]">该站点禁止内嵌</span>
        )}
        <a
          href={tab.url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex shrink-0 items-center gap-1 rounded-md bg-[var(--color-accent-soft)] px-2 py-1 text-xs text-[var(--color-accent)] transition-colors hover:bg-[var(--color-accent)] hover:text-white"
          title="在浏览器新标签页打开"
        >
          <ExternalLink className="h-3 w-3" />
          浏览器打开
        </a>
      </div>

      {/* 内容区：iframe 或 失败提示 */}
      {state === 'failed' ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
          <p className="text-sm font-medium text-[var(--color-text-primary)]">无法在面板内展示</p>
          <p className="max-w-60 text-xs leading-relaxed text-[var(--color-text-tertiary)]">
            该站点设置了禁止内嵌（X-Frame-Options / CSP），已为你保留原标题与链接。
          </p>
          <a
            href={tab.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 rounded-md bg-[var(--color-accent)] px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-[var(--color-accent-hover)]"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            在浏览器中打开
          </a>
        </div>
      ) : canEmbed ? (
        <iframe
          src={tab.url}
          onLoad={() => {
            if (timeoutRef.current) clearTimeout(timeoutRef.current)
            setState('loaded')
          }}
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-downloads"
          className="min-h-0 flex-1 border-0 bg-white"
          title={tab.title}
        />
      ) : (
        /* 不可直嵌来源（如联网搜索任意 URL）：占位 + 浏览器打开 */
        <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
          <p className="text-sm font-medium text-[var(--color-text-primary)]">外部网页</p>
          <p className="max-w-60 text-xs leading-relaxed text-[var(--color-text-tertiary)]">
            该来源来自联网搜索（{host}），多数站点禁止面板内嵌。建议在浏览器打开查看原文。
          </p>
          <a
            href={tab.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 rounded-md bg-[var(--color-accent)] px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-[var(--color-accent-hover)]"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            在浏览器中打开
          </a>
        </div>
      )}
    </div>
  )
}
