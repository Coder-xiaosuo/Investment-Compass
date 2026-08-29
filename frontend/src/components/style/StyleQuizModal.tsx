import { useEffect, useMemo, useState } from 'react'
import { ChevronLeft, ChevronRight, Loader2, Sparkles, X } from 'lucide-react'
import { useStyleProfile, type QuizQuestion, type RadarProfile } from '@/hooks/useStyleProfile'
import { RadarChart } from './RadarChart'
import { cn } from '@/lib/utils'

interface StyleQuizModalProps {
  open: boolean
  onClose: () => void
  /** 提交成功后回调（父级刷新画像/气泡状态） */
  onCompleted: () => void
}

const PAGE_SIZE = 5

/** 投资风格冷启动问卷弹窗：30 题分页（每页5题×6页）+ 结果雷达图 */
export function StyleQuizModal({ open, onClose, onCompleted }: StyleQuizModalProps) {
  const { fetchQuestions, fetchProfile, submitAnswers } = useStyleProfile()
  const [questions, setQuestions] = useState<QuizQuestion[]>([])
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(0)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<RadarProfile | null>(null)

  const totalPages = useMemo(() => Math.max(1, Math.ceil(questions.length / PAGE_SIZE)), [questions])
  const pageQuestions = useMemo(
    () => questions.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE),
    [questions, page],
  )
  const pageAnswered = pageQuestions.every((q) => !!answers[q.id])
  const totalAnswered = Object.keys(answers).length

  // 打开时拉题库并重置
  useEffect(() => {
    if (!open) return
    setPage(0)
    setAnswers({})
    setResult(null)
    setError('')
    setLoading(true)
    fetchQuestions()
      .then(({ questions: qs }) => setQuestions(qs))
      .catch(() => setError('题库加载失败，请稍后重试'))
      .finally(() => setLoading(false))
  }, [open, fetchQuestions])

  // 关闭时若已提交，通知父级刷新（由 onCompleted 处理）
  const handleClose = () => {
    onClose()
  }

  const pick = (qid: string, label: string) => {
    setAnswers((prev) => (prev[qid] === label ? { ...prev, [qid]: '' } : { ...prev, [qid]: label }))
  }

  const nextPage = () => {
    if (!pageAnswered) return
    setPage((p) => Math.min(totalPages - 1, p + 1))
  }

  const submit = async () => {
    if (totalAnswered < 6) {
      setError('请至少完成 6 题后再提交')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      const list = Object.entries(answers)
        .filter(([, label]) => !!label)
        .map(([question_id, selected_label]) => ({ question_id, selected_label }))
      await submitAnswers(list)
      const profile = await fetchProfile()
      setResult(profile)
      onCompleted()
    } catch (e: any) {
      setError(e?.message || '提交失败，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4" onClick={handleClose}>
      <div
        className="flex max-h-[86vh] w-[560px] max-w-full flex-col rounded-2xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[var(--color-border-light)] px-6 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--color-accent)] text-white shadow-md">
              <Sparkles className="h-4 w-4" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">投资风格测试</h2>
              <p className="text-xs text-[var(--color-text-tertiary)]">
                {result ? '你的投资画像' : `第 ${Math.min(totalAnswered + 1, questions.length)} / ${questions.length} 题`}
              </p>
            </div>
          </div>
          <button
            onClick={handleClose}
            className="flex h-8 w-8 items-center justify-center rounded-full text-[var(--color-text-tertiary)] hover:bg-[var(--color-bg-hover)] transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {loading ? (
          <div className="flex flex-col items-center justify-center gap-2 py-16 text-[var(--color-text-tertiary)]">
            <Loader2 className="h-5 w-5 animate-spin text-[var(--color-accent)]" />
            <span className="text-base">加载题库中…</span>
          </div>
        ) : result ? (
          /* ── 结果区 ── */
          <div className="overflow-y-auto px-6 py-5">
            <div className="text-center">
              <h3 className="text-xl font-semibold text-[var(--color-text-primary)]">测试完成！</h3>
              <p className="mt-1 text-base text-[var(--color-text-tertiary)]">{result.summary}</p>
            </div>
            <div className="mt-4 flex justify-center">
              <RadarChart points={result.points} size={280} className="h-64 w-64" />
            </div>
            <div className="mt-4 grid grid-cols-2 gap-2">
              {result.points.map((p) => (
                <div key={p.dimension} className="rounded-lg bg-[var(--color-bg-subtle)] px-3 py-2">
                  <p className="text-xs text-[var(--color-text-tertiary)]">{p.label}</p>
                  <p className="mt-0.5 flex items-baseline gap-1.5">
                    <span className="text-base font-semibold text-[var(--color-text-primary)]">
                      {p.matched_style}
                    </span>
                    <span className="text-xs text-[var(--color-accent)]">{p.score_0_100}%</span>
                  </p>
                </div>
              ))}
            </div>
            <div className="mt-5 text-center">
              <button
                onClick={handleClose}
                className="rounded-xl bg-[var(--color-accent)] px-6 py-2 text-base font-medium text-white hover:bg-[var(--color-accent-hover)] transition-colors"
              >
                开始使用
              </button>
            </div>
          </div>
        ) : (
          /* ── 问卷区 ── */
          <>
            {/* 进度点 */}
            <div className="flex gap-2 px-6 pt-4">
              {Array.from({ length: totalPages }).map((_, i) => (
                <span
                  key={i}
                  className={cn(
                    'h-2 flex-1 rounded-full transition-colors',
                    i < page ? 'bg-[var(--color-accent)]' : i === page ? 'bg-[var(--color-accent)]/60' : 'bg-[var(--color-border)]',
                  )}
                />
              ))}
            </div>

            {/* 题目区 */}
            <div className="flex-1 overflow-y-auto px-6 py-4">
              {pageQuestions.map((q, idx) => {
                const globalIdx = page * PAGE_SIZE + idx
                const selected = answers[q.id] || ''
                return (
                  <div key={q.id} className="mb-5">
                    <p className="text-base font-medium text-[var(--color-text-primary)]">
                      <span className="mr-1.5 text-[var(--color-accent)]">{String(globalIdx + 1).padStart(2, '0')}</span>
                      {q.scenario}
                    </p>
                    <div className="mt-2 flex flex-col gap-1.5">
                      {q.options.map((opt) => (
                        <button
                          key={opt.label}
                          onClick={() => pick(q.id, opt.label)}
                          className={cn(
                            'flex items-center gap-2 rounded-lg border px-3 py-2 text-left text-xs transition-all',
                            selected === opt.label
                              ? 'border-[var(--color-accent)] bg-[var(--color-accent-soft)] text-[var(--color-text-primary)]'
                              : 'border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[var(--color-border)] hover:bg-[var(--color-bg-subtle)]',
                          )}
                        >
                          <span
                            className={cn(
                              'flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-xs font-medium',
                              selected === opt.label
                                ? 'border-[var(--color-accent)] bg-[var(--color-accent)] text-white'
                                : 'border-[var(--color-border)] text-[var(--color-text-tertiary)]',
                            )}
                          >
                            {opt.label}
                          </span>
                          <span className="min-w-0 flex-1 leading-relaxed">{opt.text}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>

            {error && (
              <p className="px-6 pb-1 text-xs text-[var(--color-danger)]">{error}</p>
            )}

            {/* 导航按钮 */}
            <div className="flex items-center justify-between border-t border-[var(--color-border-light)] px-6 py-3.5">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0 || submitting}
                className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-base text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
                上一页
              </button>

              {page < totalPages - 1 ? (
                <button
                  onClick={nextPage}
                  disabled={!pageAnswered}
                  className="flex items-center gap-1 rounded-lg bg-[var(--color-accent)] px-4 py-1.5 text-base font-medium text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  下一页
                  <ChevronRight className="h-3.5 w-3.5" />
                </button>
              ) : (
                <button
                  onClick={submit}
                  disabled={totalAnswered < 6 || submitting}
                  className="flex items-center gap-1 rounded-lg bg-[var(--color-accent)] px-5 py-1.5 text-base font-medium text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  {submitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                  {submitting ? '提交中…' : '提交'}
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
