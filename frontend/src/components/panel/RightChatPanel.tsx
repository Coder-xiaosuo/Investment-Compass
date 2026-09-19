import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { History, MessageSquarePlus, X, Pencil, SendHorizonal, Loader2 } from 'lucide-react'
import { useChatApi } from '@/hooks/useChatApi'
import { useConversationStream } from '@/hooks/useChatStream'
import { conversationStreamStore } from '@/lib/conversationStreamStore'
import { Markdown } from '@/components/chat/Markdown'
import { useThrottledValue } from '@/hooks/useThrottledValue'
import type { ChatMessage, Conversation } from '@/types'
import { cn } from '@/lib/utils'

interface RightChatPanelProps {
  onClose: () => void
  /** 外部触发的待发送提示词（卡片「AI 分析」），发送后回调消费 */
  pendingPrompt?: string | null
  onPromptConsumed?: () => void
}

/**
 * 操盘模式右侧 AI 对话栏（spec 第二阶段）。
 * 独立于主控台的对话体系：复用 conversation 表（kind='panel'），走主 Agent 委派链路。
 * 顶部栏：靠左「对话名称 + ✎ 编辑」，靠右「历史 ▾ / ＋新建 / ✕关闭」。
 */
export function RightChatPanel({ onClose, pendingPrompt, onPromptConsumed }: RightChatPanelProps) {
  const { createConversation, listConversations, renameConversation, getMessages } = useChatApi()

  const [convs, setConvs] = useState<Conversation[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  // 流式状态按会话隔离存放于组件外：切换面板会话不中止流，切回即可见累积输出
  const { text: streamText, subagentCards, isStreaming } = useConversationStream(selectedId)
  /** 当前选中会话 id 的实时镜像：流式结束后的异步回调据此判断是否仍停留在该会话 */
  const selectedIdRef = useRef<string | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [editing, setEditing] = useState(false)
  const [titleDraft, setTitleDraft] = useState('')
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  const selected = useMemo(() => convs.find((c) => c.id === selectedId) ?? null, [convs, selectedId])

  // 初始化：加载 panel 会话；无会话时自动新建
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const list = await listConversations({ kind: 'panel' }).catch(() => [])
      if (cancelled) return
      setConvs(list)
      if (list.length > 0) {
        setSelectedId(list[0].id)
      } else {
        const conv = await createConversation(undefined, 'panel').catch(() => null)
        if (!cancelled && conv) {
          setConvs([conv])
          setSelectedId(conv.id)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // 同步选中会话镜像（供流式结束后的异步回调判断回填目标）
  useEffect(() => {
    selectedIdRef.current = selectedId
  }, [selectedId])

  // 切换会话时加载消息；不中止其它会话的流
  useEffect(() => {
    setMessages([])
    if (!selectedId) return
    let cancelled = false
    getMessages(selectedId)
      .then((list) => {
        if (!cancelled) setMessages(list)
      })
      .catch(() => {
        if (!cancelled) setMessages([])
      })
    return () => {
      cancelled = true
    }
  }, [selectedId]) // eslint-disable-line react-hooks/exhaustive-deps

  // 滚动到底部
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, streamText, subagentCards.length, isStreaming])

  const refreshConvs = useCallback(async () => {
    const list = await listConversations({ kind: 'panel' }).catch(() => [])
    setConvs(list)
  }, [listConversations])

  const handleNew = useCallback(async () => {
    setHistoryOpen(false)
    setMessages([])
    const conv = await createConversation(undefined, 'panel').catch(() => null)
    if (!conv) return
    setConvs((prev) => [conv, ...prev])
    setSelectedId(conv.id)
  }, [createConversation])

  const handleSelect = useCallback(
    (id: string) => {
      setHistoryOpen(false)
      setSelectedId(id)
    },
    [],
  )

  const handleRename = useCallback(async () => {
    const title = titleDraft.trim()
    if (!selectedId || !title) return
    await renameConversation(selectedId, title).catch(() => {})
    setEditing(false)
    await refreshConvs()
  }, [selectedId, titleDraft, renameConversation, refreshConvs])

  // 发送一条消息：乐观插入 → 流式 → 刷新落库消息 → 刷新会话标题
  const sendContent = useCallback(
    async (content: string) => {
      if (!content || !selectedId) return
      const temp: ChatMessage = {
        id: `tmp-${Date.now()}`,
        conversationId: selectedId,
        role: 'user',
        content,
        sequence: messages.length + 1,
        createdAt: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, temp])
      await conversationStreamStore.start(selectedId, content)
      // 仅当用户仍停留在该会话时回填，避免覆盖其它会话的消息
      const fresh = await getMessages(selectedId).catch(() => null)
      if (fresh && selectedIdRef.current === selectedId) setMessages(fresh)
      conversationStreamStore.clear(selectedId)
      await refreshConvs()
    },
    [selectedId, messages.length, getMessages, refreshConvs],
  )

  const handleSend = useCallback(async () => {
    const content = input.trim()
    if (!content) return
    setInput('')
    await sendContent(content)
  }, [input, sendContent])

  // 外部触发的预设提示词（卡片「AI 分析」）：待选中会话就绪后自动发送
  useEffect(() => {
    if (pendingPrompt && selectedId) {
      onPromptConsumed?.()
      sendContent(pendingPrompt)
    }
  }, [pendingPrompt, selectedId, sendContent, onPromptConsumed])

  const displayTitle = selected?.title ?? 'AI 分析对话'

  return (
    <aside className="flex h-full w-full flex-col">
      {/* 顶部栏：靠左 标题+编辑；靠右 历史/新建/关闭 */}
      <div className="flex shrink-0 items-center gap-1 border-b border-[var(--color-border-light)] px-3 py-2">
        {/* 靠左：对话名称 + 编辑 */}
        <div className="flex min-w-0 flex-1 items-center gap-1">
          {editing ? (
            <input
              autoFocus
              value={titleDraft}
              onChange={(e) => setTitleDraft(e.target.value)}
              onBlur={handleRename}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleRename()
                if (e.key === 'Escape') setEditing(false)
              }}
              className="min-w-0 flex-1 rounded border border-[var(--color-accent)] bg-white px-2 py-1 text-xs text-[var(--color-text-primary)] outline-none"
            />
          ) : (
            <>
              <span className="min-w-0 flex-1 truncate text-xs font-medium text-[var(--color-text-primary)]">
                {displayTitle}
              </span>
              <button
                onClick={() => {
                  setTitleDraft(displayTitle)
                  setEditing(true)
                }}
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded text-[var(--color-text-tertiary)] hover:bg-[var(--color-bg-hover)] hover:text-[var(--color-text-secondary)] transition-colors"
                title="重命名对话"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
            </>
          )}
        </div>

        {/* 靠右：历史 / 新建 / 关闭 */}
        <div className="flex shrink-0 items-center gap-0.5">
          <div className="relative">
            <button
              onClick={() => setHistoryOpen((v) => !v)}
              className={cn(
                'flex h-6 w-6 items-center justify-center rounded transition-colors',
                historyOpen
                  ? 'bg-[var(--color-accent-soft)] text-[var(--color-accent)]'
                  : 'text-[var(--color-text-tertiary)] hover:bg-[var(--color-bg-hover)] hover:text-[var(--color-text-secondary)]',
              )}
              title="历史消息"
            >
              <History className="h-3.5 w-3.5" />
            </button>

            {/* 历史会话下拉 */}
            {historyOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setHistoryOpen(false)} />
                <div className="absolute right-0 top-7 z-20 w-56 rounded-lg border border-[var(--color-border)] bg-white p-1.5 shadow-lg">
                  <p className="px-2 py-1 text-xs font-medium text-[var(--color-text-tertiary)] uppercase tracking-wider">
                    历史对话
                  </p>
                  {convs.length === 0 ? (
                    <p className="px-2 py-2 text-xs text-[var(--color-text-tertiary)]">暂无历史对话</p>
                  ) : (
                    <div className="flex max-h-56 flex-col overflow-y-auto">
                      {convs.map((c) => (
                        <button
                          key={c.id}
                          onClick={() => handleSelect(c.id)}
                          className={cn(
                            'flex h-8 items-center rounded-md px-2 text-left text-xs transition-colors',
                            selectedId === c.id
                              ? 'bg-[var(--color-accent-soft)] font-medium text-[var(--color-text-primary)]'
                              : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)]',
                          )}
                        >
                          <span className="flex-1 truncate">{c.title}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </>
            )}
          </div>

          <button
            onClick={handleNew}
            className="flex h-6 w-6 items-center justify-center rounded text-[var(--color-text-tertiary)] hover:bg-[var(--color-bg-hover)] hover:text-[var(--color-text-secondary)] transition-colors"
            title="新建对话"
          >
            <MessageSquarePlus className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={onClose}
            className="flex h-6 w-6 items-center justify-center rounded text-[var(--color-text-tertiary)] hover:bg-[var(--color-bg-hover)] hover:text-[var(--color-danger)] transition-colors"
            title="关闭对话栏"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* 消息区 */}
      <div className="flex-1 overflow-y-auto scrollbar-hide px-3 py-3">
        {messages.length === 0 && !streamText && subagentCards.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-1 text-center">
            <div className="rounded-full bg-[var(--color-bg-subtle)] p-2.5">
              <MessageSquarePlus className="h-4 w-4 text-[var(--color-text-tertiary)]" />
            </div>
            <p className="text-xs text-[var(--color-text-tertiary)]">与 AI 对话，解读数据或咨询问题</p>
          </div>
        ) : (
          <div className="flex flex-col">
            {messages.map((msg) => (
              <Bubble key={msg.id} msg={msg} />
            ))}
            {/* 流式子代理卡（简洁状态条） */}
            {subagentCards.map((card) => (
              <div key={card.taskId} className="mb-3 flex items-center gap-1.5 rounded-md bg-[var(--color-bg-subtle)] px-2.5 py-1.5">
                {isStreaming ? (
                  <Loader2 className="h-3 w-3 animate-spin text-[var(--color-accent)]" />
                ) : (
                  <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-success)]" />
                )}
                <span className="text-xs text-[var(--color-text-secondary)]">{card.name} 分析中…</span>
              </div>
            ))}
            {/* 流式回复 */}
            {streamText && (
              <div className="mb-3 flex justify-start">
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--color-accent-soft)] text-xs mr-2 mt-1">AI</div>
                <div className="max-w-[80%] rounded-2xl rounded-bl-md border border-[var(--color-border-light)] bg-[var(--color-bg-surface)] px-3 py-2 text-xs leading-relaxed text-[var(--color-text-primary)]">
                  <StreamingMarkdown text={streamText} />
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* 输入区 */}
      <div className="shrink-0 border-t border-[var(--color-border-light)] p-3">
        <div className="flex items-end gap-2 rounded-xl border border-[var(--color-border)] bg-white px-3 py-2 focus-within:border-[var(--color-accent)]">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSend()
              }
            }}
            rows={1}
            placeholder="输入消息，Enter 发送…"
            className="max-h-24 flex-1 resize-none bg-transparent text-xs text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-placeholder)] leading-relaxed"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isStreaming}
            className={cn(
              'flex h-6 w-6 shrink-0 items-center justify-center rounded-lg transition-all',
              input.trim() && !isStreaming
                ? 'text-[var(--color-accent)] hover:bg-[var(--color-accent-soft)]'
                : 'text-[var(--color-text-placeholder)]',
            )}
          >
            <SendHorizonal className="h-4 w-4" />
          </button>
        </div>
      </div>
    </aside>
  )
}

