import { useCallback } from 'react'
import axios from 'axios'

/**
 * 基本面数据源调用（财务摘要 / 财务报表 / 估值）。
 * 对应 Python 8002 `/api/financial/*`、`/api/valuation`。
 * 后端失败时返回 null，调用方回退到 mock 数据。
 */

/** 财务摘要（最新一期） */
export interface FinancialAbstract {
  symbol: string
  report_date: string
  report_type: string
  roe: number | null
  roa: number | null
  gross_margin: number | null
  net_margin: number | null
  operating_margin: number | null
  revenue: number | null          // 营业总收入（元）
  net_profit: number | null       // 归母净利润（元）
  cash_flow_op: number | null     // 经营现金流量净额（元）
  revenue_growth: number | null   // 营收增长率(%)
  profit_growth: number | null    // 利润增长率(%)
  debt_ratio: number | null       // 资产负债率(%)
  current_ratio: number | null
  quick_ratio: number | null
  eps: number | null
  bvps: number | null
  cfps: number | null
  cash_ratio: number | null       // 经营现金/净利润
  cost_ratio: number | null       // 期间费用率(%)
  total_equity: number | null
}

/** 财务报表（4期历史） */
export interface FinancialReport {
  symbol: string
  reports: FinancialAbstract[]  // 按 report_date DESC 排序
}

/** 估值数据 */
export interface ValuationData {
  symbol: string
  trade_date: string
  close_price: number | null
  pe_ttm: number | null
  pe_static: number | null
  pb: number | null
  ps_ttm: number | null
  market_cap: number | null         // 总市值（元）
  float_market_cap: number | null   // 流通市值（元）
  turnover_rate: number | null
  volume_ratio: number | null
  source: string
}

const api = axios.create({
  baseURL: '/api',
  timeout: 45000,
})

export function useFundamentalApi() {
  /** 最新一期财务摘要。后端失败 / error 字段时返回 null。 */
  const fetchFinancialAbstract = useCallback(async (symbol: string): Promise<FinancialAbstract | null> => {
    const res = await api.get<{ code: number; message: string; data: FinancialAbstract | null }>(
      '/financial/abstract',
      { params: { symbol } },
    )
    const data = res.data.data
    if (res.data.code !== 0 || !data || (data as { error?: unknown }).error) return null
    return data
  }, [])

  /** 最近 4 期财务报表。后端失败 / reports 为空时返回 null。 */
  const fetchFinancialReport = useCallback(async (symbol: string): Promise<FinancialReport | null> => {
    const res = await api.get<{ code: number; message: string; data: FinancialReport | null }>(
      '/financial/report',
      { params: { symbol } },
    )
    const data = res.data.data
    if (
      res.data.code !== 0 ||
      !data ||
      (data as { error?: unknown }).error ||
      !data.reports ||
      data.reports.length === 0
    ) {
      return null
    }
    return data
  }, [])

  /** 最新估值数据（PE/PB/PS/市值等）。后端失败 / 空对象时返回 null。 */
  const fetchValuation = useCallback(async (symbol: string): Promise<ValuationData | null> => {
    const res = await api.get<{ code: number; message: string; data: ValuationData | null }>(
      '/valuation',
      { params: { symbol } },
    )
    const data = res.data.data
    if (res.data.code !== 0 || !data || !data.symbol) return null
    return data
  }, [])

  return { fetchFinancialAbstract, fetchFinancialReport, fetchValuation }
}
