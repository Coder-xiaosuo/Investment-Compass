export type AppMode = 'analysis' | 'trading'

/** 操盘模式主区域顶部 Tab：技术面 / 基本面 / 市场概览 */
export type MainTab = 'technical' | 'fundamental' | 'market'

export interface Conversation {
  id: string
  title: string
  createdAt: string
  updatedAt: string
  /** 会话累计 token 用量（后端 conversation.token_count） */
  tokenCount?: number
  /** 当前上下文真实占用（后端 conversation.context_tokens，模型 input_tokens） */
  contextTokens?: number
}

export interface ChatMessage {
  id: string
  conversationId: string
  role: 'user' | 'assistant' | 'system'
  content: string
  content_type?: string
  sequence: number
  tokenCount?: number
  card_data?: Record<string, any>
  createdAt: string
}

/** 复合决策卡片数据结构（对应后端 card_data） */
export interface FusionDecision {
  decision: string
  summary: string
}

export interface ValueAssessment {
  final_score?: number
  final_level?: string
  blocked?: boolean
  block_reason?: string
  warnings?: string[]
  [key: string]: any
}

export interface DecisionCardData {
  symbol: string
  stock_name: string
  value_assessment: ValueAssessment
  pa_analysis: Record<string, any> | null
  fusion: FusionDecision
  content_type: string
  /** 后端 composite_decision 结构化结果（估值/技术分析），复盘字段可能挂在此处 */
  result?: Record<string, any> | null
  [key: string]: any
}

/** 复盘回填结果（decision_cards.review_outcome，verdict: HIT / MISS） */
export interface ReviewOutcome {
  verdict?: string
  actual_trend?: string
  profit_ratio?: number | string
  [key: string]: any
}

// ── 子 Agent 流式卡片 ────────────────────────────────────────────────────────

export type SubagentStageName = 'valuation' | 'technical' | 'plan' | 'retrieve' | 'synthesize'

export interface SubagentStage {
  stage: SubagentStageName
  status: 'started' | 'done'
  score?: number
  direction?: string
  // advisory 资讯子 Agent 阶段附加字段（plan/retrieve/synthesize）
  intent?: string
  newsCount?: number
  reportCount?: number
  confidence?: number
  /** 引用源数量（后端透传 len(citations)） */
  citations?: number
  /** 联网搜索降级状态（retrieve 阶段内，后端 status 为 web_search_* 时记录） */
  webSearch?: 'started' | 'done' | 'failed'
}

export type SubagentCardStatus = 'running' | 'completed' | 'interrupted'

/** 实时流中的子 Agent 卡片状态（由 SSE 事件驱动） */
export interface SubagentCardState {
  taskId: string
  name: string
  status: SubagentCardStatus
  stockCode?: string
  stockName?: string
  stages: SubagentStage[]
}

/** 待办项状态（与 langchain TodoListMiddleware 枚举一致） */
export type TodoStatus = 'pending' | 'in_progress' | 'completed'

/** Agent 待办项（write_todos 工具产出） */
export interface Todo {
  content: string
  status: TodoStatus
}

/** 资讯引用来源（对应后端 advisory Citation） */
export interface Citation {
  /** 数据源标识：em_news/cls_telegraph/em_global/research_reports/deepseek_web_search/llm_knowledge */
  source: string
  title: string
  publish_time?: string
  url?: string
}

/** 右侧栏来源内嵌 Tab（点击信息来源后新建，iframe 展示原文） */
export interface SourceTab {
  /** 唯一 id（用 url 去重，避免同源重复开 tab） */
  id: string
  title: string
  url: string
  /** 数据源标识（决定 iframe 是否可直嵌） */
  source: string
}

/**
 * 流式结束结果类型：
 * - completed   正常结束（收到后端 {"done": true}）
 * - interrupted HITL 中断，等待用户决策（可 resume）
 * - aborted     用户主动点击「停止生成」
 * - failed      流未正常结束（网络错误 / 未收到 done 即断开）
 */
