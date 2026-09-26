import { createParser, type EventSourceMessage } from 'eventsource-parser'
import type {
  ChatMessage,
  Citation,
  Decision,
  HITLRequest,
  StreamDisplay,
  StreamOutcome,
  SubagentCardState,
  Todo,
} from '@/types'

/**
 * 会话级流式状态仓库（模块级单例，位于 React 组件树之外）。
 *
 * 设计目标：流式任务的生命周期与组件树、与 selectedId 解耦。
 * - 每个 conversationId 独立持有一份展示状态与一个 AbortController；
 * - chunk 实时写入对应会话的状态，切换会话后切回即可读到累积结果；
 * - 组件卸载 / 切换会话都不中止流，只有显式中止才 abort：
 *   interrupt() 用户在有流时发新消息 → 先发「软取消」信号，旧流在安全点主动退出，
 *              旧流结束后自动发起新请求（不暴力 abort，避免打断执行到一半的工具调用）
 *   cancel()  用户「停止生成」→ 硬中断：立即 abort 但保留已产出内容（outcome='aborted'）
 *   discard() 会话被删除       → 中止并清空展示状态
 */

/**
 * 停止 / 异常结束后的延迟对账时长。
 *
 * 用户点「停止生成」触发 abort 后，后端在 generator 的 finally 中才落库，
 * 需要几十~几百毫秒；立即 getMessages 会读不到那条 assistant 消息，
 * 表现为「点了停止，内容反而消失」。故延迟一段时间再对账。
 */
export const STREAM_RECONCILE_DELAY_MS = 1000

/** 空流状态单例：保证无内容时 getSnapshot 引用稳定（useSyncExternalStore 要求） */
export const EMPTY_STREAM_DISPLAY: StreamDisplay = {
  text: '',
  thinkingText: '',
  citations: [],
  subagentCards: [],
  todos: [],
  isStreaming: false,
  isInterrupted: false,
  interruptData: null,
  threadId: null,
  isResuming: false,
  contextTokens: null,
  outcome: null,
  isInterrupting: false,
}

interface StreamEvent {
  type: string
  [key: string]: any
}

interface StreamRuntime {
  controller: AbortController
  /** 本轮流是否产出过 interrupt 事件（同步判断，避免依赖异步 state） */
  sawInterrupt: boolean
  /** 是否收到后端 {"done": true} 结束事件（未收到即为截断） */
  sawDone: boolean
  /** 是否由用户主动点击「停止生成」触发的中止 */
  cancelledByUser: boolean
  /** 本轮流是否命中过服务端软取消（用户发新消息触发的协作式退出） */
  sawSoftCancel: boolean
  /** 本轮开始时间（等待时长提示用，不入快照避免高频 commit） */
  startedAt: number
  /** 最近一次收到业务事件的时间（同上） */
  lastEventAt: number
  /** 本轮流收尾（end/discard）时兑现：供 interrupt() 编排「旧流结束 → 自动重发」 */
  settled: Promise<void>
  resolveSettled: () => void
}

/** 流式时序元信息（供等待提示条使用；与展示快照分离，避免每秒触发 commit） */
export interface StreamMeta {
  startedAt: number
  lastEventAt: number
}

/**
 * 将 SSE 消息的 data 解析为后端结构化事件（非法 JSON 返回 null）。
 *
 * 分帧（含 CRLF/CR、多行 data 拼接、注释与空行）由 eventsource-parser 按规范处理，
 * 此处只负责 JSON 解码与类型收窄。
 */
function parseEventMessage(message: EventSourceMessage): StreamEvent | null {
  const payload = message.data.trim()
  if (!payload) return null
  try {
    return JSON.parse(payload) as StreamEvent
  } catch {
    return null
  }
}

class ConversationStreamStore {
  private states = new Map<string, StreamDisplay>()
  private listeners = new Map<string, Set<() => void>>()
  private runtimes = new Map<string, StreamRuntime>()

  /** 读取某会话当前展示状态（无变化时返回同一引用） */
  getSnapshot = (conversationId: string): StreamDisplay =>
    this.states.get(conversationId) ?? EMPTY_STREAM_DISPLAY

