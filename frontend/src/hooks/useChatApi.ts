import axios from 'axios'
import type { Conversation, ChatMessage } from '@/types'

/** Python 后端通用响应包装 */
interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

function mapConversation(raw: any): Conversation {
  return {
    id: String(raw.id),
    title: raw.title || '',
    createdAt: raw.created_at || '',
    updatedAt: raw.updated_at || '',
    tokenCount: raw.token_count,
    contextTokens: raw.context_tokens,
  }
}

function mapMessage(raw: any): ChatMessage {
  let cardData: Record<string, any> | undefined
  if (raw.card_data) {
    if (typeof raw.card_data === 'string') {
      try { cardData = JSON.parse(raw.card_data) } catch { cardData = undefined }
    } else {
      cardData = raw.card_data
    }
  }
  return {
    id: String(raw.id),
    conversationId: String(raw.conversation_id),
    role: raw.role || 'user',
    content: raw.content || '',
    content_type: raw.content_type || undefined,
    sequence: raw.sequence || 0,
    tokenCount: raw.token_count,
    card_data: cardData,
    createdAt: raw.created_at || '',
  }
}

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

export function useChatApi() {
  const createConversation = async (title?: string, kind?: string): Promise<Conversation> => {
    const res = await api.post<ApiResponse<any>>('/chat/conversation', { title, kind: kind || 'analysis' })
    return mapConversation(res.data.data)
  }

  const listConversations = async (params?: { status?: string; kind?: string }): Promise<Conversation[]> => {
    const res = await api.get<ApiResponse<any[]>>('/chat/conversation/list', { params })
    return (res.data.data || []).map(mapConversation)
  }

  const renameConversation = async (id: string, title: string): Promise<void> => {
    await api.put<ApiResponse<any>>(`/chat/conversation/${id}/title`, { title })
  }

  const getConversation = async (id: string): Promise<Conversation> => {
    const res = await api.get<ApiResponse<any>>(`/chat/conversation/${id}`)
    return mapConversation(res.data.data)
  }

  const archiveConversation = async (id: string): Promise<void> => {
    await api.put(`/chat/conversation/${id}/archive`)
  }

  const deleteConversation = async (id: string): Promise<void> => {
    await api.delete(`/chat/conversation/${id}`)
  }

  const getMessages = async (
    id: string,
    page = 1,
    pageSize = 50,
  ): Promise<ChatMessage[]> => {
    const res = await api.get<ApiResponse<{ items: any[] }>>(
      `/chat/conversation/${id}/message`,
      { params: { page, pageSize } },
    )
    return (res.data.data?.items || []).map(mapMessage)
  }

  const sendMessage = async (
    id: string,
    content: string,
    contentType = 'text',
  ): Promise<{ user_message: ChatMessage; assistant_message: ChatMessage }> => {
    const res = await api.post<ApiResponse<any>>(
      `/chat/conversation/${id}/message`,
      { content, content_type: contentType },
    )
    return {
      user_message: mapMessage(res.data.data.user_message),
      assistant_message: mapMessage(res.data.data.assistant_message),
    }
  }

  return {
    createConversation,
    listConversations,
    renameConversation,
    getConversation,
    archiveConversation,
    deleteConversation,
    getMessages,
    sendMessage,
  }
}
