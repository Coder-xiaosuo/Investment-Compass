import { useRef, useEffect, useState } from 'react'
import type { AnalysisTraceCardData, ChatMessage, Citation, Decision, StreamDisplay } from '@/types'
import { WelcomeCard } from './WelcomeCard'
import { InputArea } from './InputArea'
import { QuickEntryPanel } from './QuickEntryPanel'
import { SubagentCard } from './SubagentCard'
import { HITLConfirmCard } from './HITLConfirmCard'
import { Markdown } from './Markdown'
import { useThrottledValue } from '@/hooks/useThrottledValue'
import { ChevronDown, Link2, PanelRight } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ChatViewProps {
  conversationTitle: string | null
  messages: ChatMessage[]
  streaming: StreamDisplay | null
  onSendMessage: (content: string) => void
  /** HITL 中断后提交用户决策（resume 续流） */
  onResume?: (decisions: Decision[]) => void
  /** 右侧面板开关（分析模式复盘面板） */
  panelOpen: boolean
  onPanelToggle: () => void
  /** 点击信息来源 → 右侧新建内嵌 tab（iframe 展示原文） */
  onOpenSource?: (citation: Citation) => void
}

/** 右侧面板开关按钮（标题栏 / 欢迎页共用） */
function PanelToggleButton({ panelOpen, onPanelToggle }: { panelOpen: boolean; onPanelToggle: () => void }) {
  return (
    <button
      onClick={onPanelToggle}
      className={cn(
        'flex h-7 items-center gap-1.5 rounded-full px-3 text-xs font-medium transition-all',
        panelOpen
          ? 'bg-[var(--color-accent)] text-white'
          : 'bg-[var(--color-accent-soft)] text-[var(--color-accent)] hover:bg-[var(--color-accent)] hover:text-white',
      )}
      title={panelOpen ? '收起右侧面板' : '打开右侧面板'}
    >
      <PanelRight className="h-3.5 w-3.5" />
      面板
    </button>
  )
}

/** assistant 消息是否携带可回放的分析过程 trace */
function isTraceMessage(msg: ChatMessage): msg is ChatMessage & { card_data: AnalysisTraceCardData } {
  return (
    msg.role === 'assistant' &&
    !!msg.card_data &&
    Array.isArray(msg.card_data.analysis_trace) &&
    msg.card_data.analysis_trace.length > 0
  )
}

