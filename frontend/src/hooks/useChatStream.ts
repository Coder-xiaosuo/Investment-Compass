import { useCallback, useRef, useState } from 'react'
import type { Citation, Decision, HITLRequest, SubagentCardState, Todo } from '@/types'

interface StreamEvent {
  type: string
  [key: string]: any
}

/** 从 SSE 块中解析出 data: 行的 JSON 事件（无事件时返回 null） */
function parseDataEvent(part: string): StreamEvent | null {
  for (const line of part.split('\n')) {
    if (line.startsWith('data:')) {
      const payload = line.slice(5).trim()
      if (!payload) continue
      try {
        return JSON.parse(payload) as StreamEvent
      } catch {
        // 忽略无法解析的行
      }
    }
  }
  return null
}

export function useChatStream() {
  const [streamText, setStreamText] = useState('')
  /** 主 Agent 思维链（thinking 事件实时增量，DeepSeek reasoning_content） */
  const [thinkingText, setThinkingText] = useState('')
  /** 本次流引用的信息来源（advisory subagent_result 透传） */
  const [citations, setCitations] = useState<Citation[]>([])
  const [subagentCards, setSubagentCards] = useState<SubagentCardState[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  // ── Agent 待办列表（write_todos 实时透传，完整替换）──
  const [todos, setTodos] = useState<Todo[]>([])
  // ── HITL 中断状态 ──
  const [isInterrupted, setIsInterrupted] = useState(false)
  const [interruptData, setInterruptData] = useState<HITLRequest | null>(null)
  const [threadId, setThreadId] = useState<string | null>(null)
  const [isResuming, setIsResuming] = useState(false)
  /** 当前上下文真实占用（usage 事件实时透传；与后端 context_tokens 同口径） */
  const [contextTokens, setContextTokens] = useState<number | null>(null)

  const abortRef = useRef<AbortController | null>(null)
  /** 最近一次 sendStream 使用的会话 id（resume 复用同一会话） */
  const conversationIdRef = useRef<string | null>(null)
  /** 标记本轮流中是否产出过 interrupt 事件（同步判断，避免依赖 setState 异步） */
  const sawInterruptRef = useRef(false)

  const cancelStream = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
  }, [])

  const resetStream = useCallback(() => {
    setStreamText('')
    setThinkingText('')
    setCitations([])
    setSubagentCards([])
    setTodos([])
    setIsStreaming(false)
    setIsInterrupted(false)
    setInterruptData(null)
    setThreadId(null)
    setIsResuming(false)
    setContextTokens(null)
    sawInterruptRef.current = false
  }, [])

  /** 解析并应用单个 SSE 事件到展示状态（sendStream 与 resume 共用）。 */
  const applyEvent = useCallback((event: StreamEvent) => {
    switch (event.type) {
      case 'chunk':
        if (typeof event.chunk === 'string' && event.chunk) {
          setStreamText((t) => t + event.chunk)
        }
        break

      case 'thinking': {
        // 主 Agent 思维链增量（DeepSeek reasoning_content，thinking 模式开启时）
        if (typeof event.content === 'string' && event.content) {
          setThinkingText((t) => t + event.content)
        }
        break
      }

      case 'subagent_started': {
        const taskId = String(event.task_id ?? '')
        setSubagentCards((prev) => {
          if (!taskId || prev.some((c) => c.taskId === taskId)) return prev
          return [
            ...prev,
            {
              taskId,
              name: String(event.subagent ?? 'task'),
              status: 'running' as const,
              stages: [],
            },
          ]
        })
        break
      }

      case 'stage': {
        const taskId = String(event.task_id ?? '')
        const stage = String(event.stage ?? '')
        const rawStatus = String(event.status ?? '')
        const status = rawStatus === 'done' ? 'done' : 'started'
        setSubagentCards((prev) =>
          prev.map((card) => {
            if (taskId && card.taskId !== taskId) return card
            if (!taskId && card.name !== event.subagent) return card
            if (card.status !== 'running') return card

            const rec: SubagentCardState['stages'][number] = {
              stage: stage as any,
              status,
            }
            if (event.score != null) rec.score = Number(event.score)
            if (event.direction) rec.direction = String(event.direction)
            // advisory 资讯子 Agent 附加字段（intent/检索数量/置信度/引用源）
            if (event.intent) rec.intent = String(event.intent)
            if (event.news_count != null) rec.newsCount = Number(event.news_count)
            if (event.report_count != null) rec.reportCount = Number(event.report_count)
            if (event.confidence != null) rec.confidence = Number(event.confidence)
            if (event.citations != null) rec.citations = Number(event.citations)
            // 联网搜索降级状态（status=web_search_* 时记录，不覆盖主状态）
            if (rawStatus.startsWith('web_search_')) {
              rec.webSearch = rawStatus.replace('web_search_', '') as any
            }

            const stages = [...card.stages]
            const idx = stages.findIndex((s) => s.stage === stage)
            if (idx >= 0) {
              stages[idx] = { ...stages[idx], ...rec }
            } else {
              stages.push(rec)
            }

            return {
              ...card,
              stockCode: card.stockCode || event.stock_code || undefined,
              stockName: card.stockName || event.stock_name || undefined,
              stages,
            }
          }),
        )
        break
      }

      case 'subagent_completed': {
        const taskId = String(event.task_id ?? '')
        setSubagentCards((prev) =>
          prev.map((c) => (c.taskId === taskId ? { ...c, status: 'completed' as const } : c)),
        )
        break
      }

      case 'subagent_result': {
        // advisory 子 Agent 结构化结果：提取引用来源列表（无则忽略）
        const result = event.result as { citations?: unknown } | undefined
        if (result && Array.isArray(result.citations) && result.citations.length > 0) {
          setCitations(result.citations as Citation[])
        }
        break
      }

      case 'todos': {
        // Agent 待办列表（完整替换，与后端 write_todos 语义一致）
        if (Array.isArray(event.todos)) {
          setTodos(event.todos)
        }
        break
      }

      case 'usage': {
        // 真实模型上下文占用（input_tokens 即送入模型的上下文量）
        if (typeof event.input_tokens === 'number' && event.input_tokens > 0) {
          setContextTokens(event.input_tokens)
        }
        break
      }

      case 'interrupt': {
        // HITL 中断：记录请求数据与线程 id，等待用户决策后 resume 续流
        const data = event.data as HITLRequest | undefined
        if (data && Array.isArray(data.action_requests) && data.action_requests.length > 0) {
          sawInterruptRef.current = true
          setInterruptData(data)
          setThreadId(event.thread_id ? String(event.thread_id) : null)
          setIsInterrupted(true)
        }
        break
      }

      default:
        break
    }
  }, [])

  /** 消费一个 SSE Response：分块解析并逐事件应用。 */
  const consumeStream = useCallback(
    async (res: Response) => {
      if (!res.ok || !res.body) {
        throw new Error(`stream request failed: HTTP ${res.status}`)
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n')
        buffer = parts.pop() ?? ''
        for (const part of parts) {
          const event = parseDataEvent(part)
          if (event) applyEvent(event)
        }
      }
      if (buffer.trim()) {
        const event = parseDataEvent(buffer)
        if (event) applyEvent(event)
      }
    },
    [applyEvent],
  )

  /**
   * 发送消息并消费后端 SSE 结构化事件流（token / 子 Agent 生命周期 / 阶段事件）。
   * @returns 是否以 HITL 中断结束（true 表示流被中断、等待用户决策）
   */
  const sendStream = useCallback(
    async (conversationId: string, content: string): Promise<boolean> => {
      // 取消上一轮未完成的流
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller
      conversationIdRef.current = conversationId

      setStreamText('')
      setThinkingText('')
      setCitations([])
      setSubagentCards([])
      setTodos([])
      setIsStreaming(true)
      setIsInterrupted(false)
      setInterruptData(null)
      setThreadId(null)
      setIsResuming(false)
      setContextTokens(null)
      sawInterruptRef.current = false

      try {
        const res = await fetch(`/api/chat/conversation/${conversationId}/message/stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content, content_type: 'text' }),
          signal: controller.signal,
        })
        await consumeStream(res)
      } catch (err: any) {
        // 主动取消不视为错误
        if (err?.name !== 'AbortError') {
          console.error('[useChatStream] stream failed:', err)
          setSubagentCards((prev) =>
            prev.map((c) => ({ ...c, status: 'interrupted' as const })),
          )
        }
        return false
      } finally {
        setIsStreaming(false)
        if (abortRef.current === controller) {
          abortRef.current = null
        }
      }
      return sawInterruptRef.current
    },
    [consumeStream],
  )

  /**
   * HITL resume：提交用户决策，恢复中断线程的 SSE 续流并合并进当前展示状态。
   * @returns 续流后是否仍处于中断（true 表示再次中断、等待新一轮决策）
   */
  const resume = useCallback(
    async (decisions: Decision[]): Promise<boolean> => {
      const conversationId = conversationIdRef.current
      if (!conversationId) return false

      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller
      sawInterruptRef.current = false
      // 续流期间保持中断卡片可见，但展示为"分析中"
      setIsResuming(true)

      try {
        const res = await fetch(`/api/chat/${conversationId}/resume`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ decisions }),
          signal: controller.signal,
        })
        await consumeStream(res)

        const stillInterrupted = sawInterruptRef.current
        // 续流正常结束（未再次中断）→ 清理中断状态
        if (!stillInterrupted) {
          setIsInterrupted(false)
          setInterruptData(null)
          setThreadId(null)
        }
        return stillInterrupted
      } catch (err: any) {
        // 主动取消不视为错误；失败时保留中断状态，允许用户重试
        if (err?.name !== 'AbortError') {
          console.error('[useChatStream] resume failed:', err)
        }
        return true
      } finally {
        setIsResuming(false)
        setIsStreaming(false)
        if (abortRef.current === controller) {
          abortRef.current = null
        }
      }
    },
    [consumeStream],
  )

  return {
    sendStream,
    cancelStream,
    resetStream,
    resume,
    streamText,
    thinkingText,
    citations,
    subagentCards,
    todos,
    isStreaming,
    isInterrupted,
    interruptData,
    threadId,
    isResuming,
    contextTokens,
  }
}
