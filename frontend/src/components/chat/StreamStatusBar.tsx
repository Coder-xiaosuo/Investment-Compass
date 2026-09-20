import { AlertCircle, Loader2 } from 'lucide-react'
import { STREAM_IDLE_HINT_MS, useStreamMeta } from '@/hooks/useChatStream'
import type { StreamOutcome } from '@/types'
import { cn } from '@/lib/utils'

/** 毫秒 → 简洁中文时长：45s / 3m15s */
function formatDuration(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  if (total < 60) return `${total}s`
  const minutes = Math.floor(total / 60)
  const seconds = total % 60
  return seconds === 0 ? `${minutes}m` : `${minutes}m${seconds}s`
}

/**
 * 流式等待提示条（消息流底部，仅生成中渲染）。
 *
 * 只做中立的进度提示，**不声称「连接已断开」**：后端无心跳时无法可靠区分
 * 「网络断了」与「子 Agent 取数较慢」，给出会误判的结论比不给更糟。
 * 每秒轮询时序元信息（不入展示快照），因此只有本组件按秒重渲染。
 */
export function StreamStatusBar({ conversationId }: { conversationId: string }) {
  const meta = useStreamMeta(conversationId, true)
  if (!meta) return null
  const longIdle = meta.idleMs >= STREAM_IDLE_HINT_MS

  return (
    <div className="mb-3 flex items-center gap-2 rounded-lg bg-[var(--color-bg-subtle)] px-3 py-1.5 text-xs text-[var(--color-text-tertiary)]">
      <Loader2 className="h-3 w-3 shrink-0 animate-spin text-[var(--color-accent)]" />
      <span className="tabular-nums">分析进行中 · 已等待 {formatDuration(meta.elapsedMs)}</span>
      {longIdle && <span>· 暂无新输出，分析可能较慢</span>}
    </div>
  )
}

/**
 * 流异常结束提示（aborted / failed，消息流底部）。
 *
 * 此时已产出的内容仍保留在会话中未被清空，因此文案需说明「内容可能不完整」，
 * 并引导用户重新发送。刻意不做自动重试：后端每次请求都会插入一条新的 user
 * 消息并重算标题，自动重发会产生重复数据。
 */
export function StreamOutcomeNotice({ outcome }: { outcome?: StreamOutcome | null }) {
  if (outcome !== 'aborted' && outcome !== 'failed') return null
  const aborted = outcome === 'aborted'

  return (
    <div
      className={cn(
        'mb-3 flex items-start gap-2 rounded-lg border px-3 py-2 text-xs leading-relaxed',
        aborted
          ? 'border-[var(--color-border)] bg-[var(--color-bg-subtle)] text-[var(--color-text-tertiary)]'
          : 'border-[var(--color-warning)]/30 bg-[var(--color-warning)]/5 text-[var(--color-warning)]',
      )}
    >
      {aborted ? (
        <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-[var(--color-text-tertiary)]" />
      ) : (
        <AlertCircle className="mt-px h-3.5 w-3.5 shrink-0" />
      )}
      <span>
        {aborted
          ? '已停止生成，以上为已产出的部分内容。'
          : '本轮未收到结束信号（可能网络中断），以上为已产出的部分内容。'}
        {' '}可重新发送该问题以获得完整回复。
      </span>
    </div>
  )
}