/** 右侧面板流式 Markdown：节流渲染 + 光标（紧凑风格，与 Bubble 字号体系一致） */
function StreamingMarkdown({ text }: { text: string }) {
  const throttled = useThrottledValue(text)
  return <Markdown content={throttled} streaming compact />
}

/** 消息气泡（用户右 / AI 左） */
function Bubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === 'user'
  return (
    <div className={cn('mb-3 flex', isUser ? 'justify-end' : 'justify-start')}>
      {!isUser && (
        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--color-accent-soft)] text-xs mr-2 mt-1">
          AI
        </div>
      )}
      <div
        className={cn(
          'max-w-[80%] rounded-2xl px-3 py-2 text-xs leading-relaxed',
          isUser
            ? 'rounded-br-md bg-[var(--color-accent)] text-white'
            : 'rounded-bl-md border border-[var(--color-border-light)] bg-[var(--color-bg-surface)] text-[var(--color-text-primary)]',
        )}
      >
        {isUser ? (
          <span className="whitespace-pre-wrap">{msg.content}</span>
        ) : (
          <Markdown content={msg.content} compact />
        )}
      </div>
      {isUser && (
        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--color-bg-subtle)] text-xs ml-2 mt-1">
          我
        </div>
      )}
    </div>
  )
}
