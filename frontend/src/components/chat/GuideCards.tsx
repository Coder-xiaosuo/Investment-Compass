import { Newspaper, Flame, BarChart3 } from 'lucide-react'

interface GuideCardsProps {
  /** 点击卡片时触发，传入对应的分析指令 */
  onSend: (text: string) => void
}

interface CardConfig {
  icon: typeof Newspaper
  title: string
  items: string[]
  action: string
  accent: 'info' | 'warning' | 'success'
}

const CARDS: CardConfig[] = [
  {
    icon: Newspaper,
    title: '今日资讯',
    items: ['茅台Q3业绩超预期', '宁德时代发布新品', '央行降准0.25%'],
    action: '今日资讯',
    accent: 'info',
  },
  {
    icon: Flame,
    title: '热门策略',
    items: ['价值回归策略', '技术突破策略'],
    action: '推荐策略',
    accent: 'warning',
  },
  {
    icon: BarChart3,
    title: '市场大盘',
    items: ['沪深300 +0.8%', '创业板 -0.3%'],
    action: '分析沪深300',
    accent: 'success',
  },
]

const ACCENT_MAP: Record<CardConfig['accent'], { icon: string; hover: string }> = {
  info: {
    icon: 'text-[var(--color-info)]',
    hover: 'hover:border-[var(--color-info)]',
  },
  warning: {
    icon: 'text-[var(--color-warning)]',
    hover: 'hover:border-[var(--color-warning)]',
  },
  success: {
    icon: 'text-[var(--color-success)]',
    hover: 'hover:border-[var(--color-success)]',
  },
}

export function GuideCards({ onSend }: GuideCardsProps) {
  return (
    <div className="grid w-full max-w-[720px] grid-cols-1 gap-3 sm:grid-cols-3">
      {CARDS.map((card) => {
        const Icon = card.icon
        const accent = ACCENT_MAP[card.accent]
        return (
          <button
            key={card.title}
            onClick={() => onSend(card.action)}
            className={`flex flex-col rounded-xl border border-[var(--color-border-light)] bg-[var(--color-bg-surface)] p-3 text-left transition-colors ${accent.hover}`}
          >
            <div className="mb-2 flex items-center gap-1.5">
              <Icon className={`h-3.5 w-3.5 ${accent.icon}`} />
              <span className="text-xs font-medium text-[var(--color-text-primary)]">
                {card.title}
              </span>
            </div>
            <ul className="space-y-1">
              {card.items.map((item, idx) => (
                <li
                  key={idx}
                  className="truncate text-xs text-[var(--color-text-tertiary)]"
                >
                  {item}
                </li>
              ))}
            </ul>
          </button>
        )
      })}
    </div>
  )
}
