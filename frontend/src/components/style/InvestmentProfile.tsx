import { Loader2, Sparkles, Shield, Clock, Target, UserCheck, FileText } from 'lucide-react'
import type { RadarPoint, RadarProfile } from '@/hooks/useStyleProfile'
import type { PreferencesData } from '@/hooks/usePreferences'
import { RadarChart } from './RadarChart'

interface InvestmentProfileProps {
  profile: RadarProfile | null
  /** 画像是否加载中 */
  loading?: boolean
  /** 未测试时点击开始测试 */
  onStartQuiz: () => void
  /** 已测试时点击重新测试（仅重置画像，不弹窗） */
  onRetakeQuiz: () => void
  /** 偏好数据（已测试时有值） */
  preferences?: PreferencesData | null
}

/** 未测试时的空六维表（仅网格 + 顶点标签，无数据多边形） */
const EMPTY_POINTS: RadarPoint[] = [
  { dimension: 'risk_appetite', label: '风险偏好', axis_label: '保守-激进', score: 0, score_0_100: 0, matched_style: '', evidence_count: 0 },
  { dimension: 'time_horizon', label: '时间周期', axis_label: '短线-长线', score: 0, score_0_100: 0, matched_style: '', evidence_count: 0 },
  { dimension: 'decision_basis', label: '决策依据', axis_label: '技术-基本面', score: 0, score_0_100: 0, matched_style: '', evidence_count: 0 },
  { dimension: 'trading_style', label: '交易风格', axis_label: '左侧-右侧', score: 0, score_0_100: 0, matched_style: '', evidence_count: 0 },
  { dimension: 'concentration', label: '仓位集中度', axis_label: '分散-集中', score: 0, score_0_100: 0, matched_style: '', evidence_count: 0 },
  { dimension: 'emotion_pref', label: '情绪偏好', axis_label: '防御-题材', score: 0, score_0_100: 0, matched_style: '', evidence_count: 0 },
]

/**
 * 右侧栏「投资画像」模块 — 替换原"对话上下文"占位。
 * 未测试：标题 + 空六维表 + 开始测试按钮（简洁引导）；
 * 已测试：六维雷达图 + 概要 + 维度条 + 重新测试。
 */
