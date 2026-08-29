import { useMemo } from 'react'
import type { RadarPoint } from '@/hooks/useStyleProfile'

interface RadarChartProps {
  points: RadarPoint[]
  size?: number
  className?: string
  /** 空网格模式：只渲染六边形/辐条/标签，不渲染数据多边形（用于未测试引导） */
  empty?: boolean
}

/** 六边形雷达图 SVG（投资画像）。score_0_100 归一化到半径，蓝系主题。
 *  字号/留白按 size 比例计算：卡片自适应放大时标签同步变大（显示字号 ≈ 0.05×显示像素）；
 *  viewBox 四周预留标签空间，防止左右文字被截断。 */
export function RadarChart({ points, size = 220, className, empty = false }: RadarChartProps) {
  const PAD = size * 0.29 // 标签留白（≈0.29×逻辑尺寸）
  const viewSize = size + PAD * 2
  const cx = viewSize / 2
  const cy = viewSize / 2
  const R = size * 0.34
  const n = points.length

  const { ringPaths, ringPolys, dataPoints } = useMemo(() => {
    const ringPaths: string[] = []
    const ringPolys: string[] = []
    const dataPoints: { x: number; y: number }[] = []

    // 背景网格：4 层等距环（0/33/66/100）
    for (let ring = 1; ring <= 4; ring++) {
      const rr = (R * ring) / 4
      let path = ''
      for (let i = 0; i <= n; i++) {
        const angle = Math.PI / 2 + (2 * Math.PI * i) / n
        const x = cx + rr * Math.cos(angle)
        const y = cy - rr * Math.sin(angle)
        path += `${i === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)} `
      }
      ringPaths.push(path + 'Z')
    }
    // 顶点连线（蜘蛛网辐条）
    for (let i = 0; i < n; i++) {
      const angle = Math.PI / 2 + (2 * Math.PI * i) / n
      const x = cx + R * Math.cos(angle)
      const y = cy - R * Math.sin(angle)
      ringPolys.push(`M${cx},${cy}L${x.toFixed(2)},${y.toFixed(2)}`)
    }
    // 数据多边形顶点（score_0_100 → 半径占比）
    for (let i = 0; i < n; i++) {
      const ratio = Math.max(4, Math.min(100, points[i]?.score_0_100 ?? 0)) / 100
      const angle = Math.PI / 2 + (2 * Math.PI * i) / n
      const x = cx + R * ratio * Math.cos(angle)
      const y = cy - R * ratio * Math.sin(angle)
      dataPoints.push({ x, y })
    }
    return { ringPaths, ringPolys, dataPoints }
  }, [points, n, cx, cy, R])

  const dataPolygon = dataPoints.map((p) => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(' ')

  return (
    <svg viewBox={`0 0 ${viewSize} ${viewSize}`} className={className} role="img" aria-label="投资风格六维雷达图" preserveAspectRatio="xMidYMid meet">
      {/* 背景填充区域（交替填充环带，增强层次感） */}
      {ringPaths.map((d, i) => {
        if (i % 2 === 1) return null
        return (
          <path
            key={`fill-${i}`}
            d={d}
            fill="rgba(59,130,246,0.04)"
            stroke="none"
          />
        )
      })}

      {/* 网格环线 */}
      {ringPaths.map((d, i) => (
        <path key={i} d={d} fill="none" stroke="#cbd5e1" strokeWidth={1} opacity={0.5} />
      ))}
      {/* 辐条 */}
      {ringPolys.map((d, i) => (
        <path key={`s-${i}`} d={d} fill="none" stroke="#cbd5e1" strokeWidth={0.8} opacity={0.35} />
      ))}

      {/* 数据多边形（空网格模式跳过） */}
      {!empty && (
        <>
          <polygon
            points={dataPolygon}
            fill="rgba(59,130,246,0.18)"
            stroke="var(--color-accent)"
            strokeWidth={2}
            strokeLinejoin="round"
          />
          {dataPoints.map((p, i) => (
            <circle key={i} cx={p.x} cy={p.y} r={2.5} fill="var(--color-accent)" />
          ))}
        </>
      )}

      {/* 顶点标签 */}
      {points.map((pt, i) => {
        const angle = Math.PI / 2 + (2 * Math.PI * i) / n
        const lr = R + size * 0.06
        const lx = cx + lr * Math.cos(angle)
        const ly = cy - lr * Math.sin(angle)
        const anchor =
          Math.abs(Math.cos(angle)) < 0.2 ? 'middle' : Math.cos(angle) > 0 ? 'start' : 'end'
        return (
          <text
            key={pt.dimension}
            x={lx}
            y={ly}
            textAnchor={anchor}
            dominantBaseline="middle"
            fontSize={size * 0.082}
            fontWeight={600}
            fill="#475569"
          >
            {pt.label}
          </text>
        )
      })}
    </svg>
  )
}
