import { useState } from 'react'
import { cn } from '@/lib/utils'
import type { AppMode, Conversation } from '@/types'
import { Plus, Settings, Search, Archive, Trash2, PanelLeftClose } from 'lucide-react'
import { groupConversations, formatConversationTime, type ConversationGroup } from '@/lib/date-utils'
import { WatchlistPanel } from './WatchlistPanel'

interface SidebarProps {
  mode: AppMode
  onModeChange: (mode: AppMode) => void
  conversations: Conversation[]
  selectedId: string | null
  onSelectConversation: (id: string) => void
  onNewConversation: () => void
  /** 归档 / 删除会话（hover 操作按钮触发） */
  onArchiveConversation: (id: string) => void
  onDeleteConversation: (id: string) => void
  onOpenSettings?: () => void
}

function GroupLabel({ group }: { group: ConversationGroup }) {
  return (
    <div className="flex items-center px-2 py-1.5">
      <span className="text-sm font-medium text-[var(--color-text-tertiary)] uppercase tracking-wider">
        {group}
      </span>
    </div>
  )
}

export function Sidebar({
  mode,
  onModeChange,
  conversations,
  selectedId,
  onSelectConversation,
  onNewConversation,
  onArchiveConversation,
  onDeleteConversation,
  onOpenSettings,
}: SidebarProps) {
  const [hoveredId, setHoveredId] = useState<string | null>(null)

  // 折叠：仅通过顶部按钮点击切换展开 / 窄条
  const [collapsed, setCollapsed] = useState(false)
  const expanded = !collapsed

  const groups = groupConversations(conversations)

  return (
    <aside
      className="flex shrink-0 flex-col select-none transition-[width] duration-200 ease-out"
      style={{ width: expanded ? 360 : 56 }}
    >
      {/* 窗口控制区 / 折叠开关 */}
      <div className="flex h-8 shrink-0 items-center px-4">
        {expanded ? (
          <>
            <div className="flex items-center gap-[7px]">
              <div className="h-3 w-3 rounded-full bg-[#ED6A5E]" />
              <div className="h-3 w-3 rounded-full bg-[#F5BD4F]" />
              <div className="h-3 w-3 rounded-full bg-[#61C454]" />
            </div>
            <button
              onClick={() => setCollapsed(true)}
              className="ml-auto flex h-6 w-6 items-center justify-center rounded text-[var(--color-text-tertiary)] hover:bg-[var(--color-bg-sidebar-hover)] hover:text-[var(--color-text-secondary)] transition-colors"
              title="折叠侧栏"
            >
              <PanelLeftClose className="h-3.5 w-3.5" />
            </button>
          </>
        ) : (
          <button
            onClick={() => setCollapsed(false)}
            className="mx-auto"
            title="展开侧栏"
          >
            <img src="/logo.jpg" alt="TuanTuan" className="h-8 w-8 rounded-lg object-cover" />
          </button>
        )}
      </div>

      {/* Logo 区域 */}
      {expanded && (
        <div className="flex h-16 shrink-0 items-center gap-3 px-4">
          <img src="/logo.jpg" alt="TuanTuan" className="h-12 w-12 rounded-lg object-cover" />
          <span className="text-3xl font-bold text-sky-500">TuanTuan</span>
        </div>
      )}

      {/* 模式切换 - Segmented Control（窄条时为纵向图标） */}
      {expanded ? (
        <div className="flex h-12 items-center justify-center px-3 shrink-0">
          <div className="flex w-full rounded-[7px] bg-[var(--color-bg-base)] p-[3px]">
            <button
              onClick={() => onModeChange('analysis')}
              className={cn(
                'flex-1 rounded-[5px] py-1.5 text-sm font-medium transition-all duration-150',
                mode === 'analysis'
                  ? 'bg-[var(--color-bg-surface)] text-[var(--color-text-primary)] shadow-[0_1px_2px_rgba(0,0,0,0.06)]'
                  : 'text-[var(--color-text-primary)]',
              )}
            >
              分析
            </button>
            <button
              onClick={() => onModeChange('trading')}
              className={cn(
                'flex-1 rounded-[5px] py-1.5 text-sm font-medium transition-all duration-150',
                mode === 'trading'
                  ? 'bg-[var(--color-bg-surface)] text-[var(--color-text-primary)] shadow-[0_1px_2px_rgba(0,0,0,0.06)]'
                  : 'text-[var(--color-text-primary)]',
              )}
            >
              操盘
            </button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-1 py-2 shrink-0">
          <button
            onClick={() => onModeChange('analysis')}
            className={cn(
              'flex h-9 w-9 items-center justify-center rounded-md text-base transition-colors',
              mode === 'analysis'
                ? 'bg-[var(--color-bg-sidebar-active)]'
                : 'text-[var(--color-text-tertiary)] hover:bg-[var(--color-bg-sidebar-hover)]',
            )}
            title="分析模式"
          >
            📊
          </button>
          <button
            onClick={() => onModeChange('trading')}
            className={cn(
              'flex h-9 w-9 items-center justify-center rounded-md text-base transition-colors',
              mode === 'trading'
                ? 'bg-[var(--color-bg-sidebar-active)]'
                : 'text-[var(--color-text-tertiary)] hover:bg-[var(--color-bg-sidebar-hover)]',
            )}
            title="操盘模式"
          >
            📈
          </button>
        </div>
      )}

      {/* 内容区域 */}
      {expanded ? (
        <div className="flex flex-col flex-1 min-h-0 overflow-hidden">
          {mode === 'analysis' && (
            <>
              {/* 新建会话按钮 */}
              <button
                onClick={onNewConversation}
                className="mx-2 mb-1 flex h-8 items-center gap-1.5 rounded-md px-2 text-sm text-[var(--color-text-primary)] hover:bg-[var(--color-bg-sidebar-hover)] shrink-0 transition-colors"
              >
                <Plus className="h-3.5 w-3.5" />
                新建会话
              </button>

              {/* 分组对话列表 */}
              <div className="flex-1 overflow-y-auto scrollbar-hide px-2">
                {conversations.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full text-sm text-[var(--color-text-primary)] px-4">
                    <Search className="h-6 w-6 mb-2 opacity-40" />
                    <p>暂无对话</p>
                    <p className="mt-1">点击上方按钮开始</p>
                  </div>
                ) : (
                  <div className="flex flex-col">
                    {groups.map(([group, items]) => (
                      <div key={group}>
                        <GroupLabel group={group} />
                        <div className="flex flex-col gap-0.5">
                          {items.map((conv) => (
                            <div
                              key={conv.id}
                              onMouseEnter={() => setHoveredId(conv.id)}
                              onMouseLeave={() => setHoveredId(null)}
                              onClick={() => onSelectConversation(conv.id)}
                              className={cn(
                                'group relative flex h-9 cursor-pointer items-center rounded-md px-2 text-sm transition-colors',
                                selectedId === conv.id
                                  ? 'bg-[var(--color-bg-sidebar-active)] font-medium text-[var(--color-text-primary)]'
                                  : 'text-[var(--color-text-primary)] hover:bg-[var(--color-bg-sidebar-hover)]',
                              )}
                            >
                              <span className="flex-1 truncate">{conv.title}</span>

                              <span className="ml-2 text-sm text-[var(--color-text-tertiary)] shrink-0">
                                {formatConversationTime(conv.updatedAt)}
                              </span>

                              {/* Hover actions */}
                              {hoveredId === conv.id && (
                                <div className="absolute right-1 flex items-center gap-0.5 bg-[var(--color-bg-sidebar)] pl-1">
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation()
                                      onArchiveConversation(conv.id)
                                    }}
                                    className="flex h-5 w-5 items-center justify-center rounded text-[var(--color-text-tertiary)] hover:bg-[var(--color-bg-sidebar-hover)] hover:text-[var(--color-text-secondary)]"
                                    title="归档会话"
                                  >
                                    <Archive className="h-3 w-3" />
                                  </button>
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation()
                                      if (window.confirm(`确定删除会话「${conv.title}」？此操作不可恢复。`)) {
                                        onDeleteConversation(conv.id)
                                      }
                                    }}
                                    className="flex h-5 w-5 items-center justify-center rounded text-[var(--color-text-tertiary)] hover:bg-[var(--color-bg-sidebar-hover)] hover:text-[var(--color-down)]"
                                    title="删除会话"
                                  >
                                    <Trash2 className="h-3 w-3" />
                                  </button>
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}

          {mode === 'trading' && (
            <div className="flex-1 min-h-0 overflow-hidden">
              <WatchlistPanel />
            </div>
          )}
        </div>
      ) : (
        /* 窄条：仅保留新建会话快捷入口 */
        <div className="flex flex-col items-center pt-2">
          {mode === 'analysis' && (
            <button
              onClick={() => {
                setCollapsed(false)
                onNewConversation()
              }}
              className="flex h-9 w-9 items-center justify-center rounded-md text-[var(--color-text-tertiary)] hover:bg-[var(--color-bg-sidebar-hover)] hover:text-[var(--color-text-secondary)] transition-colors"
              title="新建会话"
            >
              <Plus className="h-4 w-4" />
            </button>
          )}
        </div>
      )}

      {/* 设置栏（窄条时为图标） */}
      {expanded ? (
        <button
          onClick={() => onOpenSettings?.()}
          className="flex h-9 items-center gap-2 border-t border-[var(--color-border-light)] px-4 text-sm text-[var(--color-text-primary)] hover:bg-[var(--color-bg-sidebar-hover)] shrink-0 transition-colors"
        >
          <Settings className="h-3.5 w-3.5" />
          设置
        </button>
      ) : (
        <button
          onClick={() => onOpenSettings?.()}
          className="flex h-9 items-center justify-center border-t border-[var(--color-border-light)] text-[var(--color-text-tertiary)] hover:bg-[var(--color-bg-sidebar-hover)] hover:text-[var(--color-text-secondary)] shrink-0 transition-colors"
          title="设置"
        >
          <Settings className="h-3.5 w-3.5" />
        </button>
      )}
    </aside>
  )
}
