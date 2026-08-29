export function formatConversationTime(updatedAt: string): string {
  const date = new Date(updatedAt)
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today.getTime() - 86400000)
  const target = new Date(date.getFullYear(), date.getMonth(), date.getDate())

  if (target.getTime() === today.getTime()) {
    // 今天：显示 HH:MM
    return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
  }

  if (target.getTime() === yesterday.getTime()) {
    return '昨天'
  }

  // 更早：显示 MM/DD
  return `${date.getMonth() + 1}/${date.getDate()}`
}

export type ConversationGroup = '今天' | '昨天' | '更早'

export interface GroupedConversation {
  group: ConversationGroup
  updatedAt: string
}

export function getConversationGroup(updatedAt: string): ConversationGroup {
  const date = new Date(updatedAt)
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today.getTime() - 86400000)
  const target = new Date(date.getFullYear(), date.getMonth(), date.getDate())

  if (target.getTime() === today.getTime()) return '今天'
  if (target.getTime() === yesterday.getTime()) return '昨天'
  return '更早'
}

const GROUP_ORDER: Record<ConversationGroup, number> = {
  '今天': 0,
  '昨天': 1,
  '更早': 2,
}

export function groupConversations<T extends { updatedAt: string }>(
  conversations: T[],
): [ConversationGroup, T[]][] {
  const groups = new Map<ConversationGroup, T[]>()

  for (const conv of conversations) {
    const group = getConversationGroup(conv.updatedAt)
    if (!groups.has(group)) groups.set(group, [])
    groups.get(group)!.push(conv)
  }

  return Array.from(groups.entries())
    .sort(([a], [b]) => GROUP_ORDER[a] - GROUP_ORDER[b])
}