export type StreamOutcome = 'completed' | 'interrupted' | 'aborted' | 'failed'

/** 流式会话的展示状态（App 持有，传给 ChatView 渲染） */
export interface StreamDisplay {
  text: string
  /** 主 Agent 思维链（DeepSeek reasoning_content 实时增量） */
  thinkingText: string
  subagentCards: SubagentCardState[]
  /** 本次流引用的信息来源（advisory 子 Agent subagent_result 透传） */
  citations?: Citation[]
  isStreaming: boolean
  /** Agent 待办列表（write_todos 实时透传，完整替换） */
  todos?: Todo[]
  /** 是否处于 HITL 中断（等待用户决策） */
  isInterrupted?: boolean
  /** HITL 中断请求数据（如估值确认） */
  interruptData?: HITLRequest | null
  /** 中断线程 id（resume 用） */
  threadId?: string | null
  /** 是否正在 resume 续流（中断卡片显示"分析中"） */
  isResuming?: boolean
  /** 当前上下文真实占用（usage 事件实时透传；与后端 context_tokens 同口径） */
  contextTokens?: number | null
  /** 本轮流的结束结果（由 store 在流收尾时写入；aborted/failed 时内容仍保留在 text 中） */
  outcome?: StreamOutcome | null
  /** 等待态：用户已发来新消息，正在软取消旧流；旧流退出后自动发出新请求 */
  isInterrupting?: boolean
}

// ── HITL 人工干预 ───────────────────────────────────────────────────────────

/** 用户对 HITL 中断的决策类型 */
export type DecisionType = 'approve' | 'reject' | 'respond'

/** 用户决策（resume 请求体 decisions 元素） */
export interface Decision {
  type: DecisionType
  message?: string
}

/** HITL 动作请求（interrupt 事件 data.action_requests 元素） */
export interface ActionRequest {
  name: string
  args: Record<string, any>
}

/** HITL 审核配置（data.review_configs 元素） */
export interface ReviewConfig {
  action_name: string
  allowed_decisions: DecisionType[]
}

/** HITL 中断请求体（SSE interrupt 事件 data 字段） */
export interface HITLRequest {
  action_requests: ActionRequest[]
  review_configs: ReviewConfig[]
}

/** SSE interrupt 事件 */
export interface InterruptEvent {
  type: 'interrupt'
  data: HITLRequest
  thread_id?: string
}

/** 后端落库的 assistant 消息 card_data（content_type="composite_decision"） */
export interface AnalysisTraceCardData {
  symbol?: string | null
  stock_name?: string | null
  analysis_trace?: SubagentStage[]
  result?: Record<string, any> | null
  [key: string]: any
}

// ── 设置中心（user-configurable API keys） ──────────────────────────────
export type ReasoningEffort = 'low' | 'medium' | 'high'
export type KlineAdjust = 'qfq' | 'hfq' | 'none'

export interface ProviderSettingsView {
  api_key_masked: string
  api_key_set: boolean
  model?: string
  base_url?: string
  thinking?: boolean
  reasoning_effort?: ReasoningEffort
  context_window?: number
  search_model?: string
  search_enabled?: boolean
}

export interface GeneralSettingsView {
  analysis_bar_count?: number
  refresh_interval_ms?: number
  context_warning_threshold_pct?: number
  last_data_source?: string
  kline_adjust?: KlineAdjust
  last_tradingview_exchange?: string
  last_symbol?: string
  last_timeframe?: string
  decision_flow_auto_play?: boolean
  decision_flow_play_seconds?: number
  alert_on_order_opportunity?: boolean
  incremental_max_new_bars?: number
  decision_stance?: string
  decision_flow_default_zoom_pct?: number
  stream_pane_font_pt?: number
  chart_seq_label_font_pt?: number
  auto_resume_chart_after_analysis?: boolean
  keep_analysis?: boolean
  cancel_keep_analysis_on_retry?: boolean
  decision_confidence_threshold?: number
  enable_next_bar_prediction?: boolean
  structure_flip_cooldown_bars?: number
}

