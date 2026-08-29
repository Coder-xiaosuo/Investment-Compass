import { useCallback } from 'react'
import axios from 'axios'

/**
 * 演示级数据源调用（spec R3/R5）。
 * 对应 Python 8002 `/api/demo/*`（DEMO：演示级数据，仅联调用）。
 */

/** 股东户数一期（/api/demo/shareholders rows 元素） */
export interface ShareholderRow {
  date: string
  count: number
  change: number
  change_pct: number
}

/** /api/demo/shareholders 响应 data */
export interface ShareholdersData {
  symbol: string
  rows: ShareholderRow[]
}

/** /api/demo/fundflow daily 模式每日行（东财，金额单位元） */
export interface FundFlowDailyRow {
  date: string
  main_net: number
  super_net: number
  large_net: number
  medium_net: number
  small_net: number
  main_net_pct: number
}

/** /api/demo/fundflow snapshot 模式数据（同花顺快照，字符串金额） */
export interface FundFlowSnapshot {
  name: string
  price: string
  change_pct: string
  turnover: string
  inflow: string
  outflow: string
  net: string
  amount: string
}

/** /api/demo/fundflow 响应 data */
export interface FundFlowData {
  symbol: string
  source: string
  mode: 'daily' | 'snapshot'
  /** daily 模式每日主力净流入 */
  daily?: FundFlowDailyRow[]
  /** daily 模式 3/5/10 日净流入汇总 */
  summary?: { '3d'?: number; '5d'?: number; '10d'?: number }
  snapshot?: FundFlowSnapshot
}

const api = axios.create({
  baseURL: '/api',
  // fundflow 需实时拉取外部数据源（东财→同花顺降级），实测可达 20s+，超时放宽
  timeout: 45000,
})

export function useDemoApi() {
  /** 股东户数历史（20 期）。后端失败时 data 为 {error, message}，返回 null。 */
  const fetchShareholders = useCallback(async (symbol: string): Promise<ShareholdersData | null> => {
    const res = await api.get<{ code: number; message: string; data: ShareholdersData & { error?: boolean; message?: string } | null }>(
      '/demo/shareholders',
      { params: { symbol } },
    )
    const data = res.data.data
    if (res.data.code !== 0 || !data || (data as { error?: boolean }).error) return null
    return data
  }, [])

  /** 大单资金流向（DEMO，Task 5 使用） */
  const fetchFundFlow = useCallback(async (symbol: string, days = 10): Promise<FundFlowData | null> => {
    const res = await api.get<{ code: number; message: string; data: FundFlowData & { error?: boolean; message?: string } | null }>(
      '/demo/fundflow',
      { params: { symbol, days } },
    )
    const data = res.data.data
    if (res.data.code !== 0 || !data || (data as { error?: boolean }).error) return null
    return data
  }, [])

  return { fetchShareholders, fetchFundFlow }
}
