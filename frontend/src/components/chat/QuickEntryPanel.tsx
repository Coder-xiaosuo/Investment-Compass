import { useState, useEffect } from 'react'
import { TrendingUp, TrendingDown, Calendar, Zap, ChevronLeft, ChevronRight, Flame, ListOrdered, Target } from 'lucide-react'
import { useQuickEntry, type HotSector, type CalendarEvent, type RankingItem, type StrategyItem } from '@/hooks/useQuickEntry'

/* ================================================================
   QuickEntryPanel — 对话页输入框下方投研快捷入口面板（v3 三列网格）

   数据源：优先调用 /api/demo/* 接口，失败时回退内置模拟数据
   ================================================================ */

interface QuickEntryPanelProps {
  onSend: (text: string) => void
}

/* ────────── 数据定义 ────────── */

type QuestionTab = 'tech' | 'fund' | 'basis'

const QUESTION_TABS: { key: QuestionTab; label: string }[] = [
  { key: 'tech', label: '技术面' },
  { key: 'fund', label: '资金面' },
  { key: 'basis', label: '基本面' },
]

const QUESTIONS: Record<QuestionTab, string[]> = {
  tech: [
    '放量突破月线三阳',
    '底部反转底背离',
    '冷门股KDJ金叉',
    '均线多头排列',
    'MACD零轴金叉',
    '缩量回踩支撑位',
    '龙虎榜机构净买入',
    '涨停板回调低吸',
  ],
  fund: [
    '北向资金净流入',
    '主力控盘低价股',
    '高现金高毛利',
    '连续资金流入',
    '大宗交易溢价成交',
    '融资余额持续增加',
    '大单净流入排行',
    '机构重仓股增持',
  ],
  basis: [
    '低估值高股息',
    '营收持续增长',
    'ROE连续三年大于15%',
    '业绩预增翻倍',
    '市盈率低于行业均值',
    '连续分红超10年',
    'PEG小于1的成长股',
    '高净资产收益率',
  ],
}

const HOT_SECTORS = [
  { name: 'AI人工智能', change: 4.32, reason: 'OpenAI发布新一代推理模型' },
  { name: '半导体', change: 3.15, reason: '国产替代政策加速落地' },
  { name: '新能源车', change: 2.87, reason: '8月销量同比增长45%' },
  { name: '机器人', change: -1.23, reason: '特斯拉Optimus量产推迟' },
  { name: '低空经济', change: 5.61, reason: '多省市发布低空空域开放政策' },
  { name: '数据要素', change: 1.98, reason: '数据资产入表细则出台' },
  { name: '创新药', change: -0.76, reason: '集采范围扩大影响预期' },
  { name: '光伏', change: -2.14, reason: '组件价格持续低迷' },
]

const UPCOMING_EVENTS = [
  { date: '08-15', name: '美联储议息会议纪要', desc: '关注降息路径指引' },
  { date: '08-18', name: '世界人工智能大会', desc: '大模型+具身智能' },
  { date: '08-20', name: 'LPR报价日', desc: '关注5年期LPR调整' },
  { date: '08-25', name: '光伏行业峰会', desc: '新技术路线与产能' },
  { date: '08-28', name: '中报披露截止日', desc: '业绩暴雷/超预期' },
]

const RANKINGS = [
  {
    title: '涨幅榜',
    desc: '今日涨幅TOP3',
    stocks: ['N强邦 +120%', '双成药业 +10%', '华立股份 +10%'],
  },
  {
    title: '营收榜',
    desc: '连续5年营收增长',
    stocks: ['贵州茅台', '宁德时代', '比亚迪'],
  },
  {
    title: '主力资金榜',
    desc: '今日主力净流入TOP',
    stocks: ['科大讯飞', '中科曙光', '浪潮信息'],
  },
  {
    title: '行业龙头榜',
    desc: '细分行业市占率第一',
    stocks: ['海康威视', '恒瑞医药', '迈瑞医疗'],
  },
]

const STRATEGIES = [
  { name: '主力控盘低价股战法', annual: 18.6, total: 142.3, drawdown: -15.2 },
  { name: '高股息稳健策略', annual: 12.4, total: 89.7, drawdown: -8.5 },
  { name: '北向资金流入战法', annual: 15.8, total: 115.2, drawdown: -12.1 },
]

/* ────────── 共用子组件 ────────── */

function ChangeBadge({ value }: { value: number }) {
  const isUp = value > 0
  const color = isUp ? 'text-[var(--color-up)]' : 'text-[var(--color-down)]'
  const Icon = isUp ? TrendingUp : TrendingDown
  return (
    <span className={`inline-flex items-center gap-0.5 text-xs font-bold tabular-nums ${color}`}>
      <Icon className="h-3 w-3" />
      {isUp ? '+' : ''}{value.toFixed(2)}%
    </span>
  )
}