  /** 订阅某会话的状态变化；返回取消订阅函数 */
  subscribe = (conversationId: string, listener: () => void): (() => void) => {
    let set = this.listeners.get(conversationId)
    if (!set) {
      set = new Set()
      this.listeners.set(conversationId, set)
    }
    const listeners = set
    listeners.add(listener)
    return () => {
      listeners.delete(listener)
      if (listeners.size === 0) this.listeners.delete(conversationId)
    }
  }

  /**
   * 硬中断（用户点击「停止生成」，或在软取消等待期间再次点击）：
   * 立即 abort，不等安全边界，**保留已产出内容**。
   *
   * 不清理展示状态 —— 中止会经 start()/resume() 的收尾逻辑写入
   * outcome='aborted'，内容留在 text 中等待调用方延迟对账。
   */
  cancel(conversationId: string): void {
    const runtime = this.runtimes.get(conversationId)
    if (!runtime) return
    runtime.cancelledByUser = true
    runtime.controller.abort()
  }

  /**
   * 用户在有流进行时发来新消息：先「软取消」旧流，旧流结束后自动发起新请求。
   *
   * 与硬中断的区别：软取消只向服务端写一个协作标记，旧流在下一个安全检查点
   * 主动退出并正常落库，避免把执行到一半的工具调用/写操作截断。
   *
   * 等待期间用户可再次点击「停止生成」触发硬中断（cancel），此时不再等安全边界，
   * 但用户已表达的新消息仍会在旧流收尾后发出。
   *
   * @param options.onRoundInterrupted 旧轮被用户打断且有产出时的交接回调：
   *   用于把这段内容落为一条消息（带 user_interrupted 标记）插入消息列表 ——
   *   新一轮 begin() 会重置展示状态，不交接则这段内容会从界面消失。
   * @returns 新请求的收尾结果：是否以 HITL 中断结束（与 start() 语义一致）
   */
  async interrupt(
    conversationId: string,
    content: string,
    options?: { onRoundInterrupted?: (message: ChatMessage) => void },
  ): Promise<boolean> {
    const runtime = this.runtimes.get(conversationId)
    // 无进行中的流：不存在竞态，直接发起新请求
    if (!runtime) return this.start(conversationId, content)

    // 1. 进入等待态：输入框据此禁用并提示「正在打断」，新请求暂不发出
    const prev = this.states.get(conversationId) ?? EMPTY_STREAM_DISPLAY
    this.commit(conversationId, { ...prev, isInterrupting: true })

    // 2. 软取消信号：旧流在下一个安全检查点主动退出
    const delivered = await this.notifySoftCancel(conversationId)
    if (!delivered) {
      // 信号未送达（网络/服务端异常）→ 不做无谓等待，直接硬中断兜底
      runtime.cancelledByUser = true
      runtime.controller.abort()
    }

    // 3. 等旧流收尾（软取消命中则正常结束；兜底硬中断则为 abort 后的收尾）
    await runtime.settled

    // 3.5 交接被打断的旧轮内容（详见参数说明），随后新一轮会重置展示状态
    this.handOffInterruptedRound(conversationId, runtime, options?.onRoundInterrupted)

    // 4. 旧流结束后自动发起新请求
    return this.start(conversationId, content)
  }

  /**
   * 交接被打断的旧轮
   */
  private handOffInterruptedRound(
    conversationId: string,
    runtime: StreamRuntime,
    onRoundInterrupted?: (message: ChatMessage) => void,
  ): void {
    if (!onRoundInterrupted) return
    if (!runtime.sawSoftCancel && !runtime.cancelledByUser) return
    const state = this.states.get(conversationId)
    if (!state?.text) return
    onRoundInterrupted({
      id: `local-interrupted-${Date.now()}`,
      conversationId,
      role: 'assistant',
      content: state.text,
      content_type: 'text',
      sequence: 0,
      card_data: { user_interrupted: true },
      createdAt: new Date().toISOString(),
    })
  }

