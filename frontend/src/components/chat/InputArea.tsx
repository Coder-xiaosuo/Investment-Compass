import { useState, useRef, useCallback } from 'react'
import { SendHorizonal, Paperclip, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'

interface InputAreaProps {
  onSend: (content: string) => void
  disabled?: boolean
}

/** 输入框默认最小高度（约 4 行，text-base 行高） */
const MIN_TEXTAREA_H = 96

export function InputArea({ onSend, disabled = false }: InputAreaProps) {
  const [value, setValue] = useState('')
  const [focused, setFocused] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleSend = useCallback(() => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }, [value, disabled, onSend])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleInput = () => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    // 默认最小 4 行高度，输入超出后再增高（上限 200px）
    el.style.height = `${Math.min(Math.max(el.scrollHeight, MIN_TEXTAREA_H), 200)}px`
  }

  const hasValue = value.trim().length > 0

  return (
    <div className="w-full max-w-[720px]">
      {/* 输入框主体 */}
      <div
        className={cn(
          'flex flex-col rounded-[20px] border-2 p-3 transition-all',
          focused
            ? 'border-[var(--color-border)] shadow-[0_2px_12px_rgba(0,0,0,0.06)]'
            : hasValue
              ? 'border-[var(--color-border)]'
              : 'border-[var(--color-border-light)]',
          'bg-[var(--color-bg-surface)]',
        )}
      >
        {/* 文本输入区（从左上角开始，占满宽度，默认 4 行，自动增高） */}
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder="输入消息开始分析..."
          disabled={disabled}
          rows={4}
          className="w-full resize-none bg-transparent text-base text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-placeholder)] leading-relaxed max-h-[200px]"
          style={{ minHeight: MIN_TEXTAREA_H }}
        />

        {/* 底部工具栏：附件居左，优化提示词 + 发送居右 */}
        <div className="mt-2 flex items-center justify-between">
          {/* 左侧附件按钮 */}
          <button
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-[var(--color-text-tertiary)] hover:bg-[var(--color-bg-hover)] hover:text-[var(--color-text-secondary)] transition-colors"
            title="添加上下文"
          >
            <Paperclip className="h-4 w-4" />
          </button>

          {/* 右侧操作区 */}
          <div className="flex items-center gap-0.5">
            {/* 优化提示词按钮（有内容时显示） */}
            {hasValue && (
              <button
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-[var(--color-text-tertiary)] hover:bg-[var(--color-bg-hover)] hover:text-[var(--color-warning)] transition-colors"
                title="优化提示词"
              >
                <Sparkles className="h-3.5 w-3.5" />
              </button>
            )}

            {/* 发送按钮（与其他操作按钮统一配色：浅蓝底 + 天蓝图标） */}
            <button
              onClick={handleSend}
              disabled={!hasValue || disabled}
              className={cn(
                'flex h-7 w-7 shrink-0 items-center justify-center rounded-lg transition-all',
                hasValue && !disabled
                  ? 'bg-[var(--color-accent-soft)] text-[var(--color-accent)] hover:bg-[var(--color-accent)] hover:text-white'
                  : 'bg-[var(--color-bg-subtle)] text-[var(--color-text-tertiary)]',
              )}
            >
              <SendHorizonal className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
