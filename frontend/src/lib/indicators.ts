import type { Time } from 'lightweight-charts'

/**
 * 技术指标前端计算库（spec R2.4，KDJ/BOLL/BIAS 前端自算；MACD 一并自算）。
 *
 * 输入统一为 chart-ready 的 OHLC 序列（time 为 lightweight-charts Time 类型），
 * 输出点与输入按 time 对齐，便于直接 setData 到图表 series。
 */

export interface OHLCBar {
  time: Time
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface ValuePoint {
  time: Time
  value: number
}

export interface MACDPoint {
  time: Time
  dif: number
  dea: number
  hist: number
}

export interface KDJPoint {
  time: Time
  k: number
  d: number
  j: number
}

export interface BOLLPoint {
  time: Time
  mid: number
  upper: number
  lower: number
}

/** 简单移动平均（SMA） */
export function calcMA(ohlc: OHLCBar[], period: number): ValuePoint[] {
  const result: ValuePoint[] = []
  let sum = 0
  for (let i = 0; i < ohlc.length; i++) {
    sum += ohlc[i].close
    if (i >= period) sum -= ohlc[i - period].close
    if (i >= period - 1) {
      result.push({ time: ohlc[i].time, value: Number((sum / period).toFixed(4)) })
    }
  }
  return result
}

/** 指数移动平均（EMA） */
function calcEMA(values: number[], period: number): number[] {
  if (values.length === 0) return []
  const k = 2 / (period + 1)
  const ema: number[] = [values[0]]
  for (let i = 1; i < values.length; i++) {
    ema.push(values[i] * k + ema[i - 1] * (1 - k))
  }
  return ema
}

/** MACD（12/26/9）：dif = EMA12 - EMA26，dea = EMA9(dif)，hist = (dif - dea) * 2 */
export function calcMACD(ohlc: OHLCBar[], fast = 12, slow = 26, signal = 9): MACDPoint[] {
  if (ohlc.length < slow + signal) return []
  const closes = ohlc.map((b) => b.close)
  const emaFast = calcEMA(closes, fast)
  const emaSlow = calcEMA(closes, slow)
  const dif = closes.map((_, i) => emaFast[i] - emaSlow[i])
  const dea = calcEMA(dif, signal)
  return ohlc.map((b, i) => ({
    time: b.time,
    dif: Number(dif[i].toFixed(4)),
    dea: Number(dea[i].toFixed(4)),
    hist: Number(((dif[i] - dea[i]) * 2).toFixed(4)),
  }))
}

/** KDJ（9,3,3）：RSV → K/D 平滑 → J */
export function calcKDJ(ohlc: OHLCBar[], n = 9): KDJPoint[] {
  if (ohlc.length < n) return []
  let k = 50
  let d = 50
  const result: KDJPoint[] = []
  for (let i = 0; i < ohlc.length; i++) {
    const start = Math.max(0, i - n + 1)
    let llv = Infinity
    let hhv = -Infinity
    for (let j = start; j <= i; j++) {
      if (ohlc[j].low < llv) llv = ohlc[j].low
      if (ohlc[j].high > hhv) hhv = ohlc[j].high
    }
    const rsv = hhv === llv ? 50 : ((ohlc[i].close - llv) / (hhv - llv)) * 100
    k = (2 / 3) * k + (1 / 3) * rsv
    d = (2 / 3) * d + (1 / 3) * k
    const j = 3 * k - 2 * d
    result.push({ time: ohlc[i].time, k: Number(k.toFixed(2)), d: Number(d.toFixed(2)), j: Number(j.toFixed(2)) })
  }
  return result
}

/** BOLL（20,2）：mid = SMA，upper/lower = mid ± 2σ */
export function calcBOLL(ohlc: OHLCBar[], period = 20, mult = 2): BOLLPoint[] {
  if (ohlc.length < period) return []
  const result: BOLLPoint[] = []
  let sum = 0
  let sumSq = 0
  for (let i = 0; i < ohlc.length; i++) {
    const c = ohlc[i].close
    sum += c
    sumSq += c * c
    if (i >= period) {
      const old = ohlc[i - period].close
      sum -= old
      sumSq -= old * old
    }
    if (i >= period - 1) {
      const mid = sum / period
      const variance = sumSq / period - mid * mid
      const std = Math.sqrt(Math.max(0, variance))
      result.push({
        time: ohlc[i].time,
        mid: Number(mid.toFixed(4)),
        upper: Number((mid + mult * std).toFixed(4)),
        lower: Number((mid - mult * std).toFixed(4)),
      })
    }
  }
  return result
}

/** BIAS（乖离率）：(close - MA(period)) / MA(period) * 100，多周期返回 */
export function calcBIAS(ohlc: OHLCBar[], periods: number[] = [6, 12, 24]): Record<number, ValuePoint[]> {
  const result: Record<number, ValuePoint[]> = {}
  for (const period of periods) {
    const ma = calcMA(ohlc, period)
    // 第 i 个 MA 点对应 ohlc[i + period - 1]（SMA 从第 period 根起）
    result[period] = ma.map((p, i) => {
      const bar = ohlc[i + period - 1]
      const maVal = p.value
      return {
        time: p.time,
        value: Number((((bar.close - maVal) / maVal) * 100).toFixed(4)),
      }
    })
  }
  return result
}
