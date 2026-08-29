import { useEffect, useRef, useState } from 'react'

/**
 * 节流值：流式内容频繁更新时，将渲染频率限制为最多每 intervalMs 一次，
 * 避免 Markdown 全量解析在高频 chunk 下造成性能问题与中间态闪烁。
 */
export function useThrottledValue<T>(value: T, intervalMs = 120): T {
  const [throttled, setThrottled] = useState<T>(value)
  const lastUpdateRef = useRef(0)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    const now = Date.now()
    const elapsed = now - lastUpdateRef.current

    if (elapsed >= intervalMs) {
      // 距上次刷新已超过间隔：立即更新
      lastUpdateRef.current = now
      setThrottled(value)
      return
    }

    // 间隔未到：安排一次尾随更新（保证最终值一定渲染）
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => {
      lastUpdateRef.current = Date.now()
      setThrottled(value)
    }, intervalMs - elapsed)

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [value, intervalMs])

  return throttled
}
