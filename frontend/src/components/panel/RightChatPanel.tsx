import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { History, MessageSquarePlus, X, Pencil, SendHorizonal, SquareStop, Loader2 } from 'lucide-react'
import { useChatApi } from '@/hooks/useChatApi'
import { useConversationStream } from '@/hooks/useChatStream'
import { conversationStreamStore, STREAM_RECONCILE_DELAY_MS } from '@/lib/conversationStreamStore'
import { Markdown } from '@/components/chat/Markdown'
import { StreamOutcomeNotice, StreamStatusBar } from '@/components/chat/StreamStatusBar'
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
  const { text: streamText, subagentCards, isStreaming, outcome, isInterrupting } =
    useConversationStream(selectedId)
  /** 当前选中会话 id 的实时镜像：流式结束后的异步回调据此判断是否仍停留在该会话 */
  const selectedIdRef = useRef<string | null>(null)
  /** 最近一次发送前的本地 assistant 条数：判断后端是否已落库本轮消息 */
  const assistantCountRef = useRef(0)
  /** messages 的实时镜像：让 sendContent 依赖稳定，避免预设提示词 effect 反复触发 */
  const messagesRef = useRef<ChatMessage[]>(messages)
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

  // 同步消息镜像（sendContent 通过 ref 读取，保持依赖稳定）
  useEffect(() => {
    messagesRef.current = messages
  }, [messages])

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

  /**
   * 流收尾对账：延迟等待后端落库后刷新消息（同主控台策略）。
   * 仅当后端确实落库了本轮助手消息时才清空流式状态，否则保留内容与提示；
   * 若该会话已被新一轮接管（用户打断后自动重发）则跳过清空，避免清掉新流的展示状态。
   */
  const reconcile = useCallback(
    async (convId: string, baselineAssistantCount: number) => {
      await new Promise((resolve) => setTimeout(resolve, STREAM_RECONCILE_DELAY_MS))
      const fresh = await getMessages(convId).catch(() => null)
      if (!fresh) return
      if (selectedIdRef.current === convId) setMessages(fresh)
      const persisted = fresh.filter((m) => m.role === 'assistant').length > baselineAssistantCount
      if (persisted && !conversationStreamStore.hasActiveStream(convId)) {
        conversationStreamStore.clear(convId)
      }
    },
    [getMessages],
  )

  // 发送一条消息：乐观插入 → 流式 → 延迟对账 → 刷新会话标题。
  // 若该会话已有流在进行，走「软取消 + 自动重发」（旧流在安全检查点主动退出，
  // 避免打断执行到一半的工具调用），随后自动发出本条消息
  const sendContent = useCallback(
    async (content: string) => {
      if (!content || !selectedId) return
      const current = messagesRef.current
      const baselineAssistantCount = current.filter((m) => m.role === 'assistant').length
      assistantCountRef.current = baselineAssistantCount
      const temp: ChatMessage = {
        id: `tmp-${Date.now()}`,
        conversationId: selectedId,
        role: 'user',
        content,
        sequence: current.length + 1,
        createdAt: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, temp])
      // 被中断的旧轮内容以带「用户手动中断」标记的消息交接回来，须插在本条用户
      // 消息之前，否则「一问一答」的时间顺序会颠倒
      await conversationStreamStore.interrupt(selectedId, content, {
        onRoundInterrupted: (message) =>
          setMessages((prev) => {
            const idx = prev.findIndex((m) => m.id === temp.id)
            if (idx < 0) return [...prev, message]
            return [...prev.slice(0, idx), message, ...prev.slice(idx)]
          }),
      })
      await reconcile(selectedId, baselineAssistantCount)
      await refreshConvs()
    },
    [selectedId, reconcile, refreshConvs],
  )

  const handleSend = useCallback(async () => {
    const content = input.trim()
    if (!content) return
    setInput('')
    await sendContent(content)
  }, [input, sendContent])

  /**
   * 停止生成：硬中断当前面板会话的流（已产出内容保留），随后延迟对账。
   * 也是「软取消等待期间再次点击」的出口：立即 abort，不等安全检查点；
   * 用户此前排队的新消息仍会在旧流收尾后自动发出。
   */
  const handleStop = useCallback(() => {
    const convId = selectedIdRef.current
    if (!convId) return
    conversationStreamStore.cancel(convId)
    void reconcile(convId, assistantCountRef.current)
  }, [reconcile])

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
        {messages.length === 0 && !streamText && subagentCards.length === 0 && !outcome ? (
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
            {/* 生成中：中立等待提示（不判定断连） */}
            {isStreaming && selectedId && <StreamStatusBar conversationId={selectedId} />}
            {/* 已停止 / 未正常结束：内容保留提示 */}
            {!isStreaming && <StreamOutcomeNotice outcome={outcome} />}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* 输入区 */}
      <div className="shrink-0 border-t border-[var(--color-border-light)] p-3">
        {/* 等待态：新消息已排队，正在软取消旧流 */}
        {isInterrupting && (
          <div className="mb-2 flex items-center gap-1.5 rounded-md bg-[var(--color-bg-subtle)] px-2.5 py-1.5">
            <Loader2 className="h-3 w-3 shrink-0 animate-spin text-[var(--color-warning)]" />
            <span className="text-xs text-[var(--color-text-secondary)]">
              已收到你的消息，正在打断当前任务，稍后自动发送…
            </span>
          </div>
        )}
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
            disabled={isInterrupting}
            placeholder={isInterrupting ? '正在打断当前任务…' : '输入消息，Enter 发送…'}
            className="max-h-24 flex-1 resize-none bg-transparent text-xs text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-placeholder)] leading-relaxed disabled:cursor-not-allowed"
          />
          {/* 生成中 → 停止生成；空闲 → 发送 */}
          {isStreaming ? (
            <button
              onClick={handleStop}
              title={
                isInterrupting
                  ? '立即中断当前任务'
                  : '停止生成'
              }
              className={cn(
                'flex h-6 w-6 shrink-0 items-center justify-center rounded-lg transition-all hover:bg-[var(--color-danger)]/10',
                isInterrupting ? 'text-[var(--color-danger)] animate-pulse' : 'text-[var(--color-danger)]',
              )}
            >
              <SquareStop className="h-4 w-4" />
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!input.trim()}
              className={cn(
                'flex h-6 w-6 shrink-0 items-center justify-center rounded-lg transition-all',
                input.trim()
                  ? 'text-[var(--color-accent)] hover:bg-[var(--color-accent-soft)]'
                  : 'text-[var(--color-text-placeholder)]',
              )}
            >
              <SendHorizonal className="h-4 w-4" />
            </button>
          )}
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
  /** 用户主动打断的助手消息（软取消时由后端落库 / 本地交接时打标） */
  const interrupted = !isUser && msg.card_data?.user_interrupted === true
  return (
    <div className="mb-3">
      <div className={cn('flex', isUser ? 'justify-end' : 'justify-start')}>
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
      {/* 用户手动打断：本条回复是打断前已产出的部分内容 */}
      {interrupted && (
        <div className="mt-1 flex items-center gap-1 pl-8 text-xs text-[var(--color-text-tertiary)]">
          <SquareStop className="h-3 w-3 shrink-0" />
          <span>用户手动中断，以上为已产出的部分内容</span>
        </div>
      )}
    </div>
  )
}
