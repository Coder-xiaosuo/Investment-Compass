import type { DecisionCardData, ReviewOutcome } from '@/types'

/** 从 card_data 中提取复盘信息（review_outcome，或直接挂载的复盘字段） */
function extractReview(data: DecisionCardData): ReviewOutcome | null {
  const result = data.result ?? {}
  const review = (data.review_outcome ?? result.review_outcome) as ReviewOutcome | undefined
  if (review && typeof review === 'object' && Object.keys(review).length > 0) {
    return review
  }
  // 复盘字段也可能直接挂在 result 或卡片顶层
  if (result.verdict != null || result.actual_trend != null || result.profit_ratio != null) {
    return result as ReviewOutcome
  }
  if (data.verdict != null || data.actual_trend != null || data.profit_ratio != null) {
    return data as ReviewOutcome
  }
  return null
}

/** 复盘命中状态标签（verdict: HIT / MISS） */
function getVerdictLabel(verdict?: string): string {
  const v = String(verdict ?? '').toUpperCase()
  if (v === 'HIT') return '✅ 命中'
  if (v === 'MISS') return '❌ 未命中'
  return verdict ? `⚠️ ${verdict}` : ''
}

/** 格式化实际涨跌：3.12 → +3.12%；字符串数字同处理；其余原样返回 */
function formatProfitRatio(ratio?: number | string): string {
  if (ratio == null || ratio === '') return ''
  if (typeof ratio === 'number') {
    return `${ratio > 0 ? '+' : ''}${ratio.toFixed(2)}%`
  }
  const s = String(ratio).trim()
  if (/^[-+]?\d+(\.\d+)?$/.test(s)) {
    const n = parseFloat(s)
    return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`
  }
  if (s.endsWith('%')) return s
  return s
}

/** 决策颜色映射 */
const DECISION_STYLE: Record<string, { bg: string; text: string; label: string }> = {
  强烈买入: { bg: 'bg-red-50 dark:bg-red-950/30', text: 'text-red-600 dark:text-red-400', label: '强烈买入' },
  买入: { bg: 'bg-red-50 dark:bg-red-950/30', text: 'text-red-600 dark:text-red-400', label: '买入' },
  等买点: { bg: 'bg-amber-50 dark:bg-amber-950/30', text: 'text-amber-600 dark:text-amber-400', label: '等待' },
  轻仓试水: { bg: 'bg-rose-50 dark:bg-rose-950/30', text: 'text-rose-600 dark:text-rose-400', label: '轻仓' },
  '减仓/警惕': { bg: 'bg-orange-50 dark:bg-orange-950/30', text: 'text-orange-600 dark:text-orange-400', label: '警惕' },
  不关注: { bg: 'bg-gray-50 dark:bg-gray-800/50', text: 'text-gray-500 dark:text-gray-400', label: '观望' },
  清仓: { bg: 'bg-green-50 dark:bg-green-950/30', text: 'text-green-600 dark:text-green-400', label: '清仓' },
  不建议追涨: { bg: 'bg-gray-50 dark:bg-gray-800/50', text: 'text-gray-500 dark:text-gray-400', label: '回避' },
}

function getDecisionStyle(decision: string) {
  return DECISION_STYLE[decision] || { bg: 'bg-gray-50 dark:bg-gray-800/50', text: 'text-gray-500', label: decision }
}

/** PA 方向标识 */
function getDirectionIcon(direction?: string) {
  switch (direction) {
    case 'buy':
      return '↑'
    case 'sell':
      return '↓'
    default:
      return '→'
  }
}

interface DecisionCardProps {
  data: DecisionCardData | null
}

export function DecisionCard({ data }: DecisionCardProps) {
  if (!data) {
    return (
      <div className="flex flex-col items-center justify-center flex-1 text-center px-4">
        <div className="rounded-full bg-[var(--color-bg-subtle)] p-3 mb-2">
          <svg className="h-5 w-5 text-[var(--color-text-tertiary)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456z" />
          </svg>
        </div>
        <p className="text-xs text-[var(--color-text-tertiary)]">
          选择股票后<br />AI 决策将在此显示
        </p>
      </div>
    )
  }

  const { stock_name, symbol, value_assessment, pa_analysis, fusion } = data
  const review = extractReview(data)
  // 无融合决策且无复盘数据时无内容可展示
  if (!fusion && !review) return null

  const ds = getDecisionStyle(fusion?.decision ?? '')
  const verdictLabel = getVerdictLabel(review?.verdict)
  const profitText = formatProfitRatio(review?.profit_ratio)

  const paCard = pa_analysis?.card_data
  const paDirection = paCard?.direction
  const paConfidence = paCard?.trade_confidence

  const score = value_assessment?.final_score
  const level = value_assessment?.final_level
  const isBlocked = value_assessment?.blocked

  return (
    <div className="flex flex-col gap-3 px-4 py-3">
      {/* Header: 股票名称 + 决策标签 */}
      <div className="flex items-center justify-between">
        <div className="min-w-0">
          <p className="text-base font-medium text-[var(--color-text-primary)] truncate">
            {stock_name || symbol}
          </p>
          {symbol && (
            <p className="text-xs font-mono text-[var(--color-text-tertiary)] mt-0.5">
              {symbol}
            </p>
          )}
        </div>
        <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold ${ds.bg} ${ds.text}`}>
          {ds.label}
        </span>
      </div>

      {/* 双指标：价值评分 + PA 分析 */}
      <div className="grid grid-cols-2 gap-2">
        {/* 价值评估 */}
        <div className="rounded-lg bg-[var(--color-bg-subtle)] p-2.5">
          <p className="text-xs font-medium text-[var(--color-text-tertiary)] mb-1.5 uppercase tracking-wider">
            价值评分
          </p>
          {isBlocked ? (
            <p className="text-xs text-[var(--color-text-tertiary)]">
              未通过门控
            </p>
          ) : score != null ? (
            <div className="flex items-baseline gap-1.5">
              <span className="text-xl font-bold text-[var(--color-text-primary)]">
                {score}
              </span>
              {level && (
                <span className="text-xs font-medium text-[var(--color-text-tertiary)]">
                  {level}
                </span>
              )}
            </div>
          ) : (
            <p className="text-xs text-[var(--color-text-tertiary)]">
              暂无数据
            </p>
          )}
          {value_assessment?.warnings && value_assessment.warnings.length > 0 && (
            <p className="mt-1 text-xs text-[var(--color-warning)] truncate">
              {value_assessment.warnings[0]}
            </p>
          )}
        </div>

        {/* PA 技术分析 */}
        <div className="rounded-lg bg-[var(--color-bg-subtle)] p-2.5">
          <p className="text-xs font-medium text-[var(--color-text-tertiary)] mb-1.5 uppercase tracking-wider">
            PA 技术面
          </p>
          {pa_analysis ? (
            <>
              <div className="flex items-baseline gap-1.5">
                {paDirection ? (
                  <span className={`text-xl font-bold ${
                    paDirection === 'buy' ? 'text-red-500' :
                    paDirection === 'sell' ? 'text-green-500' :
                    'text-[var(--color-text-secondary)]'
                  }`}>
                    {getDirectionIcon(paDirection)}
                  </span>
                ) : (
                  <span className="text-xl font-bold text-[var(--color-text-secondary)]">→</span>
                )}
                {paConfidence != null && (
                  <span className="text-xs font-medium text-[var(--color-text-tertiary)]">
                    {paConfidence}%
                  </span>
                )}
              </div>
              <p className="text-xs text-[var(--color-text-tertiary)] mt-0.5 capitalize">
                {paDirection === 'buy' ? '买入' :
                 paDirection === 'sell' ? '卖出' :
                 paDirection || '观望'}
              </p>
            </>
          ) : (
            <p className="text-xs text-[var(--color-text-tertiary)]">
              {isBlocked ? '未执行' : score != null && score < 40 ? '评分不足' : '等待分析'}
            </p>
          )}
        </div>
      </div>

      {fusion?.summary && (
        <p className="text-xs leading-relaxed text-[var(--color-text-secondary)] bg-[var(--color-bg-subtle)] rounded-lg p-2.5">
          {fusion.summary}
        </p>
      )}

      {/* 复盘状态（有复盘回填数据时展示） */}
      {review && (
        <div className="rounded-lg border border-[var(--color-border-light)] bg-[var(--color-bg-surface)] p-2.5">
          <p className="text-xs font-medium text-[var(--color-text-tertiary)] mb-1.5 uppercase tracking-wider">
            复盘状态
          </p>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            {verdictLabel && (
              <span
                className={`text-xs font-semibold ${
                  String(review.verdict ?? '').toUpperCase() === 'HIT'
                    ? 'text-[var(--color-success)]'
                    : String(review.verdict ?? '').toUpperCase() === 'MISS'
                      ? 'text-[var(--color-warning)]'
                      : 'text-[var(--color-text-secondary)]'
                }`}
              >
                {verdictLabel}
              </span>
            )}
            {profitText && (
              <span className="text-xs text-[var(--color-text-secondary)]">
                实际涨跌 {profitText}
              </span>
            )}
            {review.actual_trend && (
              <span className="text-xs text-[var(--color-text-tertiary)]">
                趋势：{review.actual_trend}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
