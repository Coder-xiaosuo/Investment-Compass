import type { AnalysisTraceCardData, SubagentCardState, SubagentStage } from '@/types'

/** 子 Agent 名称 → 中文标签 */
const SUBAGENT_LABELS: Record<string, string> = {
  value_assessment: '估值分析',
  technical_analysis: '技术分析',
  watchlist_manage: '自选股管理',
  advisory: '资讯分析',
  'general-purpose': '通用分析',
}

/** advisory 资讯子 Agent 阶段 → 行标签 */
const ADVISORY_STAGE_LABELS: Record<string, string> = {
  plan: '意图规划',
  retrieve: '信息检索',
  synthesize: '综合回答',
}

const DIRECTION_LABELS: Record<string, string> = {
  buy: '买入',
  sell: '卖出',
  neutral: '观望',
}

/** 阶段行状态 */
type StageRowState = 'done' | 'running' | 'waiting' | 'skipped' | 'hidden'

function StageRow({ label, state, extra }: { label: string; state: StageRowState; extra?: string }) {
  if (state === 'hidden') return null
  return (
    <div className="flex items-center gap-2 py-1 text-xs">
      {state === 'done' ? (
        <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-[var(--color-success)] text-xs text-white">
          ✓
        </span>
      ) : state === 'running' ? (
        <span className="h-4 w-4 shrink-0 rounded-full border-2 border-[var(--color-accent)] border-t-transparent animate-spin" />
      ) : (
        <span className="h-4 w-4 shrink-0 rounded-full bg-[var(--color-bg-subtle)]" />
      )}
      <span
        className={
          state === 'done'
            ? 'text-[var(--color-text-primary)]'
            : state === 'running'
              ? 'text-[var(--color-accent)]'
              : 'text-[var(--color-text-tertiary)]'
        }
      >
        {label}
      </span>
      {state === 'running' && <span className="text-xs text-[var(--color-text-tertiary)]">进行中…</span>}
      {extra && <span className="text-xs text-[var(--color-text-secondary)]">{extra}</span>}
    </div>
  )
}

/** 计算估值/技术两行的展示状态与附加信息 */
function buildRows(stages: SubagentStage[], completed: boolean): Array<{ key: string; label: string; state: StageRowState; extra?: string }> {
  // 无任何阶段事件（如自选股管理等无投资流程的子 Agent）→ 不渲染阶段时间线
  if (stages.length === 0) return []

  // advisory 资讯子 Agent：按事件顺序渲染 plan → retrieve → synthesize 子流程
  const advisoryStages = stages.filter((s) => s.stage === 'plan' || s.stage === 'retrieve' || s.stage === 'synthesize')
  if (advisoryStages.length > 0) {
    const order: SubagentStage['stage'][] = ['plan', 'retrieve', 'synthesize']
    const rows: Array<{ key: string; label: string; state: StageRowState; extra?: string }> = []
    for (const stage of order) {
      const rec = advisoryStages.find((s) => s.stage === stage)
      if (!rec) {
        // 后续阶段未开始：上一阶段完成前不猜测，全部完成后才补"等待"
        rows.push({ key: stage, label: ADVISORY_STAGE_LABELS[stage], state: 'hidden' })
        continue
      }
      let extra: string | undefined
      if (rec.stage === 'retrieve') {
        const parts: string[] = []
        if (rec.webSearch) {
          parts.push(
            rec.webSearch === 'started'
              ? '联网搜索中'
              : rec.webSearch === 'done'
                ? '联网搜索完成'
                : '联网搜索失败',
          )
        }
        if (rec.newsCount != null) parts.push(`资讯 ${rec.newsCount} 条`)
        if (rec.reportCount != null) parts.push(`研报 ${rec.reportCount} 篇`)
        if (parts.length > 0) extra = parts.join(' · ')
      } else if (rec.stage === 'synthesize') {
        if (rec.intent) extra = rec.intent
        if (rec.confidence != null) extra = (extra ? `${extra} · ` : '') + `置信度 ${Math.round(rec.confidence * 100)}%`
        if (rec.citations) extra = (extra ? `${extra} · ` : '') + `引用 ${rec.citations} 处`
      }
      rows.push({
        key: stage,
        label: ADVISORY_STAGE_LABELS[stage],
        state: rec.status === 'done' ? 'done' : 'running',
        extra,
      })
    }
    return rows
  }

  const valuation = [...stages].reverse().find((s) => s.stage === 'valuation')
  const technical = [...stages].reverse().find((s) => s.stage === 'technical')

  const rows: Array<{ key: string; label: string; state: StageRowState; extra?: string }> = []

  // 估值评估行：仅当该子 Agent 确实产出过 valuation 阶段事件时才渲染，
  // 避免技术分析等子 Agent 卡片误显示"估值评估 进行中"
  if (valuation) {
    rows.push(
      valuation.status === 'done'
        ? {
            key: 'valuation',
            label: '估值评估',
            state: 'done',
            extra: valuation.score != null ? `得分 ${valuation.score}` : undefined,
          }
        : { key: 'valuation', label: '估值评估', state: 'running' },
    )
  }

  // 技术分析行
  if (technical) {
    if (technical.status === 'done') {
      rows.push({
        key: 'technical',
        label: '技术分析',
        state: 'done',
        extra: technical.direction ? `方向 ${DIRECTION_LABELS[technical.direction] ?? technical.direction}` : undefined,
      })
    } else if (technical.status === 'started') {
      rows.push({ key: 'technical', label: '技术分析', state: 'running' })
    }
  } else if (valuation?.status === 'done') {
    // 估值已出结果，技术分析尚未开始：按分数判断等待或跳过
    const score = valuation.score
    const skip = completed || (score != null && score < 60)
    rows.push({
      key: 'technical',
      label: '技术分析',
      state: skip ? 'skipped' : 'waiting',
      extra: skip ? '估值不足，跳过' : undefined,
    })
  }
  // 估值未出结果时不显示技术分析行，避免猜测

  return rows
}