function RankBadge({ rank }: { rank: number }) {
  const colors: Record<number, string> = {
    1: 'bg-amber-100 text-amber-700',
    2: 'bg-slate-100 text-slate-500',
    3: 'bg-orange-50 text-orange-600',
  }
  return (
    <span className={`inline-flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded text-[9px] font-bold ${colors[rank] || 'bg-gray-100 text-gray-400'}`}>
      {rank}
    </span>
  )
}

/** 模块卡片标题 */
function CardTitle({ icon: Icon, iconBg, iconColor, title, extra }: {
  icon: typeof Zap
  iconBg: string
  iconColor: string
  title: string
  extra?: React.ReactNode
}) {
  return (
    <div className="flex items-center gap-2 mb-2.5">
      <div className={`flex h-6 w-6 items-center justify-center rounded-md ${iconBg}`}>
        <Icon className={`h-3.5 w-3.5 ${iconColor}`} />
      </div>
      <span className="text-sm font-semibold text-[var(--color-text-primary)]">{title}</span>
      {extra && <div className="ml-auto">{extra}</div>}
    </div>
  )
}

/* ────────── 元素基础样式 ────────── */

const innerCard = 'rounded-lg border border-[var(--color-border-light)] bg-white px-3 py-2.5 text-left transition-all duration-200 hover:border-[var(--color-accent)]/30 hover:shadow-sm hover:-translate-y-0.5 cursor-pointer'
const innerCardGray = 'rounded-lg border border-[var(--color-border-light)] bg-[var(--color-bg-subtle)] px-3 py-2.5 text-left transition-all duration-200 hover:border-[var(--color-accent)]/30 hover:shadow-sm hover:-translate-y-0.5 cursor-pointer'
const tagBtn = 'rounded-lg border border-[var(--color-border-light)] bg-white px-3 py-2.5 text-xs text-[var(--color-text-secondary)] text-left transition-all duration-200 hover:bg-[var(--color-accent-soft)] hover:border-[var(--color-accent)]/30 hover:text-[var(--color-accent)] cursor-pointer'

/* ───────────────────────────────────────────────
   主组件
   ─────────────────────────────────────────────── */

