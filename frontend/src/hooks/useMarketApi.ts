import { useCallback } from 'react'
import axios from 'axios'

/**
 * 市场概览看板数据 hook。
 * 对应 Python 8002 `/api/demo/market-overview`（DEMO：演示级数据，仅联调用）。
 */

/** 大盘指数行情 */
export interface IndexItem {
  code: string
  name: string
  price: number
  change: number
  changePct: number
  volume: number
  amount: number
}

/** 市场宽度 */
export interface BreadthData {
  total: number
  up: number
  down: number
  flat: number
  limitUp: number
  limitDown: number
}

/** 热点板块 */
export interface SectorItem {
  name: string
  changePct: number
  netFlow: number
}

/** 北向资金单日 */
export interface NorthDailyFlow {
  date: string
  netFlow: number
}

/** 北向资金 */
export interface NorthFlowData {
  todayNet: number
  todayBuy: number
  todaySell: number
  dailyFlow: NorthDailyFlow[]
}

/** 大盘成交额单日 */
export interface VolumeDaily {
  date: string
  amount: number
  volume: number
}

/** 大盘成交量/额 */
export interface VolumeData {
  todayAmount: number
  todayVolume: number
  amountChange: number
  daily: VolumeDaily[]
}

/** 市场概览聚合数据 */
export interface MarketOverviewData {
  indices: IndexItem[]
  breadth: BreadthData
  sectors: SectorItem[]
  northFlow: NorthFlowData
  volume: VolumeData
}

const api = axios.create({
  baseURL: '/api',
  timeout: 45000,
})

export function useMarketApi() {
  const fetchMarketOverview = useCallback(async (): Promise<MarketOverviewData | null> => {
    const res = await api.get<{ code: number; message: string; data: MarketOverviewData & { error?: boolean } | null }>(
      '/demo/market-overview',
    )
    const data = res.data.data
    if (res.data.code !== 0 || !data || (data as { error?: boolean }).error) return null
    return data
  }, [])

  return { fetchMarketOverview }
}
