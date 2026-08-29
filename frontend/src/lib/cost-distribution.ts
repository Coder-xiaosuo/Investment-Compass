import type { KlineBar } from '@/types/kline'

/**
 * 成交密集区替代算法（DEMO，spec R4）。
 *
 * 近 60 日 K 线 → 以当前价 2.5% 为一档 → 每档筹码量=落档 K 线成交量加权 →
 * 获利盘%（现价以下档位筹码占比）/ 套牢盘% / 平均成本（量价加权）/ 主力成本线。
 * 说明：真实筹码分布需逐笔/龙虎榜数据，此处为演示级近似。
 */

export interface CostBucket {
  /** 档位中心价 */
  center: number
  /** 档位累计成交量 */
  volume: number
  /** 档位筹码占比（%） */
  ratio: number
}

export interface CostDistribution {
  profitRatio: number
  trappedRatio: number
  /** 平均成本 = 近 60 日量价加权均价 */
  avgCost: number
  /** 主力持仓成本线（DEMO：同量价加权均价） */
  mainCost: number
  buckets: CostBucket[]
}

const WINDOW = 60
const BUCKET_PCT = 0.025

export function calcCostDistribution(bars: KlineBar[], currentPrice: number): CostDistribution {
  const recent = bars.slice(-WINDOW)
  const empty: CostDistribution = { profitRatio: 0, trappedRatio: 0, avgCost: 0, mainCost: 0, buckets: [] }
  if (recent.length === 0 || !currentPrice || currentPrice <= 0) return empty

  const step = Math.max(currentPrice * BUCKET_PCT, 0.01)
  const minP = Math.min(...recent.map((b) => b.low))
  const maxP = Math.max(...recent.map((b) => b.high))

  // 档位中心：以现价为中心，按 step 向上下扩展覆盖全部价格区间
  const centers: number[] = []
  for (let p = currentPrice; p >= minP; p -= step) centers.push(p)
  for (let p = currentPrice + step; p <= maxP; p += step) centers.push(p)
  centers.sort((a, b) => a - b)
  if (centers.length === 0) return empty

  // 每根 K 线按收盘价就近落档，成交量累计
  const volumeByCenter = new Map<number, number>()
  let totalVolume = 0
  let weightedSum = 0
  for (const b of recent) {
    const close = b.close
    totalVolume += b.volume
    weightedSum += close * b.volume
    let nearest = centers[0]
    let minDist = Infinity
    for (const c of centers) {
      const d = Math.abs(close - c)
      if (d < minDist) {
        minDist = d
        nearest = c
      }
    }
    volumeByCenter.set(nearest, (volumeByCenter.get(nearest) ?? 0) + b.volume)
  }

  // 获利盘：档位中心 ≤ 现价的筹码
  let profitVolume = 0
  for (const c of centers) {
    if (c <= currentPrice) profitVolume += volumeByCenter.get(c) ?? 0
  }

  const profitRatio = totalVolume > 0 ? (profitVolume / totalVolume) * 100 : 0
  const avgCost = totalVolume > 0 ? weightedSum / totalVolume : 0
  const buckets: CostBucket[] = centers.map((c) => ({
    center: Number(c.toFixed(2)),
    volume: volumeByCenter.get(c) ?? 0,
    ratio: totalVolume > 0 ? ((volumeByCenter.get(c) ?? 0) / totalVolume) * 100 : 0,
  }))

  return {
    profitRatio: Number(profitRatio.toFixed(2)),
    trappedRatio: Number((100 - profitRatio).toFixed(2)),
    avgCost: Number(avgCost.toFixed(2)),
    mainCost: Number(avgCost.toFixed(2)),
    buckets,
  }
}