export function InvestmentProfile({ profile, loading, onStartQuiz, onRetakeQuiz, preferences }: InvestmentProfileProps) {
  const tested = !!profile && profile.quiz_completed_count > 0

  return (
    <div className="flex flex-1 min-h-0 flex-col">
      {/* 标题 */}
      <div className="shrink-0 flex items-center justify-between px-4 py-2">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-medium text-[var(--color-text-primary)]">投资画像</span>
          <span className="rounded bg-[var(--color-accent-soft)] px-1.5 py-0.5 text-xs text-[var(--color-accent)]">
            6 维度
          </span>
        </div>
        {tested && (
          <button
            onClick={onRetakeQuiz}
            className="flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-[var(--color-accent)] hover:bg-[var(--color-accent-soft)] transition-colors"
          >
            <Sparkles className="h-3 w-3" />
            重新测试
          </button>
        )}
      </div>

      {loading ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 pb-4 text-[var(--color-text-tertiary)]">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span className="text-xs">加载画像中…</span>
        </div>
      ) : tested && profile ? (
        /* ── 已测试：真实画像，内容紧凑靠上 ── */
        <div className="flex min-h-0 flex-col items-center overflow-y-auto scrollbar-hide px-4 pb-4">
          <div className="flex w-full items-center justify-center mt-2">
            <RadarChart points={profile.points} className="w-full max-w-[280px] max-h-[280px]" />
          </div>
          <p className="mt-1 shrink-0 text-center text-base leading-relaxed text-[var(--color-text-secondary)]">
            {profile.summary}
          </p>
          <div className="mt-2 w-full shrink-0 space-y-1.5">
            {profile.points.map((p) => (
              <div key={p.dimension} className="flex items-center gap-2">
                <span className="w-14 shrink-0 text-xs text-[var(--color-text-tertiary)]">
                  {p.label}
                </span>
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--color-bg-hover)]">
                  <div
                    className="h-full rounded-full bg-[var(--color-accent)]"
                    style={{ width: `${Math.max(4, p.score_0_100)}%` }}
                  />
                </div>
                <span className="w-14 shrink-0 text-right text-xs text-[var(--color-text-secondary)]">
                  {p.matched_style}
                </span>
              </div>
            ))}
          </div>

          {/* 偏好文件渲染 */}
          {preferences?.evolution && (
            <div className="mt-4 w-full shrink-0 rounded-lg border border-[var(--color-border-light)] bg-white px-4 py-3">
              <div className="flex items-center gap-1.5 mb-2">
                <FileText className="h-3.5 w-3.5 text-[var(--color-accent)]" />
                <span className="text-xs font-medium text-[var(--color-text-primary)]">画像诊断报告</span>
              </div>
              <pre className="whitespace-pre-wrap text-xs leading-relaxed text-[var(--color-text-secondary)] font-sans">
                {preferences.evolution}
              </pre>
            </div>
          )}
        </div>
      ) : (
        /* ── 未测试：引导提示 + 按钮 + 空六维雷达图 + 功能说明 ── */
        <div className="flex flex-1 min-h-0 flex-col overflow-y-auto scrollbar-hide px-4 pb-4 pt-8">
          <div className="shrink-0 rounded-lg bg-[var(--color-bg-subtle)] px-3 py-3">
            <p className="text-center text-base leading-relaxed text-[var(--color-text-secondary)]">
              <Sparkles className="inline h-3.5 w-3.5 mr-1 -mt-0.5 text-[var(--color-accent)]" />
              快来看看你的投资风格，让我们能更好地帮助你投资
            </p>
          </div>
          <button
            onClick={onStartQuiz}
            className="mt-4 shrink-0 rounded-full bg-[var(--color-accent)] px-6 py-2 text-base font-medium text-white hover:bg-[var(--color-accent-hover)] transition-colors self-center"
          >
            开始测试
          </button>
          <div className="flex w-full items-center justify-center mt-1">
            <RadarChart points={EMPTY_POINTS} empty className="w-full max-w-[280px] max-h-[280px]" />
          </div>

          {/* 功能说明 */}
          <div className="mt-4 shrink-0 rounded-lg border border-[var(--color-border-light)] bg-white px-4 py-4">
            <p className="text-base leading-relaxed font-medium text-[var(--color-text-primary)]">
              完成投资风格测试，生成你的专属投资画像
            </p>
            <p className="mt-2 text-xs leading-relaxed text-[var(--color-text-secondary)]">
              系统将记录你的风险偏好、情绪偏好、仓位习惯、交易周期与决策依据。后续智能助手会以此为基准：
            </p>
            <div className="mt-3 space-y-2.5">
              <div className="flex items-start gap-2.5">
                <Shield className="h-4 w-4 mt-0.5 shrink-0 text-[var(--color-accent)]" />
                <span className="text-xs leading-relaxed text-[var(--color-text-secondary)]">
                  避开超出你风险承受能力的投资思路
                </span>
              </div>
              <div className="flex items-start gap-2.5">
                <Clock className="h-4 w-4 mt-0.5 shrink-0 text-[var(--color-accent)]" />
                <span className="text-xs leading-relaxed text-[var(--color-text-secondary)]">
                  匹配适合你的持仓周期与仓位建议
                </span>
              </div>
              <div className="flex items-start gap-2.5">
                <Target className="h-4 w-4 mt-0.5 shrink-0 text-[var(--color-accent)]" />
                <span className="text-xs leading-relaxed text-[var(--color-text-secondary)]">
                  结合你的决策习惯输出分析，减少无关推荐
                </span>
              </div>
              <div className="flex items-start gap-2.5">
                <UserCheck className="h-4 w-4 mt-0.5 shrink-0 text-[var(--color-accent)]" />
                <span className="text-xs leading-relaxed text-[var(--color-text-secondary)]">
                  所有 AI 输出的投资建议，都更贴合你的个人情况，不再是通用模板
                </span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
