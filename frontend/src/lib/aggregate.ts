import type { KlineBar } from '@/types/kline'

/**
 * 日线聚合为周线 / 月线（spec R2.3）。
 *
 * Java `/api/stock/kline` 仅提供 1m/5m/.../1d，周/月由日线在前端聚合：
 * open=首日开、close=末日收、high=max、low=min、volume/amount=求和、pct_chg=末日涨跌。
 */

/** 将 'YYYY-MM-DD' 归到所在周的周一日期（A股以周一为一周起始） */
function weekStart(dateStr: string): string {
  const [y, m, d] = dateStr.split('-').map(Number)
  const date = new Date(y, m - 1, d)
  const day = date.getDay() // 0=周日
  const diff = day === 0 ? -6 : 1 - day // 周日回退到上周一
  date.setDate(date.getDate() + diff)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

/** 将 'YYYY-MM-DD' 归到所在月份 'YYYY-MM' */
function monthKey(dateStr: string): string {
  return dateStr.slice(0, 7)
}

function aggregate(bars: KlineBar[], keyOf: (date: string) => string, timeframe: string): KlineBar[] {
  const groups = new Map<string, KlineBar[]>()
  for (const bar of bars) {
    const key = keyOf(bar.trade_date)
    const list = groups.get(key)
    if (list) list.push(bar)
    else groups.set(key, [bar])
  }
  const result: KlineBar[] = []
  for (const group of groups.values()) {
    const last = group[group.length - 1]
    result.push({
      symbol: last.symbol,
      trade_date: last.trade_date,
      timeframe,
      ts_open: last.ts_open,
      open: group[0].open,
      high: Math.max(...group.map((b) => b.high)),
      low: Math.min(...group.map((b) => b.low)),
      close: last.close,
      volume: group.reduce((s, b) => s + b.volume, 0),
      amount: group.reduce((s, b) => s + b.amount, 0),
      pct_chg: last.pct_chg,
      closed: last.closed,
      volume_ratio: null,
      turnover_rate: null,
    })
  }
  return result.sort((a, b) => (a.trade_date < b.trade_date ? -1 : 1))
}

/** 日线 → 周线（按周一至周日分组） */
export function aggregateToWeekly(dailyBars: KlineBar[]): KlineBar[] {
  return aggregate(dailyBars, weekStart, '1w')
}

/** 日线 → 月线（按自然月分组） */
export function aggregateToMonthly(dailyBars: KlineBar[]): KlineBar[] {
  return aggregate(dailyBars, monthKey, '1M')
}
