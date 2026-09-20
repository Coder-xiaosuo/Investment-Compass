import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from 'react'
import { EMPTY_STREAM_DISPLAY, conversationStreamStore } from '@/lib/conversationStreamStore'
import type { StreamDisplay } from '@/types'

/**
 * 订阅指定会话的流式展示状态。
 *
 * 状态存放在模块级 conversationStreamStore（React 组件树之外）：
 * - 组件卸载 / 切换会话都不会中止流；
 * - 切回该会话时直接读取已累积的流式结果与中断状态；
 * - 命令式操作（start / resume / cancel / discard / clear）统一走 conversationStreamStore。
 */
export function useConversationStream(conversationId: string | null): StreamDisplay {
  const subscribe = useCallback(
    (onStoreChange: () => void) =>
      conversationId
        ? conversationStreamStore.subscribe(conversationId, onStoreChange)
        : () => {},
    [conversationId],
  )

  const getSnapshot = useCallback(
    () =>
      conversationId
        ? conversationStreamStore.getSnapshot(conversationId)
        : EMPTY_STREAM_DISPLAY,
    [conversationId],
  )

  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot)
}

/** 业务事件静默超过该时长 → 提示"仍在分析"（不判定连接已断开） */
export const STREAM_IDLE_HINT_MS = 30_000

/** 等待时长提示的刷新间隔 */
const META_POLL_MS = 1000

/**
 * 订阅某会话的流式时序元信息（已等待时长 / 静默时长）。
 *
 * 时间戳刻意不放进 StreamDisplay 快照（否则每个 token 都会触发 commit 与全树重渲染），
 * 改由消费组件按秒轮询读取；仅在 active 时轮询，流结束自动停止。
 * 请在独立的小组件中使用，避免每秒重渲染波及父组件。
 */
export function useStreamMeta(
  conversationId: string | null,
  active: boolean,
): { elapsedMs: number; idleMs: number } | null {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (!active || !conversationId) return
    const timer = setInterval(() => setNow(Date.now()), META_POLL_MS)
    return () => clearInterval(timer)
  }, [active, conversationId])

  return useMemo(() => {
    if (!active || !conversationId) return null
    const meta = conversationStreamStore.getStreamMeta(conversationId)
    if (!meta) return null
    return { elapsedMs: now - meta.startedAt, idleMs: now - meta.lastEventAt }
  }, [active, conversationId, now])
}
