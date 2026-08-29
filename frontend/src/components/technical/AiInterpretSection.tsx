import { Sparkles } from 'lucide-react'

interface AiInterpretSectionProps {
  /** 点击后生成预设提示词并在右侧对话中发起提问 */
  onAnalyze: () => void
}

/**
 * 卡片右上角「AI分析」按钮（浅蓝）。
 * 点击触发右侧 AI 对话栏按预设提示词发起提问（不再弹 dropdown 小窗）。
 */
export function AiInterpretSection({ onAnalyze }: AiInterpretSectionProps) {
  return (
    <button
      onClick={onAnalyze}
      className="flex h-6 items-center gap-1 rounded-full bg-[var(--color-accent-soft)] px-2.5 text-xs font-medium text-[var(--color-accent)] transition-all hover:bg-[var(--color-accent)] hover:text-white"
      title="在右侧 AI 对话中发起分析提问"
    >
      <Sparkles className="h-3 w-3" />
      AI 分析
    </button>
  )
}
