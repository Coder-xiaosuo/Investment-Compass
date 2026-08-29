import { useMemo } from 'react'
import type { ChatMessage } from '@/types'
import { cn } from '@/lib/utils'

/** 上下文压缩触发阈值（与后端 SummarizationMiddleware trigger=54000 一致） */
export const MAX_CONTEXT_TOKENS = 54000

interface ContextUsageProps {
  messages: ChatMessage[]
  /** 会话累计 token 用量（后端 conversation.token_count，回退用） */
  conversationTokenCount?: number
  /** 当前上下文真实占用（后端 conversation.context_tokens = 最后一次模型调用 input_tokens；优先展示） */
  contextTokens?: number
}

/** 千位格式化：1234 → 1.2k */
function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

/**
 * 任务摘要页「上下文」模块：展示当前会话 token 用量。
 * 一条用量条展示「已用 / 最大」，并按占用百分比着色（>80% 转警示色）。
 *
 * 展示优先级：contextTokens（真实模型 input_tokens，对齐压缩阈值）
 *  > conversationTokenCount（累计估算） > messages 汇总估算。
 */
export function ContextUsage({ messages, conversationTokenCount, contextTokens }: ContextUsageProps) {
  const used = useMemo(() => {
    if (contextTokens != null && contextTokens > 0) return contextTokens
    if (conversationTokenCount != null && conversationTokenCount > 0) return conversationTokenCount
    return messages.reduce((sum, m) => sum + (m.tokenCount ?? 0), 0)
  }, [contextTokens, conversationTokenCount, messages])
  const pct = Math.min(100, (used / MAX_CONTEXT_TOKENS) * 100)

  return (
    <div className="flex min-h-0 flex-1 flex-col border-b border-[var(--color-border)]">
      {/* 标题 */}
      <div className="shrink-0 flex items-center justify-between px-4 py-2">
        <span className="text-xs font-medium text-[var(--color-text-primary)]">上下文</span>
        <span className="rounded bg-[var(--color-accent-soft)] px-1.5 py-0.5 text-xs text-[var(--color-accent)]">
          Token
        </span>
      </div>

      <div className="flex flex-1 flex-col justify-center px-4 pb-3">
        <div className="flex items-baseline justify-between">
          <span className="text-base font-semibold text-[var(--color-text-primary)]">
            {formatTokens(used)}
          </span>
          <span className="text-xs text-[var(--color-text-tertiary)]">
            最大 {formatTokens(MAX_CONTEXT_TOKENS)}
          </span>
        </div>
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-[var(--color-bg-hover)]">
          <div
            className={cn(
              'h-full rounded-full transition-all duration-300',
              pct > 80 ? 'bg-[var(--color-warning)]' : 'bg-[var(--color-accent)]',
            )}
            style={{ width: `${pct}%` }}
          />
        </div>
        <p className="mt-1 text-xs text-[var(--color-text-tertiary)]">已占用 {pct.toFixed(0)}%</p>
      </div>
    </div>
  )
}
