import { memo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Components } from 'react-markdown'
import { cn } from '@/lib/utils'

/**
 * 统一 Markdown 渲染组件：将 AI 回答的 MD 语法渲染为结构化界面，
 * 样式映射到现有 CSS 变量体系（标题层级 / 表格 / 列表 / 代码块 / 引用）。
 *
 * 使用 react-markdown（默认转义 HTML，避免 XSS）+ remark-gfm（表格/任务列表等扩展）。
 */
const COMPONENTS: Components = {
  // ── 标题：收敛为 4 级（与全局字号体系对齐：xl=20 / lg=18 / base=16）──
  h1: ({ children, ...props }) => (
    <h1 {...props} className="mb-1.5 mt-3 text-xl font-semibold leading-snug text-[var(--color-text-primary)] first:mt-0">
      {children}
    </h1>
  ),
  h2: ({ children, ...props }) => (
    <h2 {...props} className="mb-1.5 mt-3 text-lg font-semibold leading-snug text-[var(--color-text-primary)] first:mt-0">
      {children}
    </h2>
  ),
  h3: ({ children, ...props }) => (
    <h3 {...props} className="mb-1 mt-2.5 text-base font-semibold leading-snug text-[var(--color-text-primary)] first:mt-0">
      {children}
    </h3>
  ),
  h4: ({ children, ...props }) => (
    <h4 {...props} className="mb-1 mt-2 text-base font-medium leading-snug text-[var(--color-text-primary)] first:mt-0">
      {children}
    </h4>
  ),

  // ── 段落与内联 ──
  p: ({ children, ...props }) => (
    <p {...props} className="my-1.5 text-base leading-relaxed text-[var(--color-text-primary)]">
      {children}
    </p>
  ),
  strong: ({ children, ...props }) => (
    <strong {...props} className="font-semibold text-[var(--color-text-primary)]">
      {children}
    </strong>
  ),
  em: ({ children, ...props }) => (
    <em {...props} className="text-[var(--color-text-primary)]">
      {children}
    </em>
  ),
  del: ({ children, ...props }) => (
    <del {...props} className="text-[var(--color-text-tertiary)]">
      {children}
    </del>
  ),
  a: ({ children, ...props }) => (
    <a {...props} target="_blank" rel="noreferrer" className="break-all text-[var(--color-accent)] underline underline-offset-2 hover:text-[var(--color-accent-hover)]">
      {children}
    </a>
  ),

  // ── 列表 ──
  ul: ({ children, ...props }) => (
    <ul {...props} className="my-1.5 list-disc space-y-1 pl-5 text-base leading-relaxed text-[var(--color-text-primary)] marker:text-[var(--color-accent)]">
      {children}
    </ul>
  ),
  ol: ({ children, ...props }) => (
    <ol {...props} className="my-1.5 list-decimal space-y-1 pl-5 text-base leading-relaxed text-[var(--color-text-primary)] marker:text-[var(--color-accent)]">
      {children}
    </ol>
  ),
  li: ({ children, ...props }) => (
    <li {...props} className="text-base leading-relaxed text-[var(--color-text-primary)]">
      {children}
    </li>
  ),

  // ── 代码：行内 vs 代码块 ──
  code: ({ children, className, ...props }) => {
    // react-markdown 中代码块（pre>code）与行内 code 均走此处；用是否含换行/语言标记粗判
    const isBlock = /language-/.test(className ?? '')
    if (isBlock) {
      return (
        <code {...props} className={cn('block overflow-x-auto p-0 font-mono text-[13px] leading-relaxed text-[var(--color-text-primary)]', className)}>
          {children}
        </code>
      )
    }
    return (
      <code {...props} className="rounded bg-[var(--color-bg-hover)] px-1.5 py-0.5 font-mono text-[13px] text-[var(--color-accent-hover)]">
        {children}
      </code>
    )
  },
  pre: ({ children, ...props }) => (
    <pre {...props} className="my-2 overflow-x-auto rounded-lg border border-[var(--color-border-light)] bg-[var(--color-bg-subtle)] p-2.5 font-mono text-[13px] leading-relaxed text-[var(--color-text-primary)]">
      {children}
    </pre>
  ),

  // ── 引用 ──
  blockquote: ({ children, ...props }) => (
    <blockquote
      {...props}
      className="my-2 border-l-2 border-[var(--color-accent)] bg-[var(--color-accent-soft)] py-1 pl-3 pr-2 text-base leading-relaxed text-[var(--color-text-secondary)]"
    >
      {children}
    </blockquote>
  ),

  // ── 表格（AI 高频内容，GFM 支持）──
  table: ({ children, ...props }) => (
    <div className="my-2 overflow-x-auto rounded-lg border border-[var(--color-border-light)]">
      <table {...props} className="w-full border-collapse text-sm leading-relaxed">
        {children}
      </table>
    </div>
  ),
  thead: ({ children, ...props }) => (
    <thead {...props} className="bg-[var(--color-bg-subtle)]">
      {children}
    </thead>
  ),
  tbody: ({ children, ...props }) => <tbody {...props}>{children}</tbody>,
  tr: ({ children, ...props }) => (
    <tr {...props} className="border-b border-[var(--color-border-light)] last:border-b-0">
      {children}
    </tr>
  ),
  th: ({ children, ...props }) => (
    <th {...props} className="whitespace-nowrap border-r border-[var(--color-border-light)] px-2.5 py-1.5 text-left text-xs font-semibold text-[var(--color-text-secondary)] last:border-r-0">
      {children}
    </th>
  ),
  td: ({ children, ...props }) => (
    <td {...props} className="border-r border-[var(--color-border-light)] px-2.5 py-1.5 align-top text-[13px] text-[var(--color-text-primary)] last:border-r-0">
      {children}
    </td>
  ),

  // ── 分隔线 ──
  hr: ({ ...props }) => <hr {...props} className="my-2.5 border-t border-[var(--color-border)]" />,
}

interface MarkdownProps {
  /** MD 源文本 */
  content: string
  /** 是否正在流式输出（追加光标动画） */
  streaming?: boolean
  /** 紧凑模式（右侧面板 text-xs 风格）：整体字号降一档 */
  compact?: boolean
  className?: string
}

/** 流式状态的光标元素（与 StreamingBubble 原样式保持一致） */
function Cursor() {
  return <span className="ml-0.5 inline-block h-3.5 w-[2px] animate-pulse align-middle bg-[var(--color-accent)]" />
}

/**
 * Markdown 渲染器。
 *
 * 流式场景：由调用方先经 useThrottledValue 节流再传入 content，
 * 避免高频 chunk 触发全量解析；组件内部不再二次节流。
 */
function MarkdownBase({ content, streaming = false, compact = false, className }: MarkdownProps) {
  return (
    <div className={cn('md-body break-words', compact && 'md-body-compact', className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={COMPONENTS}>
        {content}
      </ReactMarkdown>
      {streaming && <Cursor />}
    </div>
  )
}

/** memo：content 未变化时跳过重渲染（历史消息场景收益明显） */
export const Markdown = memo(MarkdownBase)