/** 历史消息携带的引用来源（落库在 card_data.result.citations） */
function getHistoryCitations(msg: ChatMessage): Citation[] {
  const cites = msg.card_data?.result?.citations
  return Array.isArray(cites) ? (cites as Citation[]) : []
}

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      {!isUser && (
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--color-accent-soft)] mr-2 mt-1 text-xs">
          AI
        </div>
      )}
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-base leading-relaxed ${
          isUser
            ? 'bg-[var(--color-accent)] text-white rounded-br-md'
            : 'bg-[var(--color-bg-surface)] text-[var(--color-text-primary)] rounded-bl-md border border-[var(--color-border-light)]'
        }`}
      >
        {isUser ? (
          <span className="whitespace-pre-wrap">{msg.content}</span>
        ) : (
          <Markdown content={msg.content} />
        )}
      </div>
      {isUser && (
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--color-bg-subtle)] ml-2 mt-1 text-xs">
          我
        </div>
      )}
    </div>
  )
}

/** 流式中的主 Agent 回复气泡（Markdown 渲染 + 节流 + 光标） */
function StreamingBubble({ text }: { text: string }) {
  const throttled = useThrottledValue(text)
  return (
    <div className="flex justify-start mb-4">
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--color-accent-soft)] mr-2 mt-1 text-xs">
        AI
      </div>
      <div className="max-w-[80%] rounded-2xl px-4 py-2.5 text-base leading-relaxed bg-[var(--color-bg-surface)] text-[var(--color-text-primary)] rounded-bl-md border border-[var(--color-border-light)]">
        <Markdown content={throttled} streaming />
      </div>
    </div>
  )
}

/** 主 Agent 思维链折叠区（DeepSeek reasoning_content 实时增量） */
function ThinkingBlock({ text, streaming }: { text: string; streaming: boolean }) {
  const [open, setOpen] = useState(false)
  if (!text) return null
  return (
    <div className="mb-2 ml-9 flex max-w-[80%] flex-col overflow-hidden rounded-xl border border-[var(--color-border-light)] bg-[var(--color-bg-subtle)]">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 px-3 py-1.5 text-left transition-colors hover:bg-[var(--color-bg-surface)]"
      >
        {streaming ? (
          <span className="h-3 w-3 shrink-0 animate-pulse rounded-full bg-[var(--color-accent)]" />
        ) : (
          <span className="h-3 w-3 shrink-0 rounded-full bg-[var(--color-success)]" />
        )}
        <span className="text-xs font-medium text-[var(--color-text-secondary)]">思考过程</span>
        <span className="flex-1" />
        <ChevronDown className={cn('h-3.5 w-3.5 text-[var(--color-text-tertiary)] transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="max-h-48 overflow-y-auto scrollbar-hide border-t border-[var(--color-border-light)] px-3 py-2 text-xs leading-relaxed text-[var(--color-text-tertiary)] whitespace-pre-wrap">
          {text}
        </div>
      )}
    </div>
  )
}

// ── 信息来源溯源 ─────────────────────────────────────────────────────────────

type SourceKind = 'local' | 'web' | 'knowledge'

/** 数据源标识 → 中文名 + 类型（local 本地检索 / web 联网搜索 / knowledge 通用知识） */
const SOURCE_META: Record<string, { label: string; kind: SourceKind }> = {
  em_news: { label: '东方财富', kind: 'local' },
  cls_telegraph: { label: '财联社', kind: 'local' },
  em_global: { label: '东财全球', kind: 'local' },
  research_reports: { label: '券商研报', kind: 'local' },
  deepseek_web_search: { label: '联网搜索', kind: 'web' },
  llm_knowledge: { label: '通用知识', kind: 'knowledge' },
}

const KIND_STYLE: Record<SourceKind, { chip: string; icon: string }> = {
  local: { chip: 'bg-[var(--color-accent-soft)] text-[var(--color-accent)]', icon: 'text-[var(--color-accent)]' },
  web: { chip: 'bg-[var(--color-warning)]/10 text-[var(--color-warning)]', icon: 'text-[var(--color-warning)]' },
  knowledge: { chip: 'bg-[var(--color-bg-subtle)] text-[var(--color-text-tertiary)]', icon: 'text-[var(--color-text-tertiary)]' },
}

function SourceChip({ source }: { source: string }) {
  const meta = SOURCE_META[source] ?? { label: source, kind: 'local' as SourceKind }
  const style = KIND_STYLE[meta.kind]
  return (
    <span className={cn('inline-flex shrink-0 items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium', style.chip)}>
      {meta.label}
    </span>
  )
}

/** 信息来源脚注区（编号与 citations 顺序对应，点击在右侧面板内嵌打开） */
function SourcesBlock({ citations, onOpenSource }: { citations: Citation[]; onOpenSource?: (c: Citation) => void }) {
  if (!citations.length) return null
  /** 联网搜索占位标题（如"联网搜索结果来源 1"）→ 用 URL 域名替代，更直观 */
  const displayTitle = (c: Citation): string => {
    if (c.title && !/^联网搜索结果来源\s*\d+$/.test(c.title)) return c.title
    if (c.url) {
      try {
        return new URL(c.url).hostname
      } catch {
        return c.url
      }
    }
    return c.title || '未命名来源'
  }
  return (
    <div className="mb-4 max-w-[80%] rounded-xl border border-[var(--color-border-light)] bg-[var(--color-bg-surface)] px-3 py-2">
      <div className="mb-1 flex items-center gap-1.5">
        <Link2 className="h-3.5 w-3.5 text-[var(--color-text-tertiary)]" />
        <span className="text-xs font-medium text-[var(--color-text-secondary)]">
          信息来源
        </span>
        <span className="text-[10px] text-[var(--color-text-tertiary)]">（{citations.length} 条）</span>
      </div>
      <ol className="flex flex-col gap-1">
        {citations.map((c, i) => (
          <li key={i} className="flex items-center gap-2 text-xs leading-relaxed">
            <span className="shrink-0 font-mono text-[10px] text-[var(--color-text-tertiary)]">[{i + 1}]</span>
            <span className="min-w-0 flex-1 truncate text-[var(--color-text-primary)]">
              {c.url ? (
                <a
                  href={c.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => {
                    // 分析模式右侧面板内嵌打开（不走外部跳转）；仅无法内嵌时保留默认跳转
                    if (onOpenSource) {
                      e.preventDefault()
                      onOpenSource(c)
                    }
                  }}
                  className="transition-colors hover:text-[var(--color-accent)] hover:underline"
                  title={c.url}
                >
                  {displayTitle(c)}
                </a>
              ) : (
                displayTitle(c)
              )}
            </span>
            {c.publish_time && <span className="shrink-0 text-[10px] text-[var(--color-text-tertiary)]">{c.publish_time}</span>}
            <SourceChip source={c.source} />
          </li>
        ))}
      </ol>
    </div>
  )
}

export function ChatView({ conversationTitle, messages, streaming, onSendMessage, onResume, panelOpen, onPanelToggle, onOpenSource }: ChatViewProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  // 新消息、流式内容或中断卡片出现时自动滚到底部
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, streaming?.text, streaming?.thinkingText, streaming?.subagentCards, streaming?.isInterrupted])

  if (!conversationTitle) {
    return (
      <div className="relative flex flex-col flex-1 bg-transparent min-w-0">
        {/* 无会话时右上角的面板开关 */}
        <div className="absolute right-4 top-3 z-10">
          <PanelToggleButton panelOpen={panelOpen} onPanelToggle={onPanelToggle} />
        </div>
        {/* 标题 + 输入框上抬，下方放引导卡片 */}
        <div className="flex flex-1 flex-col min-h-0 px-6 pt-[4vh]">
          <div className="flex flex-col items-center">
            <WelcomeCard />
            <div className="mt-4 w-full max-w-[720px]">
              <InputArea onSend={onSendMessage} />
            </div>
          </div>
          <div className="mt-4 w-full min-h-0 flex-1 overflow-y-auto pb-6">
            <QuickEntryPanel onSend={onSendMessage} />
          </div>
        </div>
      </div>
    )
  }

  const hasStockMatch = conversationTitle.match(/[0-9]{6}/)
  const stockLabel = hasStockMatch
    ? conversationTitle.replace(/\s*[0-9]{6}/, '').trim()
    : conversationTitle

  return (
    <div className="flex flex-col flex-1 bg-transparent min-w-0">
      {/* 任务基本信息栏 */}
      <div className="flex items-center gap-3 border-b border-[var(--color-border-light)] bg-[var(--color-bg-surface)] px-5 py-2.5 shrink-0">
        {hasStockMatch && (
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-[var(--color-accent-soft)] text-xs">📈</span>
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="text-base font-medium text-[var(--color-text-primary)] truncate">{stockLabel}</h2>
            {hasStockMatch && (
              <span className="rounded bg-[var(--color-bg-subtle)] px-1.5 py-0.5 text-xs font-mono text-[var(--color-text-tertiary)]">
                {hasStockMatch[0]}
              </span>
            )}
          </div>
          <p className="text-xs text-[var(--color-text-tertiary)] mt-0.5">AI 投研分析 · 数据驱动</p>
        </div>
        <div className="flex items-center gap-1.5 rounded-full bg-[var(--color-bg-subtle)] px-2.5 py-1">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-success)]" />
          <span className="text-xs text-[var(--color-text-secondary)]">就绪</span>
        </div>
        <PanelToggleButton panelOpen={panelOpen} onPanelToggle={onPanelToggle} />
      </div>

      {/* 消息流区域 */}
      <div className="flex-1 overflow-y-auto scrollbar-hide px-6 py-4">
        <div className="mx-auto max-w-[720px]">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-xs text-[var(--color-text-tertiary)]">
              <p>开始对话，AI 将在此展示分析过程</p>
            </div>
          ) : (
            <div className="flex flex-col">
              {messages.map((msg) => (
                <div key={msg.id}>
                  {isTraceMessage(msg) && <SubagentCard history={msg.card_data} />}
                  <MessageBubble msg={msg} />
                  <SourcesBlock citations={getHistoryCitations(msg)} onOpenSource={onOpenSource} />
                </div>
              ))}
              {streaming && (
                <>
                  <ThinkingBlock text={streaming.thinkingText} streaming={!!streaming.isStreaming} />
                  {streaming.subagentCards.map((card) => (
                    <SubagentCard key={card.taskId} state={card} />
                  ))}
                  {streaming.text && <StreamingBubble text={streaming.text} />}
                  <SourcesBlock citations={streaming.citations ?? []} onOpenSource={onOpenSource} />
                  {streaming.isInterrupted && streaming.interruptData && (
                    <HITLConfirmCard
                      data={streaming.interruptData}
                      isResuming={!!streaming.isResuming}
                      onResume={(decisions) => onResume?.(decisions)}
                    />
                  )}
                </>
              )}
              <div ref={bottomRef} />
            </div>
          )}
        </div>
      </div>

      {/* 输入框 */}
      <div className="flex min-h-[16.67vh] items-center justify-center bg-transparent px-6">
        <div className="w-full max-w-[720px]">
          <InputArea onSend={onSendMessage} disabled={!!streaming?.isStreaming} />
        </div>
      </div>
    </div>
  )
}
