import { Component, useState, useEffect, useMemo, useCallback, useRef } from 'react'
import type { ReactNode } from 'react'
import { AppLayout } from '@/components/layout/AppLayout'
import { useChatApi } from '@/hooks/useChatApi'
import { useChatStream } from '@/hooks/useChatStream'
import { useStyleProfile, type RadarProfile } from '@/hooks/useStyleProfile'
import { usePreferences, type PreferencesData } from '@/hooks/usePreferences'
import { StyleQuizModal } from '@/components/style/StyleQuizModal'
import { SettingsDialog } from '@/components/settings/SettingsDialog'
import type { AppMode, ChatMessage, Citation, Conversation, Decision, DecisionCardData, MainTab, SourceTab, StreamDisplay } from '@/types'
import { CARD_PROMPTS, type CardType } from '@/lib/cardPrompts'

export default function App() {
  const { createConversation, listConversations, getMessages, archiveConversation, deleteConversation } = useChatApi()
  const { fetchProfile } = useStyleProfile()
  const { fetchPreferences } = usePreferences()
  const {
    sendStream,
    cancelStream,
    resetStream,
    resume,
    streamText,
    thinkingText,
    citations,
    subagentCards,
    todos,
    isStreaming,
    isInterrupted,
    interruptData,
    isResuming,
    contextTokens,
  } = useChatStream()
  const [mode, setMode] = useState<AppMode>('analysis')
  const [activeTab, setActiveTab] = useState<MainTab>('technical')
  const [symbol, setSymbol] = useState<string>('600519')
  // 右侧卡片开关（两模式统一，默认开启）
  const [panelOpen, setPanelOpen] = useState(true)
  // 待发送到右侧对话的预设提示词（卡片「AI 分析」触发）
  const [panelPrompt, setPanelPrompt] = useState<string | null>(null)
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  /** 程序性选中会话（发送流程自动建会话）时跳过 cancelStream/resetStream，避免中止刚发出的流 */
  const skipStreamResetRef = useRef(false)
  // 投资画像（右侧栏模块 + 左下角气泡）
  const [profile, setProfile] = useState<RadarProfile | null>(null)
  const [profileLoading, setProfileLoading] = useState(true)
  const [preferences, setPreferences] = useState<PreferencesData | null>(null)
  const [quizOpen, setQuizOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  // 来源内嵌 Tab（分析模式右侧栏：点击信息来源后新建，iframe 展示原文）
  const [sourceTabs, setSourceTabs] = useState<SourceTab[]>([])
  const [activeSourceId, setActiveSourceId] = useState<string | null>(null)

  /** 点击信息来源 → 打开右侧面板并新建/激活内嵌 tab */
  const handleOpenSource = useCallback((citation: Citation) => {
    if (!citation.url) return
    const id = citation.url
    setPanelOpen(true)
    setSourceTabs((prev) => {
      if (prev.some((t) => t.id === id)) return prev
      return [
        ...prev,
        {
          id,
          title: citation.title || id,
          url: citation.url as string,
          source: citation.source,
        },
      ]
    })
    setActiveSourceId(id)
  }, [])

  const handleSelectSourceTab = useCallback((id: string) => {
    setActiveSourceId(id)
  }, [])

  const handleCloseSourceTab = useCallback((id: string) => {
    setSourceTabs((prev) => {
      const next = prev.filter((t) => t.id !== id)
      // 关闭的是激活来源 → 回退到最后一个剩余来源（AppLayout 内另处理回退摘要）
      if (activeSourceId === id) {
        const last = next[next.length - 1]
        setActiveSourceId(last ? last.id : null)
      }
      return next
    })
  }, [activeSourceId])

  // 快捷键：Cmd/Ctrl + 1/2 切换分析 / 操盘模式
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (!e.metaKey && !e.ctrlKey) return
      if (e.key === '1') {
        e.preventDefault()
        setMode('analysis')
      } else if (e.key === '2') {
        e.preventDefault()
        setMode('trading')
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  // 初始加载会话列表（仅主控台 analysis 会话，右侧对话 panel 独立管理）
  useEffect(() => {
    listConversations({ kind: 'analysis' })
      .then(setConversations)
      .catch(() => {})
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // 加载投资画像（右侧栏模块 + 气泡状态）
  useEffect(() => {
    let cancelled = false
    fetchProfile()
      .then((p) => {
        if (!cancelled) setProfile(p)
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setProfileLoading(false)
      })
    fetchPreferences()
      .then((d) => {
        if (!cancelled) setPreferences(d)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [fetchProfile, fetchPreferences])

  // 问卷提交成功 → 刷新画像（右侧栏 + 气泡变已生成）
  const handleQuizCompleted = useCallback(() => {
    setQuizOpen(false)
    setProfileLoading(true)
    fetchProfile()
      .then((p) => {
        if (p) setProfile(p)
      })
      .catch(() => {})
      .finally(() => setProfileLoading(false))
    fetchPreferences()
      .then((d) => {
        if (d) setPreferences(d)
      })
      .catch(() => {})
  }, [fetchProfile, fetchPreferences])

  // 切换选中会话时加载消息（并取消/清空上一轮流式状态）
  useEffect(() => {
    // 发送流程程序性选中（自动建会话）：跳过取消/重置/拉取，流结束后统一刷新
    if (skipStreamResetRef.current) {
      skipStreamResetRef.current = false
      return
    }
    cancelStream()
    resetStream()
    if (!selectedId) {
      setMessages([])
      return
    }
    getMessages(selectedId)
      .then(setMessages)
      .catch(() => setMessages([]))
  }, [selectedId]) // eslint-disable-line react-hooks/exhaustive-deps

  // 从消息中提取最近一条 composite_decision 的 card_data（附带消息时间戳供目标价卡标注预测节点）
  const latestCardData = useMemo<DecisionCardData | null>(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i]
      if (m.content_type === 'composite_decision' && m.card_data) {
        const card = m.card_data as DecisionCardData
        if (m.createdAt && !card['_analyzed_at']) card['_analyzed_at'] = m.createdAt
        return card
      }
    }
    return null
  }, [messages])

  // 流式展示状态（有内容或 HITL 中断时非 null）
  const streaming = useMemo<StreamDisplay | null>(() => {
    if (!isStreaming && !streamText && !thinkingText && subagentCards.length === 0 && !isInterrupted && todos.length === 0) return null
    return {
      text: streamText,
      thinkingText,
      citations,
      subagentCards,
      todos,
      isStreaming,
      isInterrupted,
      interruptData,
      isResuming,
      contextTokens,
    }
  }, [streamText, thinkingText, citations, subagentCards, todos, isStreaming, isInterrupted, interruptData, isResuming, contextTokens])

  // 卡片「AI 分析」→ 打开右侧对话并发送预设提示词
  const handleAiAnalyze = useCallback(
    (cardType: CardType) => {
      const prompt = CARD_PROMPTS[cardType]?.(symbol) ?? ''
      if (!prompt) return
      setPanelOpen(true)
      setPanelPrompt(prompt)
    },
    [symbol],
  )

  // 右侧对话发送完成后清空待发提示词
  const handlePromptConsumed = useCallback(() => {
    setPanelPrompt(null)
  }, [])

  const handleNewConversation = () => {
    // 「新建对话」= 回到欢迎页（不创建会话）；欢迎页实际发消息时才自动建会话
    cancelStream()
    resetStream()
    setMessages([])
    setSelectedId(null)
  }

  /** 刷新主控台会话列表（发送/归档/删除后标题与排序同步） */
  const refreshConversations = useCallback(async () => {
    try {
      const list = await listConversations({ kind: 'analysis' })
      setConversations(list)
    } catch {
      // 刷新失败保留现有列表
    }
  }, [listConversations])

  const handleArchiveConversation = async (id: string) => {
    try {
      await archiveConversation(id)
      if (selectedId === id) {
        setSelectedId(null)
        setMessages([])
      }
      await refreshConversations()
    } catch {
      // silent
    }
  }

  const handleDeleteConversation = async (id: string) => {
    try {
      await deleteConversation(id)
      if (selectedId === id) {
        setSelectedId(null)
        setMessages([])
      }
      await refreshConversations()
    } catch {
      // silent
    }
  }

  const handleSendMessage = async (content: string) => {
    // 无会话时自动新建（欢迎页直接输入的场景）
    let convId = selectedId
    if (!convId) {
      try {
        const conv = await createConversation()
        setConversations((prev) => [conv, ...prev])
        // 程序性选中：标记跳过 useEffect[selectedId] 的 cancelStream/resetStream，
        // 避免中止刚发出的流式请求；消息在流结束后统一刷新
        skipStreamResetRef.current = true
        setSelectedId(conv.id)
        convId = conv.id
      } catch {
        return
      }
    }
    // 乐观插入用户消息（临时 id，流结束后刷新为真实消息）
    const tempUserMsg: ChatMessage = {
      id: `tmp-${Date.now()}`,
      conversationId: convId,
      role: 'user',
      content,
      sequence: 0,
      createdAt: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, tempUserMsg])

    // 流式发送；若以 HITL 中断结束则保留确认卡片，不做消息刷新
    const interrupted = await sendStream(convId, content)
    if (interrupted) return

    resetStream()
    try {
      const fresh = await getMessages(convId)
      setMessages(fresh)
    } catch {
      // 刷新失败则保留乐观消息与流式展示
    }
    // 首条消息后标题/时间戳更新，同步会话列表
    await refreshConversations()
  }

  // HITL resume：提交用户决策并续流；续流结束后刷新为后端落库消息
  const handleResume = async (decisions: Decision[]) => {
    if (!selectedId) return
    const stillInterrupted = await resume(decisions)
    if (stillInterrupted) return

    resetStream()
    try {
      const fresh = await getMessages(selectedId)
      setMessages(fresh)
    } catch {
      // 刷新失败则保留流式展示
    }
    await refreshConversations()
  }

  return (
    <ErrorBoundary>
      <AppLayout
        mode={mode}
        onModeChange={setMode}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        symbol={symbol}
        onSymbolChange={setSymbol}
        panelOpen={panelOpen}
        onPanelToggle={() => setPanelOpen((v) => !v)}
        panelPrompt={panelPrompt}
        onPromptConsumed={handlePromptConsumed}
        onAiAnalyze={handleAiAnalyze}
        conversations={conversations}
        selectedConversationId={selectedId}
        onSelectConversation={(id) => setSelectedId(id)}
        onNewConversation={handleNewConversation}
        onArchiveConversation={handleArchiveConversation}
        onDeleteConversation={handleDeleteConversation}
        messages={messages}
        streaming={streaming}
        onSendMessage={handleSendMessage}
        onResume={handleResume}
        latestCardData={latestCardData}
        profile={profile}
        profileLoading={profileLoading}
        onStartQuiz={() => { setProfile(null); setPreferences(null); setQuizOpen(true) }}
        onRetakeQuiz={() => { setProfile(null); setPreferences(null) }}
        preferences={preferences}
        sourceTabs={sourceTabs}
        activeSourceId={activeSourceId}
        onOpenSource={handleOpenSource}
        onSelectSourceTab={handleSelectSourceTab}
        onCloseSourceTab={handleCloseSourceTab}
        onOpenSettings={() => setSettingsOpen(true)}
      />
      {/* 冷启动问卷弹窗（30 题分页） */}
      <StyleQuizModal open={quizOpen} onClose={() => setQuizOpen(false)} onCompleted={handleQuizCompleted} />
      <SettingsDialog open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </ErrorBoundary>
  )
}

/** 渲染错误兜底：组件崩溃时展示错误信息而非白屏 */
class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex h-screen w-screen items-center justify-center bg-[var(--color-bg-base)]">
          <div className="max-w-md rounded-xl border border-[var(--color-border)] bg-white p-5">
            <p className="text-xl font-medium text-[var(--color-text-primary)]">页面渲染出错</p>
            <p className="mt-2 break-all text-base text-[var(--color-danger)]">{this.state.error.message}</p>
            <button
              onClick={() => this.setState({ error: null })}
              className="mt-4 rounded-md bg-[var(--color-accent)] px-3 py-1 text-xs text-white hover:bg-[var(--color-accent-hover)]"
            >
              重试
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
