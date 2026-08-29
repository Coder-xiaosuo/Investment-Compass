import { useCallback } from 'react'
import axios from 'axios'
import type { KlineBar, StockDetail, StockQuote } from '@/types/kline'

/** Java 后端返回的 K 线条目（snake_case，与 @JsonNaming(SnakeCaseStrategy) 对齐） */
interface JavaKlineBar {
  trade_date: string
  ts_open: number
  open: number
  high: number
  low: number
  close: number
  volume: number
  amount: number
  pct_chg: number | null
}

/** Java 后端 K 线查询响应 */
interface JavaKlineResponse {
  code: number
  message: string
  data: {
    symbol: string
    timeframe: string
    bars: JavaKlineBar[]
  } | null
}

/** 将 Java 后端返回的 snake_case 格式映射为内部 KlineBar 格式 */
function mapJavaToKlineBar(
  bar: JavaKlineBar,
  symbol: string,
  timeframe: string,
): KlineBar {
  return {
    symbol,
    trade_date: bar.trade_date,
    timeframe,
    ts_open: bar.ts_open,
    open: bar.open,
    high: bar.high,
    low: bar.low,
    close: bar.close,
    volume: bar.volume,
    amount: bar.amount ?? 0,
    pct_chg: bar.pct_chg ?? null,
    closed: 1,
    volume_ratio: null,
    turnover_rate: null,
  }
}

const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

export function useKlineApi() {
  /** 函数引用稳定（useCallback），避免消费方 effect 死循环 */
  const fetchKlineHistory = useCallback(
    async (symbol: string, timeframe = '1d', limit = 200): Promise<KlineBar[]> => {
      const res = await api.get<JavaKlineResponse>('/stock/kline', {
        params: { symbol, timeframe, limit },
      })
      if (res.data.code !== 0 || !res.data.data) {
        throw new Error(res.data.message || '获取K线数据失败')
      }
      const { symbol: sym, timeframe: tf, bars } = res.data.data
      return bars.map((b) => mapJavaToKlineBar(b, sym, tf))
    },
    [],
  )

  /** 触发单只股票后台同步（查不到 K 线时调用）。 */
  const triggerSync = useCallback(async (symbol: string): Promise<void> => {
    await api.post('/fetch/sync', { symbol })
  }, [])

  /** 实时行情快照（spec R2.1 左栏价格面板数据源之一） */
  const fetchQuote = useCallback(async (symbol: string): Promise<StockQuote | null> => {
    const res = await api.get<{ code: number; message: string; data: StockQuote[] | null }>('/stock/quote', {
      params: { symbols: symbol },
    })
    if (res.data.code !== 0 || !res.data.data || res.data.data.length === 0) return null
    return res.data.data[0]
  }, [])

  /** 个股详情聚合（spec R2.1 左栏价格面板数据源之二） */
  const fetchDetail = useCallback(async (symbol: string): Promise<StockDetail | null> => {
    const res = await api.get<{ code: number; message: string; data: StockDetail | null }>(`/stock/detail/${symbol}`)
    if (res.data.code !== 0 || !res.data.data) return null
    return res.data.data
  }, [])

  return { fetchKlineHistory, triggerSync, fetchQuote, fetchDetail }
}