export function QuickEntryPanel({ onSend }: QuickEntryPanelProps) {
  const [activeTab, setActiveTab] = useState<QuestionTab>('tech')
  const { fetchHotSectors, fetchCalendarEvents, fetchRankings, fetchStrategies } = useQuickEntry()

  // 数据状态：优先 API，失败回退模拟数据
  const [hotSectors, setHotSectors] = useState<HotSector[]>(HOT_SECTORS)
  const [events, setEvents] = useState<CalendarEvent[]>(UPCOMING_EVENTS)
  const [rankings, setRankings] = useState<RankingItem[]>(RANKINGS)
  const [strategies, setStrategies] = useState<StrategyItem[]>(STRATEGIES)

  useEffect(() => {
    fetchHotSectors().then(setHotSectors).catch(() => {})
    fetchCalendarEvents().then(setEvents).catch(() => {})
    fetchRankings().then(setRankings).catch(() => {})
    fetchStrategies().then(setStrategies).catch(() => {})
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="flex w-full flex-col gap-4 select-none pb-2">

      {/* ======== 第一行：常用提问 / 今日热点 / 未来大事 ======== */}
      <div className="grid grid-cols-3 gap-4">

        {/* 模块1：常用提问 */}
        <div className="rounded-xl border border-[var(--color-border-light)] bg-white p-5 shadow-sm">
          <CardTitle
            icon={Zap}
            iconBg="bg-[var(--color-accent-soft)]"
            iconColor="text-[var(--color-accent)]"
            title="常用提问"
            extra={
              <div className="flex gap-0.5 rounded-md bg-[var(--color-bg-subtle)] p-0.5">
                {QUESTION_TABS.map((t) => (
                  <button
                    key={t.key}
                    onClick={() => setActiveTab(t.key)}
                    className={`rounded px-2.5 py-1 text-[11px] font-medium transition-all duration-200 ${
                      activeTab === t.key
                        ? 'bg-[var(--color-accent)] text-white shadow-sm'
                        : 'text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)]'
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            }
          />
          <div className="grid grid-cols-2 gap-2">
            {QUESTIONS[activeTab].map((q) => (
              <button key={q} onClick={() => onSend(q)} className={tagBtn}>
                {q}
              </button>
            ))}
          </div>
        </div>

        {/* 模块2：今日热点 */}
        <div className="rounded-xl border border-[var(--color-border-light)] bg-white p-5 shadow-sm">
          <CardTitle
            icon={Flame}
            iconBg="bg-red-50"
            iconColor="text-[var(--color-up)]"
            title="今日热点"
            extra={<span className="text-[10px] text-[var(--color-text-tertiary)]">实时更新</span>}
          />
          <div className="grid grid-cols-2 gap-2">
            {hotSectors.map((s) => (
              <button
                key={s.name}
                onClick={() => onSend(`深度分析${s.name}板块投资机会`)}
                className={innerCard}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-semibold text-[var(--color-text-primary)]">{s.name}</span>
                  <ChangeBadge value={s.change} />
                </div>
                <p className="text-[10px] leading-relaxed text-[var(--color-text-tertiary)] line-clamp-1">
                  {s.reason}
                </p>
              </button>
            ))}
          </div>
        </div>

        {/* 模块3：未来大事 */}
        <div className="rounded-xl border border-[var(--color-border-light)] bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between mb-2.5">
            <CardTitle icon={Calendar} iconBg="bg-amber-50" iconColor="text-amber-600" title="未来大事" />
            <div className="flex items-center gap-0.5">
              <button className="flex h-6 w-6 items-center justify-center rounded border border-[var(--color-border-light)] text-[var(--color-text-tertiary)] hover:text-[var(--color-accent)]">
                <ChevronLeft className="h-3.5 w-3.5" />
              </button>
              <button className="flex h-6 w-6 items-center justify-center rounded border border-[var(--color-border-light)] text-[var(--color-text-tertiary)] hover:text-[var(--color-accent)]">
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
          <div className="flex flex-col gap-2 overflow-y-auto scrollbar-hide" style={{ maxHeight: 340 }}>
            {events.map((e) => (
              <button
                key={e.name}
                onClick={() => onSend(`${e.name}事件对A股有什么影响`)}
                className={innerCard}
              >
                <span className="inline-block rounded bg-[var(--color-accent-soft)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--color-accent)] mb-1">
                  {e.date}
                </span>
                <h4 className="text-xs font-semibold text-[var(--color-text-primary)] leading-snug mb-0.5">
                  {e.name}
                </h4>
                <p className="text-[11px] leading-relaxed text-[var(--color-text-tertiary)] line-clamp-2">
                  {e.desc}
                </p>
              </button>
            ))}
          </div>
        </div>

      </div>

      {/* ======== 第二行：特色榜单 / 经典策略 / 占位 ======== */}
      <div className="grid grid-cols-3 gap-4">

        {/* 模块4：特色榜单 */}
        <div className="rounded-xl border border-[var(--color-border-light)] bg-white p-5 shadow-sm">
          <CardTitle icon={ListOrdered} iconBg="bg-purple-50" iconColor="text-purple-600" title="特色榜单" />
          <div className="flex flex-col gap-2">
            {rankings.map((r) => (
              <button
                key={r.title}
                onClick={() => onSend(`查看${r.title}详细名单与分析`)}
                className={innerCardGray}
              >
                <div className="flex items-center gap-1.5 mb-2">
                  <span className="text-xs font-semibold text-[var(--color-text-primary)]">{r.title}</span>
                  <span className="text-[10px] text-[var(--color-text-tertiary)]">· {r.desc}</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {r.stocks.map((s, i) => (
                    <div key={s} className="flex items-center gap-1.5">
                      <RankBadge rank={i + 1} />
                      <span className="text-[11px] text-[var(--color-text-secondary)]">{s}</span>
                    </div>
                  ))}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* 模块5：经典策略 */}
        <div className="rounded-xl border border-[var(--color-border-light)] bg-white p-5 shadow-sm">
          <CardTitle icon={Target} iconBg="bg-emerald-50" iconColor="text-emerald-600" title="经典策略" />
          <div className="flex flex-col gap-2.5">
            {strategies.map((s) => (
              <button
                key={s.name}
                onClick={() => onSend(`回测${s.name}的近期表现`)}
                className={innerCard}
              >
                <h4 className="text-xs font-semibold text-[var(--color-text-primary)] mb-2">
                  {s.name}
                </h4>
                <div className="flex items-baseline gap-1.5 mb-1.5">
                  <span className="text-xl font-bold text-[var(--color-up)] tabular-nums">{s.annual}%</span>
                  <span className="text-[10px] text-[var(--color-text-tertiary)]">年化收益</span>
                </div>
                <div className="flex items-center justify-between text-[10px]">
                  <span className="text-[var(--color-text-tertiary)]">
                    累计 <span className="font-medium text-[var(--color-text-secondary)]">+{s.total}%</span>
                  </span>
                  <span className="text-[var(--color-down)] font-medium">回撤 {s.drawdown}%</span>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* 第三列占位 */}
        <div className="rounded-xl border border-dashed border-[var(--color-border-light)] bg-white/50 p-4" />

      </div>

    </div>
  )
}

export default QuickEntryPanel
