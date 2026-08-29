import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'
import { Star } from 'lucide-react'

/** 自选股列表项（Java `/api/watchlist/list` 返回 camelCase） */
interface WatchlistItem {
  id: number
  symbol: string
  symbolName: string
  groupName: string
  sortOrder: number
  note?: string | null
  close: number | null
  changePct: number | null
  preClose: number | null
  tradeDate: string | null
}

interface WatchlistPanelProps {
  /** 选中股票代码（受控） */
  selectedSymbol?: string | null
  /** 点击某只自选股时回调 */
  onSelect?: (symbol: string) => void
}

/** 操盘模式侧栏自选股面板：只读列表 + 选中高亮，增删交互后续设计 */
export function WatchlistPanel({ selectedSymbol, onSelect }: WatchlistPanelProps) {
  const [items, setItems] = useState<WatchlistItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  // 内部选中态（未受控时自管理；外部传入 selectedSymbol 时优先使用外部值）
  const [internalSelected, setInternalSelected] = useState<string | null>(null)
  const activeSymbol = selectedSymbol ?? internalSelected

  useEffect(() => {
    let cancelled = false
    fetch('/api/watchlist/list')
      .then((r) => r.json())
      .then((res: { code: number; data?: WatchlistItem[] }) => {
        if (cancelled) return
        if (res.code === 0) setItems(res.data ?? [])
        else setError(true)
      })
      .catch(() => {
        if (!cancelled) setError(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* 面板标题 */}
      <div className="flex shrink-0 items-center gap-1.5 px-3 pb-1.5 pt-1">
        <Star className="h-3.5 w-3.5 text-[var(--color-text-tertiary)]" />
        <span className="text-sm font-medium text-[var(--color-text-primary)]">自选股</span>
        {!loading && !error && items.length > 0 && (
          <span className="ml-auto text-sm text-[var(--color-text-tertiary)]">{items.length}</span>
        )}
      </div>

      {/* 列表区 */}
      <div className="flex-1 overflow-y-auto scrollbar-hide px-2 pb-2">
        {loading ? (
          <div className="flex h-full items-center justify-center text-sm text-[var(--color-text-tertiary)]">
            加载中…
          </div>
        ) : error ? (
          <div className="flex h-full items-center justify-center text-sm text-[var(--color-text-tertiary)]">
            自选股加载失败
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center justify-center px-4 py-10 text-center">
            <Star className="mb-2 h-5 w-5 text-[var(--color-text-placeholder)]" />
            <p className="text-sm text-[var(--color-text-primary)]">暂无自选股</p>
            <p className="mt-1 text-sm text-[var(--color-text-tertiary)]">后续支持添加自选股票</p>
          </div>
        ) : (
          <div className="flex flex-col gap-0.5">
            {items.map((item) => {
              const active = activeSymbol != null && activeSymbol === item.symbol
              const isUp = item.changePct != null && item.changePct > 0
              const isDown = item.changePct != null && item.changePct < 0
              const changeColor = isUp
                ? 'text-[var(--color-up)]'
                : isDown
                  ? 'text-[var(--color-down)]'
                  : 'text-[var(--color-text-secondary)]'
              return (
                <button
                  key={item.id}
                  onClick={() => {
                    setInternalSelected(item.symbol)
                    onSelect?.(item.symbol)
                  }}
                  className={cn(
                    'flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left transition-colors',
                    active
                      ? 'bg-[var(--color-bg-sidebar-active)]'
                      : 'hover:bg-[var(--color-bg-sidebar-hover)]',
                  )}
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-[var(--color-text-primary)]">
                      {item.symbolName || item.symbol}
                    </p>
                    <p className="truncate text-sm text-[var(--color-text-tertiary)]">
                      {item.symbol}
                    </p>
                  </div>
                  <div className="ml-2 shrink-0 text-right">
                    <p className="text-sm font-medium text-[var(--color-text-primary)] tabular-nums">
                      {item.close != null ? item.close.toFixed(2) : '--'}
                    </p>
                    <p className={cn('text-sm tabular-nums', changeColor)}>
                      {item.changePct != null
                        ? `${item.changePct > 0 ? '+' : ''}${item.changePct.toFixed(2)}%`
                        : '--'}
                    </p>
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
