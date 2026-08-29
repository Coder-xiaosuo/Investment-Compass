/** 单根K线数据（后端API返回格式） */
export interface KlineBar {
  symbol: string
  trade_date: string
  timeframe: string
  ts_open: number
  open: number
  high: number
  low: number
  close: number
  volume: number
  amount: number
  pct_chg: number | null
  closed: number | null
  volume_ratio: number | null
  turnover_rate: number | null
}

/** K线历史API响应 */
export interface KlineHistoryResponse {
  code: number
  message: string
  data: {
    symbol: string
    timeframe: string
    bars: KlineBar[]
  } | null
}

/** Lightweight Charts 蜡烛图数据格式 */
export interface CandlestickData {
  time: string
  open: number
  high: number
  low: number
  close: number
}

/** Lightweight Charts 成交量数据格式 */
export interface VolumeData {
  time: string
  value: number
  color: string
}

/** Lightweight Charts 线型数据格式（MA等） */
export interface LineData {
  time: string
  value: number
}

/** 均线配置 */
export interface MAConfig {
  period: number
  color: string
  label: string
}

/** 实时行情快照（Java `/api/stock/quote`，返回 camelCase） */
export interface StockQuote {
  symbol: string
  tradeDate: string
  close: number
  changePct: number
  preClose: number
}

/** 个股详情聚合（Java `/api/stock/detail/{symbol}`，返回 camelCase） */
export interface StockDetail {
  symbol: string
  stockName: string
  industry: string
  listDate: string
  latestClose: number
  latestOpen: number
  latestHigh: number
  latestLow: number
  latestVolume: number
  latestAmount: number
  latestPctChg: number
  latestTradeDate: string
  change: number
  changePercent: number
}
