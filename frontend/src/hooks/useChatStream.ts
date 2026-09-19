import { useCallback, useSyncExternalStore } from 'react'
import { EMPTY_STREAM_DISPLAY, conversationStreamStore } from '@/lib/conversationStreamStore'
import type { StreamDisplay } from '@/types'

/**
 * 订阅指定会话的流式展示状态。
 *
 * 状态存放在模块级 conversationStreamStore（React 组件树之外）：
 * - 组件卸载 / 切换会话都不会中止流；
 * - 切回该会话时直接读取已累积的流式结果与中断状态；
 * - 命令式操作（start / resume / cancel / clear）统一走 conversationStreamStore。
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