  /** 发送软取消信号，返回是否送达服务端 */
  private async notifySoftCancel(conversationId: string): Promise<boolean> {
    try {
      const res = await fetch(`/api/chat/conversation/${conversationId}/interrupt`, {
        method: 'POST',
      })
      return res.ok
    } catch {
      return false
    }
  }

  /** 彻底丢弃该会话的流（中止 + 清空展示状态）：会话被删除时使用 */
  discard(conversationId: string): void {
    const runtime = this.runtimes.get(conversationId)
    runtime?.controller.abort()
    // 兑现等待句柄：避免 interrupt() 的编排在会话被删除后永久挂起
    runtime?.resolveSettled()
    this.runtimes.delete(conversationId)
    this.clear(conversationId)
  }

  /** 读取该会话的流式时序元信息（仅在流进行中有值） */
  getStreamMeta = (conversationId: string): StreamMeta | null => {
    const runtime = this.runtimes.get(conversationId)
    if (!runtime) return null
    return { startedAt: runtime.startedAt, lastEventAt: runtime.lastEventAt }
  }

  /**
   * 该会话当前是否有流在运行。
   *
   * 供延迟对账判断：若新一轮已接管该会话（用户打断后自动重发），
   * 上一轮的对账不得清理展示状态，否则会清掉正在进行的流。
   */
  hasActiveStream = (conversationId: string): boolean => this.runtimes.has(conversationId)

  /** 清空该会话的流式展示状态（消息已落库并刷新后调用） */
  clear(conversationId: string): void {
    if (!this.states.has(conversationId)) return
    this.states.delete(conversationId)
    this.emit(conversationId)
  }

