import { useState } from 'react'
import type { Decision, DecisionType, HITLRequest } from '@/types'

/** 允许的决策 → 按钮文案 */
const DECISION_BUTTON_LABELS: Record<DecisionType, string> = {
  approve: '进入技术面分析',
  reject: '跳过',
  respond: '输入指令',
}

interface HITLConfirmCardProps {
  /** 后端 interrupt 事件的 data（action_requests / review_configs） */
  data: HITLRequest
  /** 是否正在 resume 续流（按钮禁用、展示"分析中"） */
  isResuming?: boolean
  /** 用户做出决策后回调（resume） */
  onResume: (decisions: Decision[]) => void
}

/** HITL 估值确认卡片：展示估值结论并征求用户是否进入技术面分析。 */
export function HITLConfirmCard({ data, isResuming = false, onResume }: HITLConfirmCardProps) {
  const action = data.action_requests?.[0]
  const args = action?.args ?? {}
  const stockIdentifier = String(args.stock_identifier ?? '')
  const recommend = Boolean(args.recommend)
  const reason = String(args.reason ?? '')

  const config = data.review_configs?.[0]
  const allowed = config?.allowed_decisions ?? ['approve', 'reject']

  const [showRespondInput, setShowRespondInput] = useState(false)
  const [respondText, setRespondText] = useState('')

  const handleClick = (type: DecisionType) => {
    if (isResuming) return
    if (type === 'respond') {
      // respond 需要额外输入指令文本
      setShowRespondInput(true)
      return
    }
    onResume([{ type }])
  }

  const handleSubmitRespond = () => {
    const message = respondText.trim()
    if (!message) return
    onResume([{ type: 'respond', message }])
  }

  return (
    <div className="mb-4 max-w-[80%] rounded-2xl border border-[var(--color-accent)]/30 bg-[var(--color-bg-surface)] px-4 py-3">
      {/* Header */}
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-[var(--color-accent-soft)] text-xs">
            ✋
          </span>
          <span className="truncate text-xs font-medium text-[var(--color-text-primary)]">估值确认</span>
          {stockIdentifier && (
            <span className="shrink-0 rounded bg-[var(--color-bg-subtle)] px-1.5 py-0.5 font-mono text-xs text-[var(--color-text-tertiary)]">
              {stockIdentifier}
            </span>
          )}
        </div>
        {isResuming ? (
          <span className="flex shrink-0 items-center gap-1 rounded-full bg-[var(--color-accent-soft)] px-2 py-0.5 text-xs font-medium text-[var(--color-accent)]">
            <span className="h-3 w-3 rounded-full border-2 border-[var(--color-accent)] border-t-transparent animate-spin" />
            分析中
          </span>
        ) : (
          <span
            className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${
              recommend
                ? 'bg-[var(--color-success)]/10 text-[var(--color-success)]'
                : 'bg-[var(--color-warning)]/10 text-[var(--color-warning)]'
            }`}
          >
            {recommend ? '推荐进入技术面' : '不推荐进入技术面'}
          </span>
        )}
      </div>

      {/* 结论与理由 */}
      <p className="text-xs leading-relaxed text-[var(--color-text-secondary)]">
        {reason || (recommend ? '估值结果良好，建议继续技术面分析。' : '估值结果不佳，不建议继续技术面分析。')}
      </p>

      {/* 决策按钮组 */}
      {isResuming ? (
        <p className="mt-2 text-xs text-[var(--color-text-tertiary)]">正在根据你的选择继续分析…</p>
      ) : (
        <>
          <div className="mt-2.5 flex flex-wrap gap-2">
            {allowed.map((type) => (
              <button
                key={type}
                onClick={() => handleClick(type)}
                className="rounded-full border border-[var(--color-border-light)] bg-[var(--color-bg-subtle)] px-3 py-1 text-xs font-medium text-[var(--color-text-secondary)] transition-colors hover:border-[var(--color-accent)] hover:text-[var(--color-accent)]"
              >
                {DECISION_BUTTON_LABELS[type] ?? type}
              </button>
            ))}
          </div>

          {/* respond 文本输入 */}
          {showRespondInput && (
            <div className="mt-2 flex gap-2">
              <input
                value={respondText}
                onChange={(e) => setRespondText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSubmitRespond()
                }}
                placeholder="输入你的指令或补充信息…"
                autoFocus
                className="flex-1 min-w-0 rounded-lg border border-[var(--color-border-light)] bg-[var(--color-bg-base)] px-2.5 py-1.5 text-xs text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-placeholder)] focus:border-[var(--color-accent)]"
              />
              <button
                onClick={handleSubmitRespond}
                disabled={!respondText.trim()}
                className="shrink-0 rounded-lg bg-[var(--color-accent)] px-3 py-1.5 text-xs font-medium text-white disabled:opacity-40"
              >
                提交
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