interface SubagentCardProps {
  /** 实时流模式（由 SSE 事件驱动） */
  state?: SubagentCardState
  /** 历史回放模式（读后端落库的 card_data） */
  history?: AnalysisTraceCardData
}

export function SubagentCard({ state, history }: SubagentCardProps) {
  const cardStatus = state?.status ?? 'completed'
  const name = state?.name ?? ''
  const label = name ? SUBAGENT_LABELS[name] ?? name : '子 Agent'
  const stockCode = state?.stockCode ?? history?.symbol ?? ''
  const stockName = state?.stockName ?? history?.stock_name ?? ''
  const stages = state?.stages ?? (history?.analysis_trace ?? [])

  const rows = buildRows(stages, cardStatus === 'completed')

  const badge =
    cardStatus === 'running' ? (
      <span className="flex items-center gap-1 rounded-full bg-[var(--color-accent-soft)] px-2 py-0.5 text-xs font-medium text-[var(--color-accent)]">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--color-accent)]" />
        分析中
      </span>
    ) : cardStatus === 'interrupted' ? (
      <span className="rounded-full bg-[var(--color-warning)]/10 px-2 py-0.5 text-xs font-medium text-[var(--color-warning)]">
        已中断
      </span>
    ) : (
      <span className="rounded-full bg-[var(--color-success)]/10 px-2 py-0.5 text-xs font-medium text-[var(--color-success)]">
        完成
      </span>
    )

  return (
    <div className="mb-4 ml-9 max-w-[80%] rounded-2xl border border-[var(--color-border-light)] bg-[var(--color-bg-surface)] px-4 py-3">
      {/* Header */}
      <div className="mb-1 flex items-center justify-between">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-[var(--color-accent-soft)] text-xs">
            🤖
          </span>
          <span className="truncate text-xs font-medium text-[var(--color-text-primary)]">{label}</span>
          {stockCode && (
            <span className="shrink-0 rounded bg-[var(--color-bg-subtle)] px-1.5 py-0.5 font-mono text-xs text-[var(--color-text-tertiary)]">
              {stockCode}
            </span>
          )}
          {stockName && stockName !== stockCode && (
            <span className="shrink-0 truncate text-xs text-[var(--color-text-tertiary)]">{stockName}</span>
          )}
        </div>
        {badge}
      </div>

      {/* 阶段时间线 */}
      {rows.length > 0 && (
        <div className="border-t border-[var(--color-border-light)] pt-1.5">
          {rows.map((row) => (
            <StageRow key={row.key} label={row.label} state={row.state} extra={row.extra} />
          ))}
        </div>
      )}
    </div>
  )
}