  /**
   * 发送消息并消费后端 SSE 结构化事件流。
   * @returns 是否以 HITL 中断结束（true 表示流被中断、等待用户决策）
   */
  async start(conversationId: string, content: string): Promise<boolean> {
    const runtime = this.begin(conversationId, 'start')
    try {
      const res = await fetch(`/api/chat/conversation/${conversationId}/message/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, content_type: 'text' }),
        signal: runtime.controller.signal,
      })
      await this.consume(conversationId, runtime, res)
    } catch (err: any) {
      // 主动取消不视为错误
      if (err?.name !== 'AbortError') {
        console.error('[conversationStreamStore] stream failed:', err)
        const prev = this.states.get(conversationId)
        if (prev) {
          this.commit(conversationId, {
            ...prev,
            subagentCards: prev.subagentCards.map((c) => ({ ...c, status: 'interrupted' as const })),
          })
        }
      }
      return false
    } finally {
      this.end(conversationId, runtime)
    }
    return runtime.sawInterrupt
  }

  /**
   * HITL resume：提交用户决策，恢复中断线程的 SSE 续流并合并进该会话的展示状态。
   * @returns 续流后是否仍处于中断（true 表示再次中断、等待新一轮决策）
   */
  async resume(conversationId: string, decisions: Decision[]): Promise<boolean> {
    const runtime = this.begin(conversationId, 'resume')
    try {
      const res = await fetch(`/api/chat/${conversationId}/resume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decisions }),
        signal: runtime.controller.signal,
      })
      await this.consume(conversationId, runtime, res)

      const stillInterrupted = runtime.sawInterrupt
      // 续流正常结束（未再次中断）→ 清理中断状态
      if (!stillInterrupted) {
        const prev = this.states.get(conversationId)
        if (prev) {
          this.commit(conversationId, { ...prev, isInterrupted: false, interruptData: null, threadId: null })
        }
      }
      return stillInterrupted
    } catch (err: any) {
      // 用户主动停止 / 被新流替换：以是否再次中断为准，交由调用方按 outcome 处理
      if (err?.name === 'AbortError') return runtime.sawInterrupt
      // 失败时保留中断状态，允许用户重试
      console.error('[conversationStreamStore] resume failed:', err)
      return true
    } finally {
      this.end(conversationId, runtime)
    }
  }

  // ── 内部实现 ──────────────────────────────────────────────────────────────

  /** 开启一轮流：接管该会话的运行时（旧流被替换），并初始化展示状态 */
  private begin(conversationId: string, mode: 'start' | 'resume'): StreamRuntime {
    // 同一会话重入 → 替换旧流（不影响其它会话）
    const replaced = this.runtimes.get(conversationId)
    replaced?.controller.abort()
    // 兑现被替换流的等待句柄，避免 interrupt() 的编排悬空
    replaced?.resolveSettled()
    const now = Date.now()
    let resolveSettled: () => void = () => {}
    const settled = new Promise<void>((resolve) => {
      resolveSettled = resolve
    })
    const runtime: StreamRuntime = {
      controller: new AbortController(),
      sawInterrupt: false,
      sawDone: false,
      cancelledByUser: false,
      sawSoftCancel: false,
      startedAt: now,
      lastEventAt: now,
      settled,
      resolveSettled,
    }
    this.runtimes.set(conversationId, runtime)

    if (mode === 'start') {
      // 新一轮对话：清空旧展示内容
      this.states.set(conversationId, { ...EMPTY_STREAM_DISPLAY, isStreaming: true })
    } else {
      // 续流：保留已累积内容，仅切换生成中标记
      const prev = this.states.get(conversationId) ?? EMPTY_STREAM_DISPLAY
      this.states.set(conversationId, { ...prev, isStreaming: true, isResuming: true })
    }
    this.emit(conversationId)
    return runtime
  }

  /**
   * 收尾：仅当仍是当前运行时（未被新流替换）时复位标记并写入 outcome。
   *
   * outcome 判定（顺序即优先级）：
   *   cancelledByUser / sawSoftCancel → aborted（用户停止或软取消，内容保留）
   *   sawInterrupt    → interrupted（HITL 等待决策）
   *   sawDone         → completed（后端明确结束）
   *   否则            → failed（未收到 done 即断开，内容保留）
   */
  private end(conversationId: string, runtime: StreamRuntime): void {
    // 先兑现等待句柄：无论本轮是否已被新流替换，这一轮确实结束了，
    // interrupt() 的「旧流结束 → 自动重发」编排据此继续
    runtime.resolveSettled()
    if (this.runtimes.get(conversationId) !== runtime) return
    this.runtimes.delete(conversationId)
    const prev = this.states.get(conversationId)
    if (!prev) return
    const outcome: StreamOutcome =
      runtime.cancelledByUser || runtime.sawSoftCancel
        ? 'aborted'
        : runtime.sawInterrupt
          ? 'interrupted'
          : runtime.sawDone
            ? 'completed'
            : 'failed'
    // 等待态随本轮收尾一并复位（旧流已退出，等待中的新请求随后接管）
    this.commit(conversationId, {
      ...prev,
      isStreaming: false,
      isResuming: false,
      isInterrupting: false,
      outcome,
    })
  }

  /** 消费一个 SSE Response：交给 eventsource-parser 分帧后逐事件应用 */
  private async consume(conversationId: string, runtime: StreamRuntime, res: Response): Promise<void> {
    if (!res.ok || !res.body) {
      throw new Error(`stream request failed: HTTP ${res.status}`)
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder()

    // 按 SSE 规范分帧：兼容 \r\n / \r / \n 换行、跨 chunk 断行、多行 data 拼接与心跳注释
    const parser = createParser({
      onEvent: (message) => {
        const event = parseEventMessage(message)
        if (event) this.applyEvent(conversationId, runtime, event)
      },
    })

    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      parser.feed(decoder.decode(value, { stream: true }))
    }
    // 冲掉解码器尾部残留的多字节字符
    parser.feed(decoder.decode())
  }

  /** 解析并应用单个 SSE 事件（一次事件一次状态写入 + 一次通知） */
  private applyEvent(conversationId: string, runtime: StreamRuntime, event: StreamEvent): void {
    // 记录活跃时间（供等待提示条判断"是否长时间无新输出"）
    runtime.lastEventAt = Date.now()

    // 后端结束事件形如 {"done": true}（key 是 done 而非 type），
    // 是唯一可靠的「本轮正常结束」信号：收到它才算 completed，
    // 否则流被截断（网络中断、服务端异常），标记为 failed。
    if (event.done === true) {
      runtime.sawDone = true
      return
    }

    // 软取消命中（用户发新消息触发）：旧流在安全检查点主动退出，
    // 内容保留在 text 中，随后由 {"done": true} 正常收尾
    if (event.type === 'cancelled') {
      runtime.sawSoftCancel = true
      return
    }

    const prev = this.states.get(conversationId)
    if (!prev) return
    const draft: StreamDisplay = { ...prev }
    let changed = false

    switch (event.type) {
      case 'chunk': {
        if (typeof event.chunk === 'string' && event.chunk) {
          draft.text = prev.text + event.chunk
          changed = true
        }
        break
      }

      case 'thinking': {
        // 主 Agent 思维链增量（DeepSeek reasoning_content，thinking 模式开启时）
        if (typeof event.content === 'string' && event.content) {
          draft.thinkingText = prev.thinkingText + event.content
          changed = true
        }
        break
      }

      case 'subagent_started': {
        const taskId = String(event.task_id ?? '')
        if (taskId && !prev.subagentCards.some((c) => c.taskId === taskId)) {
          draft.subagentCards = [
            ...prev.subagentCards,
            { taskId, name: String(event.subagent ?? 'task'), status: 'running' as const, stages: [] },
          ]
          changed = true
        }
        break
      }

      case 'stage': {
        const taskId = String(event.task_id ?? '')
        const stage = String(event.stage ?? '')
        const rawStatus = String(event.status ?? '')
        const status = rawStatus === 'done' ? 'done' : 'started'
        draft.subagentCards = prev.subagentCards.map((card) => {
          if (taskId && card.taskId !== taskId) return card
          if (!taskId && card.name !== event.subagent) return card
          if (card.status !== 'running') return card

          const rec: SubagentCardState['stages'][number] = { stage: stage as any, status }
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
          if (idx >= 0) stages[idx] = { ...stages[idx], ...rec }
          else stages.push(rec)

          return {
            ...card,
            stockCode: card.stockCode || event.stock_code || undefined,
            stockName: card.stockName || event.stock_name || undefined,
            stages,
          }
        })
        changed = true
        break
      }

      case 'subagent_completed': {
        const taskId = String(event.task_id ?? '')
        draft.subagentCards = prev.subagentCards.map((c) =>
          c.taskId === taskId ? { ...c, status: 'completed' as const } : c,
        )
        changed = true
        break
      }

      case 'subagent_result': {
        // advisory 子 Agent 结构化结果：提取引用来源列表（无则忽略）
        const result = event.result as { citations?: unknown } | undefined
        if (result && Array.isArray(result.citations) && result.citations.length > 0) {
          draft.citations = result.citations as Citation[]
          changed = true
        }
        break
      }

      case 'todos': {
        // Agent 待办列表（完整替换，与后端 write_todos 语义一致）
        if (Array.isArray(event.todos)) {
          draft.todos = event.todos as Todo[]
          changed = true
        }
        break
      }

      case 'usage': {
        // 真实模型上下文占用（input_tokens 即送入模型的上下文量）
        if (typeof event.input_tokens === 'number' && event.input_tokens > 0) {
          draft.contextTokens = event.input_tokens
          changed = true
        }
        break
      }

      case 'interrupt': {
        // HITL 中断：记录请求数据与线程 id，等待用户决策后 resume 续流
        const data = event.data as HITLRequest | undefined
        if (data && Array.isArray(data.action_requests) && data.action_requests.length > 0) {
          runtime.sawInterrupt = true
          draft.interruptData = data
          draft.threadId = event.thread_id ? String(event.thread_id) : null
          draft.isInterrupted = true
          changed = true
        }
        break
      }

      default:
        break
    }

    if (changed) this.commit(conversationId, draft)
  }

  /** 写入状态并通知订阅者（状态在 clear 后到达的事件直接丢弃） */
  private commit(conversationId: string, next: StreamDisplay): void {
    if (!this.states.has(conversationId)) return
    this.states.set(conversationId, next)
    this.emit(conversationId)
  }

  private emit(conversationId: string): void {
    const listeners = this.listeners.get(conversationId)
    if (!listeners) return
    for (const listener of [...listeners]) listener()
  }
}

export const conversationStreamStore = new ConversationStreamStore()