export interface FeishuSettingsView {
  enabled?: boolean
  webhook_url_masked?: string
  webhook_url_set?: boolean
  secret_masked?: string
  secret_set?: boolean
  app_secret_masked?: string
  app_secret_set?: boolean
  app_id?: string
  notify_on_order_only?: boolean
}

export interface TushareSettingsView {
  token_masked?: string
  token_set?: boolean
}

export interface PushplusSettingsView {
  enabled?: boolean
  token_masked?: string
  token_set?: boolean
}

export interface SchedulerSettingsView {
  enabled?: boolean
  market_sync_cron?: string
  news_sync_cron?: string
  timezone?: string
}

export interface SettingsView {
  version: number
  provider: ProviderSettingsView
  general: GeneralSettingsView
  feishu: FeishuSettingsView
  tushare: TushareSettingsView
  pushplus: PushplusSettingsView
  scheduler: SchedulerSettingsView
}

export interface ProviderSettingsPatch {
  api_key?: string | null
  model?: string | null
  base_url?: string | null
  thinking?: boolean | null
  reasoning_effort?: ReasoningEffort | null
  context_window?: number | null
  search_model?: string | null
  search_enabled?: boolean | null
  [key: string]: any
}

export interface GeneralSettingsPatch {
  analysis_bar_count?: number | null
  refresh_interval_ms?: number | null
  context_warning_threshold_pct?: number | null
  last_data_source?: string | null
  kline_adjust?: KlineAdjust | null
  last_tradingview_exchange?: string | null
  last_symbol?: string | null
  last_timeframe?: string | null
  decision_flow_auto_play?: boolean | null
  decision_flow_play_seconds?: number | null
  alert_on_order_opportunity?: boolean | null
  incremental_max_new_bars?: number | null
  decision_stance?: string | null
  decision_flow_default_zoom_pct?: number | null
  stream_pane_font_pt?: number | null
  chart_seq_label_font_pt?: number | null
  auto_resume_chart_after_analysis?: boolean | null
  keep_analysis?: boolean | null
  cancel_keep_analysis_on_retry?: boolean | null
  decision_confidence_threshold?: number | null
  enable_next_bar_prediction?: boolean | null
  structure_flip_cooldown_bars?: number | null
  [key: string]: any
}

export interface FeishuSettingsPatch {
  enabled?: boolean | null
  webhook_url?: string | null
  secret?: string | null
  app_id?: string | null
  app_secret?: string | null
  notify_on_order_only?: boolean | null
}

export interface TushareSettingsPatch {
  token?: string | null
}

export interface PushplusSettingsPatch {
  enabled?: boolean | null
  token?: string | null
}

export interface SchedulerSettingsPatch {
  enabled?: boolean | null
  market_sync_cron?: string | null
  news_sync_cron?: string | null
  timezone?: string | null
  [key: string]: any
}

export interface SettingsPatch {
  provider?: ProviderSettingsPatch
  general?: GeneralSettingsPatch
  feishu?: FeishuSettingsPatch
  tushare?: TushareSettingsPatch
  pushplus?: PushplusSettingsPatch
  scheduler?: SchedulerSettingsPatch
}

export interface TokenUsage {
  total_tokens?: number | null
  prompt_tokens?: number | null
  completion_tokens?: number | null
}

export interface ValidateLlmResult {
  ok: boolean
  latency_ms: number
  provider: string
  model: string
  usage: TokenUsage
  message: string
  raw?: Record<string, any> | null
}

export interface NotificationTestParams {
  webhook_url?: string
  secret?: string
  token?: string
}

export interface TestNotificationResult {
  ok: boolean
  latency_ms: number
  type: 'feishu' | 'pushplus'
  message: string
}
