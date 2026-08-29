import { useState, useEffect, useCallback, useRef } from 'react'
import { Search, Loader2, RefreshCw } from 'lucide-react'
import { useKlineApi } from '@/hooks/useKlineApi'
import { KlineChart } from '@/components/kline/KlineChart'
import type { KlineBar } from '@/types/kline'

type SyncState = 'idle' | 'loading' | 'empty' | 'syncing' | 'error'

export function TradingView() {
  const { fetchKlineHistory, triggerSync } = useKlineApi()
  const [symbol, setSymbol] = useState('')
  const [activeSymbol, setActiveSymbol] = useState('600519')
  const [data, setData] = useState<KlineBar[]>([])
  const [syncState, setSyncState] = useState<SyncState>('loading')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [timeframe, setTimeframe] = useState('1d')
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const TIMEFRAMES = [
    { label: '日线', value: '1d' },
    { label: '周线', value: '1w' },
    { label: '月线', value: '1M' },
  ]

  const loadData = useCallback(async (sym: string, tf?: string) => {
    setSyncState('loading')
    setErrorMsg(null)
    try {
      const bars = await fetchKlineHistory(sym, tf || timeframe, 200)
      if (bars.length === 0) {
        // 空数据 → 触发后台同步
        setSyncState('empty')
        setData([])
      } else {
        setSyncState('idle')
        setData(bars)
      }
    } catch (err) {
      setSyncState('error')
      setErrorMsg(err instanceof Error ? err.message : '获取数据失败')
      setData([])
    }
  }, [fetchKlineHistory, timeframe])

  // 空数据时自动触发同步并重试
  useEffect(() => {
    if (syncState !== 'empty') return
    if (!activeSymbol) return

    setSyncState('syncing')
    setErrorMsg(null)

    // 清理旧的定时器
    if (retryTimerRef.current) {
      clearTimeout(retryTimerRef.current)
    }

    // 触发后台同步
    triggerSync(activeSymbol).catch(() => {
      // triggerSync 失败不影响重试
    })

    // 8 秒后自动重试
    retryTimerRef.current = setTimeout(() => {
      loadData(activeSymbol, timeframe)
    }, 8000)

    return () => {
      if (retryTimerRef.current) {
        clearTimeout(retryTimerRef.current)
      }
    }
  }, [syncState, activeSymbol, timeframe, triggerSync, loadData])

  // 初始加载
  useEffect(() => {
    loadData(activeSymbol, timeframe)
    return () => {
      if (retryTimerRef.current) {
        clearTimeout(retryTimerRef.current)
      }
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleSearch = () => {
    const sym = symbol.trim().replace(/\D/g, '')
    if (sym && sym.length >= 6) {
      setActiveSymbol(sym)
      loadData(sym, timeframe)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSearch()
  }

  return (
    <div className="flex flex-col flex-1 bg-[var(--color-bg-surface)] min-w-0">
      {/* 顶部信息栏 */}
      <div className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-2">
        <div className="flex items-center gap-3">
          {/* 股票搜索 */}
          <div className="flex items-center gap-1.5 rounded-lg border border-[var(--color-border-light)] bg-[var(--color-bg-base)] px-2 py-1 focus-within:border-[var(--color-info)] transition-colors">
            <Search className="h-3.5 w-3.5 text-[var(--color-text-tertiary)] shrink-0" />
            <input
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入股票代码"
              className="w-[100px] bg-transparent text-xs text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-placeholder)]"
            />
            <button
              onClick={handleSearch}
              disabled={syncState === 'loading' || syncState === 'syncing'}
              className="rounded px-1.5 py-0.5 text-xs text-[var(--color-info)] hover:bg-[var(--color-accent-soft)] transition-colors"
            >
              查询
            </button>
          </div>

          {/* 周期选择器 */}
          <div className="flex items-center gap-0.5 border-l border-[var(--color-border-light)] ml-3 pl-3">
            {TIMEFRAMES.map(tf => (
              <button
                key={tf.value}
                onClick={() => {
                  setTimeframe(tf.value)
                  loadData(activeSymbol, tf.value)
                }}
                className={`rounded px-2 py-0.5 text-xs font-medium transition-colors ${
                  timeframe === tf.value
                    ? 'bg-[var(--color-accent)] text-white'
                    : 'text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-bg-hover)]'
                }`}
              >
                {tf.label}
              </button>
            ))}
          </div>

          {/* 当前股票 */}
          {activeSymbol && (
            <div className="flex items-center gap-2">
              <span className="text-base font-medium text-[var(--color-text-primary)]">
                {activeSymbol}
              </span>
              <span className="text-xs text-[var(--color-text-tertiary)]">
                {TIMEFRAMES.find(tf => tf.value === timeframe)?.label}
              </span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-3 text-xs text-[var(--color-text-tertiary)]">
          <span>MA5</span>
          <span>MA10</span>
          <span>MA20</span>
        </div>
      </div>

      {/* K线图区域 */}
      <div className="flex flex-1 min-h-0">
        {syncState === 'loading' && (
          <div className="flex flex-1 items-center justify-center">
            <div className="flex flex-col items-center gap-2">
              <Loader2 className="h-5 w-5 animate-spin text-[var(--color-text-tertiary)]" />
              <span className="text-xs text-[var(--color-text-tertiary)]">加载中...</span>
            </div>
          </div>
        )}

        {syncState === 'syncing' && (
          <div className="flex flex-1 flex-col items-center justify-center gap-3">
            <Loader2 className="h-5 w-5 animate-spin text-[var(--color-info)]" />
            <div className="text-center">
              <p className="text-xs font-medium text-[var(--color-text-primary)]">
                正在获取K线数据
              </p>
              <p className="mt-1 text-xs text-[var(--color-text-tertiary)]">
                后台同步已启动，8秒后自动重试
              </p>
            </div>
          </div>
        )}

        {syncState === 'error' && (
          <div className="flex flex-1 flex-col items-center justify-center gap-2">
            <p className="text-xs text-[var(--color-text-tertiary)]">{errorMsg}</p>
            <button
              onClick={() => loadData(activeSymbol, timeframe)}
              className="flex items-center gap-1 rounded-md bg-[var(--color-accent)] px-3 py-1 text-xs text-white hover:bg-[var(--color-accent-hover)] transition-colors"
            >
              <RefreshCw className="h-3 w-3" />
              重试
            </button>
          </div>
        )}

        {syncState === 'empty' && (
          <div className="flex flex-1 flex-col items-center justify-center gap-2">
            <p className="text-xs text-[var(--color-text-tertiary)]">
              该股票暂无K线数据
            </p>
            <button
              onClick={() => loadData(activeSymbol, timeframe)}
              className="flex items-center gap-1 rounded-md bg-[var(--color-accent)] px-3 py-1 text-xs text-white hover:bg-[var(--color-accent-hover)] transition-colors"
            >
              <RefreshCw className="h-3 w-3" />
              重试
            </button>
          </div>
        )}

        {syncState === 'idle' && data.length > 0 && (
          <KlineChart data={data} />
        )}
      </div>
    </div>
  )
}
