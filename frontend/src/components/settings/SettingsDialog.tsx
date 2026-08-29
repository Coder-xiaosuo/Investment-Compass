import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Check, ChevronDown, Eye, EyeOff, Loader2, Save, X, AlertCircle, Bot, Bell, Sliders, Cpu, Wand2, MessageSquarePlus, RefreshCw } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useSettingsApi } from '@/hooks/useSettingsApi'
import type {
  SettingsView,
  SettingsPatch,
  ProviderSettingsPatch,
  FeishuSettingsPatch,
  PushplusSettingsPatch,
  TushareSettingsPatch,
  ReasoningEffort,
} from '@/types'

type SecretMode = 'show' | 'edit' | 'empty'
type TestStatus = false | 'ok' | 'fail' | 'loading'

interface FormDraft {
  provider: {
    apiKeyMode: SecretMode
    api_key: string
    model: string
    base_url: string
    thinking: boolean
    reasoning_effort: ReasoningEffort
  }
  feishu: {
    enabled: boolean
    webhookUrlMode: SecretMode
    webhook_url: string
    secretMode: SecretMode
    secret: string
    app_id: string
    appSecretMode: SecretMode
    app_secret: string
    notify_on_order_only: boolean
  }
  pushplus: {
    enabled: boolean
    tokenMode: SecretMode
    token: string
  }
  tushare: {
    tokenMode: SecretMode
    token: string
  }
  scheduler: {
    enabled: boolean
    market_sync_cron: string
    news_sync_cron: string
    timezone: string
  }
}

interface SettingsDialogProps {
  open: boolean
  onClose: () => void
}

const TABS = [
  { id: 'model', label: '大模型', icon: <Bot className="h-4 w-4" /> },
  { id: 'notify', label: '通知渠道', icon: <Bell className="h-4 w-4" /> },
  { id: 'advanced', label: '高级设置', icon: <Sliders className="h-4 w-4" /> },
] as const

type TabId = (typeof TABS)[number]['id']

function createInitialDraft(): FormDraft {
  return {
    provider: {
      apiKeyMode: 'empty',
      api_key: '',
      model: 'deepseek-chat',
      base_url: 'https://api.deepseek.com',
      thinking: false,
      reasoning_effort: 'medium',
    },
    feishu: {
      enabled: false,
      webhookUrlMode: 'empty',
      webhook_url: '',
      secretMode: 'empty',
      secret: '',
      app_id: '',
      appSecretMode: 'empty',
      app_secret: '',
      notify_on_order_only: true,
    },
    pushplus: {
      enabled: false,
      tokenMode: 'empty',
      token: '',
    },
    tushare: {
      tokenMode: 'empty',
      token: '',
    },
    scheduler: {
      enabled: false,
      market_sync_cron: '0 9 * * 1-5',
      news_sync_cron: '0 10 * * 1-5',
      timezone: 'Asia/Shanghai',
    },
  }
}

function viewToDraft(view: SettingsView): FormDraft {
  const d = createInitialDraft()

  d.provider.apiKeyMode = view.provider.api_key_set ? 'show' : 'empty'
  d.provider.model = view.provider.model ?? 'deepseek-chat'
  d.provider.base_url = view.provider.base_url ?? 'https://api.deepseek.com'
  d.provider.thinking = view.provider.thinking ?? false
  d.provider.reasoning_effort = view.provider.reasoning_effort ?? 'medium'

  d.feishu.enabled = view.feishu.enabled ?? false
  d.feishu.webhookUrlMode = view.feishu.webhook_url_set ? 'show' : 'empty'
  d.feishu.secretMode = view.feishu.secret_set ? 'show' : 'empty'
  d.feishu.app_id = view.feishu.app_id ?? ''
  d.feishu.appSecretMode = view.feishu.app_secret_set ? 'show' : 'empty'
  d.feishu.notify_on_order_only = view.feishu.notify_on_order_only ?? true

  d.pushplus.enabled = view.pushplus.enabled ?? false
  d.pushplus.tokenMode = view.pushplus.token_set ? 'show' : 'empty'

  d.tushare.tokenMode = view.tushare.token_set ? 'show' : 'empty'

  d.scheduler.enabled = view.scheduler.enabled ?? false
  d.scheduler.market_sync_cron = view.scheduler.market_sync_cron ?? '0 9 * * 1-5'
  d.scheduler.news_sync_cron = view.scheduler.news_sync_cron ?? '0 10 * * 1-5'
  d.scheduler.timezone = view.scheduler.timezone ?? 'Asia/Shanghai'

  return d
}

function isDirty(draft: FormDraft, view: SettingsView | null): boolean {
  if (!view) return false

  if (draft.provider.apiKeyMode === 'edit' && draft.provider.api_key !== '') return true
  if (draft.provider.apiKeyMode === 'empty' && view.provider.api_key_set) return true
  if (draft.provider.model !== (view.provider.model ?? 'deepseek-chat')) return true
  if (draft.provider.base_url !== (view.provider.base_url ?? 'https://api.deepseek.com')) return true
  if (draft.provider.thinking !== (view.provider.thinking ?? false)) return true
  if (draft.provider.reasoning_effort !== (view.provider.reasoning_effort ?? 'medium')) return true

  if (draft.feishu.enabled !== (view.feishu.enabled ?? false)) return true
  if (draft.feishu.webhookUrlMode === 'edit' && draft.feishu.webhook_url !== '') return true
  if (draft.feishu.webhookUrlMode === 'empty' && view.feishu.webhook_url_set) return true
  if (draft.feishu.secretMode === 'edit' && draft.feishu.secret !== '') return true
  if (draft.feishu.secretMode === 'empty' && view.feishu.secret_set) return true
  if (draft.feishu.app_id !== (view.feishu.app_id ?? '')) return true
  if (draft.feishu.appSecretMode === 'edit' && draft.feishu.app_secret !== '') return true
  if (draft.feishu.appSecretMode === 'empty' && view.feishu.app_secret_set) return true
  if (draft.feishu.notify_on_order_only !== (view.feishu.notify_on_order_only ?? true)) return true

  if (draft.pushplus.enabled !== (view.pushplus.enabled ?? false)) return true
  if (draft.pushplus.tokenMode === 'edit' && draft.pushplus.token !== '') return true
  if (draft.pushplus.tokenMode === 'empty' && view.pushplus.token_set) return true

  if (draft.tushare.tokenMode === 'edit' && draft.tushare.token !== '') return true
  if (draft.tushare.tokenMode === 'empty' && view.tushare.token_set) return true

  if (draft.scheduler.enabled !== (view.scheduler.enabled ?? false)) return true
  if (draft.scheduler.market_sync_cron !== (view.scheduler.market_sync_cron ?? '0 9 * * 1-5')) return true
  if (draft.scheduler.news_sync_cron !== (view.scheduler.news_sync_cron ?? '0 10 * * 1-5')) return true
  if (draft.scheduler.timezone !== (view.scheduler.timezone ?? 'Asia/Shanghai')) return true

  return false
}

function buildPatch(draft: FormDraft, view: SettingsView | null): SettingsPatch {
  const patch: SettingsPatch = {}

  const providerPatch: ProviderSettingsPatch = {}
  if (draft.provider.apiKeyMode === 'empty') {
    providerPatch.api_key = ''
  } else if (draft.provider.apiKeyMode === 'edit' && draft.provider.api_key !== '') {
    providerPatch.api_key = draft.provider.api_key
  }
  if (draft.provider.model !== (view?.provider.model ?? 'deepseek-chat')) {
    providerPatch.model = draft.provider.model
  }
  if (draft.provider.base_url !== (view?.provider.base_url ?? 'https://api.deepseek.com')) {
    providerPatch.base_url = draft.provider.base_url
  }
  if (draft.provider.thinking !== (view?.provider.thinking ?? false)) {
    providerPatch.thinking = draft.provider.thinking
  }
  if (draft.provider.reasoning_effort !== (view?.provider.reasoning_effort ?? 'medium')) {
    providerPatch.reasoning_effort = draft.provider.reasoning_effort
  }
  if (Object.keys(providerPatch).length > 0) {
    patch.provider = providerPatch
  }

  const feishuPatch: FeishuSettingsPatch = {}
  if (draft.feishu.enabled !== (view?.feishu.enabled ?? false)) {
    feishuPatch.enabled = draft.feishu.enabled
  }
  if (draft.feishu.webhookUrlMode === 'empty') {
    feishuPatch.webhook_url = ''
  } else if (draft.feishu.webhookUrlMode === 'edit' && draft.feishu.webhook_url !== '') {
    feishuPatch.webhook_url = draft.feishu.webhook_url
  }
  if (draft.feishu.secretMode === 'empty') {
    feishuPatch.secret = ''
  } else if (draft.feishu.secretMode === 'edit' && draft.feishu.secret !== '') {
    feishuPatch.secret = draft.feishu.secret
  }
  if (draft.feishu.app_id !== (view?.feishu.app_id ?? '')) {
    feishuPatch.app_id = draft.feishu.app_id
  }
  if (draft.feishu.appSecretMode === 'empty') {
    feishuPatch.app_secret = ''
  } else if (draft.feishu.appSecretMode === 'edit' && draft.feishu.app_secret !== '') {
    feishuPatch.app_secret = draft.feishu.app_secret
  }
  if (draft.feishu.notify_on_order_only !== (view?.feishu.notify_on_order_only ?? true)) {
    feishuPatch.notify_on_order_only = draft.feishu.notify_on_order_only
  }
  if (Object.keys(feishuPatch).length > 0) {
    patch.feishu = feishuPatch
  }

  const pushplusPatch: PushplusSettingsPatch = {}
  if (draft.pushplus.enabled !== (view?.pushplus.enabled ?? false)) {
    pushplusPatch.enabled = draft.pushplus.enabled
  }
  if (draft.pushplus.tokenMode === 'empty') {
    pushplusPatch.token = ''
  } else if (draft.pushplus.tokenMode === 'edit' && draft.pushplus.token !== '') {
    pushplusPatch.token = draft.pushplus.token
  }
  if (Object.keys(pushplusPatch).length > 0) {
    patch.pushplus = pushplusPatch
  }

  const tusharePatch: TushareSettingsPatch = {}
  if (draft.tushare.tokenMode === 'empty') {
    tusharePatch.token = ''
  } else if (draft.tushare.tokenMode === 'edit' && draft.tushare.token !== '') {
    tusharePatch.token = draft.tushare.token
  }
  if (Object.keys(tusharePatch).length > 0) {
    patch.tushare = tusharePatch
  }

  const schedulerPatch = {
    enabled: draft.scheduler.enabled,
    market_sync_cron: draft.scheduler.market_sync_cron,
    news_sync_cron: draft.scheduler.news_sync_cron,
    timezone: draft.scheduler.timezone,
  }
  if (
    draft.scheduler.enabled !== (view?.scheduler.enabled ?? false) ||
    draft.scheduler.market_sync_cron !== (view?.scheduler.market_sync_cron ?? '0 9 * * 1-5') ||
    draft.scheduler.news_sync_cron !== (view?.scheduler.news_sync_cron ?? '0 10 * * 1-5') ||
    draft.scheduler.timezone !== (view?.scheduler.timezone ?? 'Asia/Shanghai')
  ) {
    patch.scheduler = schedulerPatch
  }

  return patch
}

interface SecretFieldProps {
  label: string
  placeholder: string
  mode: SecretMode
  value: string
  maskedValue?: string
  onModeChange: (mode: SecretMode) => void
  onValueChange: (value: string) => void
  onClear?: () => void
}

function SecretField({
  label,
  placeholder,
  mode,
  value,
  maskedValue,
  onModeChange,
  onValueChange,
  onClear,
}: SecretFieldProps) {
  const [showValue, setShowValue] = useState(false)

  if (mode === 'empty') {
    return (
      <div>
        <label className="mb-1.5 block text-xs font-medium text-[var(--color-text-secondary)]">{label}</label>
        <input
          type="password"
          placeholder={placeholder}
          value={value}
          onChange={(e) => onValueChange(e.target.value)}
          className="w-full rounded-lg border border-[var(--color-border)] bg-white px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-placeholder)] focus:border-[var(--color-accent)] focus:ring-2 focus:ring-[var(--color-accent-soft)]"
        />
      </div>
    )
  }

  if (mode === 'show') {
    return (
      <div>
        <label className="mb-1.5 block text-xs font-medium text-[var(--color-text-secondary)]">{label}</label>
        <div className="flex items-center gap-2 rounded-lg border border-[var(--color-border-light)] bg-[var(--color-bg-subtle)] px-3 py-2">
          <span className="text-sm text-[var(--color-text-secondary)]">
            已设置：<span className="font-mono text-[var(--color-text-primary)]">{maskedValue ?? '****'}</span>
          </span>
          <div className="ml-auto flex gap-1.5">
            <button
              type="button"
              onClick={() => {
                onValueChange('')
                onModeChange('edit')
              }}
              className="rounded-md px-2.5 py-1 text-xs font-medium text-[var(--color-accent)] hover:bg-[var(--color-accent-soft)] transition-colors"
            >
              重新设置
            </button>
            {onClear && (
              <button
                type="button"
                onClick={onClear}
                className="rounded-md px-2.5 py-1 text-xs font-medium text-[var(--color-danger)] hover:bg-red-50 transition-colors"
              >
                清空
              </button>
            )}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div>
      <label className="mb-1.5 block text-xs font-medium text-[var(--color-text-secondary)]">{label}</label>
      <div className="relative">
        <input
          type={showValue ? 'text' : 'password'}
          placeholder={placeholder}
          value={value}
          onChange={(e) => onValueChange(e.target.value)}
          className="w-full rounded-lg border border-[var(--color-border)] bg-white px-3 py-2 pr-10 text-sm text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-placeholder)] focus:border-[var(--color-accent)] focus:ring-2 focus:ring-[var(--color-accent-soft)]"
        />
        <button
          type="button"
          onClick={() => setShowValue((s) => !s)}
          className="absolute right-2 top-1/2 -translate-y-1/2 flex h-7 w-7 items-center justify-center rounded-md text-[var(--color-text-tertiary)] hover:bg-[var(--color-bg-hover)] transition-colors"
        >
          {showValue ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
    </div>
  )
}

export function SettingsDialog({ open, onClose }: SettingsDialogProps) {
  const { get, update, validateLlm, testNotification } = useSettingsApi()

  const [activeTab, setActiveTab] = useState<TabId>('model')
  const [draft, setDraft] = useState<FormDraft>(createInitialDraft())
  const [view, setView] = useState<SettingsView | null>(null)
  const [saving, setSaving] = useState(false)
  const [testingLlm, setTestingLlm] = useState<TestStatus>(false)
  const [llmResult, setLlmResult] = useState<{ ok: boolean; message: string; usage?: any; latency_ms?: number; model?: string } | null>(null)
  const [testingNotify, setTestingNotify] = useState<{
    feishu: TestStatus
    pushplus: TestStatus
  }>({ feishu: false, pushplus: false })
  const [notifyResult, setNotifyResult] = useState<{ feishu?: { ok: boolean; message: string }; pushplus?: { ok: boolean; message: string } }>({})
  const [toast, setToast] = useState<{ msg: string; type: 'success' | 'error' } | null>(null)
  const [loading, setLoading] = useState(false)

  const dirty = useMemo(() => isDirty(draft, view), [draft, view])

  const showToast = useCallback((msg: string, type: 'success' | 'error') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3000)
  }, [])

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const v = await get()
      setView(v)
      setDraft(viewToDraft(v))
      setTestingLlm(false)
      setLlmResult(null)
      setTestingNotify({ feishu: false, pushplus: false })
      setNotifyResult({})
    } catch (e: any) {
      showToast(e?.message || '加载配置失败', 'error')
    } finally {
      setLoading(false)
    }
  }, [get, showToast])

  useEffect(() => {
    if (!open) return
    refresh()
  }, [open, refresh])

  useEffect(() => {
    if (!open) return
    const h = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [open, onClose])

  const handleSave = async () => {
    if (!dirty || saving) return
    setSaving(true)
    try {
      const patch = buildPatch(draft, view)
      await update(patch)
      showToast('✅ 配置已更新', 'success')
      await refresh()
    } catch (e: any) {
      showToast('❌ 保存失败：' + (e?.message ?? '未知错误'), 'error')
    } finally {
      setSaving(false)
    }
  }

  const handleTestLlm = async () => {
    setTestingLlm('loading')
    setLlmResult(null)
    try {
      const api_key =
        draft.provider.apiKeyMode === 'show' ? undefined : draft.provider.api_key || undefined
      const res = await validateLlm({
        model: draft.provider.model,
        base_url: draft.provider.base_url,
        api_key,
        thinking: draft.provider.thinking,
        reasoning_effort: draft.provider.reasoning_effort,
      })
      setTestingLlm('ok')
      setLlmResult({
        ok: true,
        message: res.message,
        usage: res.usage,
        latency_ms: res.latency_ms,
        model: res.model,
      })
    } catch (e: any) {
      setTestingLlm('fail')
      setLlmResult({
        ok: false,
        message: e?.message || '连通性测试失败',
      })
    }
  }

  const handleTestFeishu = async () => {
    setTestingNotify((prev) => ({ ...prev, feishu: 'loading' }))
    setNotifyResult((prev) => ({ ...prev, feishu: undefined }))
    try {
      const webhook_url =
        draft.feishu.webhookUrlMode === 'show' ? undefined : draft.feishu.webhook_url || undefined
      const secret =
        draft.feishu.secretMode === 'show' ? undefined : draft.feishu.secret || undefined
      const res = await testNotification({
        type: 'feishu',
        params: { webhook_url, secret },
      })
      setTestingNotify((prev) => ({ ...prev, feishu: 'ok' }))
      setNotifyResult((prev) => ({ ...prev, feishu: { ok: true, message: res.message } }))
    } catch (e: any) {
      setTestingNotify((prev) => ({ ...prev, feishu: 'fail' }))
      setNotifyResult((prev) => ({
        ...prev,
        feishu: { ok: false, message: e?.message || '飞书测试失败' },
      }))
    }
  }

  const handleTestPushplus = async () => {
    setTestingNotify((prev) => ({ ...prev, pushplus: 'loading' }))
    setNotifyResult((prev) => ({ ...prev, pushplus: undefined }))
    try {
      const token =
        draft.pushplus.tokenMode === 'show' ? undefined : draft.pushplus.token || undefined
      const res = await testNotification({
        type: 'pushplus',
        params: { token },
      })
      setTestingNotify((prev) => ({ ...prev, pushplus: 'ok' }))
      setNotifyResult((prev) => ({ ...prev, pushplus: { ok: true, message: res.message } }))
    } catch (e: any) {
      setTestingNotify((prev) => ({ ...prev, pushplus: 'fail' }))
      setNotifyResult((prev) => ({
        ...prev,
        pushplus: { ok: false, message: e?.message || 'PushPlus 测试失败' },
      }))
    }
  }

  const updateDraft = useCallback(
    <K extends keyof FormDraft, F extends keyof FormDraft[K]>(
      section: K,
      field: F,
      value: FormDraft[K][F],
    ) => {
      setDraft((prev) => ({
        ...prev,
        [section]: {
          ...prev[section],
          [field]: value,
        },
      }))
    },
    [],
  )

  if (!open) return null

  return (
    <>
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4"
        onClick={onClose}
      >
        <div
          className="flex max-h-[88vh] w-full max-w-[640px] flex-col rounded-2xl bg-white shadow-2xl"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex h-14 items-center justify-between border-b border-[var(--color-border-light)] px-6">
            <h2 className="text-base font-semibold text-[var(--color-text-primary)]">系统设置</h2>
            <button
              onClick={onClose}
              className="flex h-8 w-8 items-center justify-center rounded-full text-[var(--color-text-tertiary)] hover:bg-[var(--color-bg-hover)] transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex h-12 items-center gap-1 border-b border-[var(--color-border-light)] px-6">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  'flex items-center gap-1.5 rounded-full px-4 py-1.5 text-sm font-medium transition-all',
                  activeTab === tab.id
                    ? 'bg-[var(--color-accent)] text-white shadow-sm'
                    : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)]',
                )}
              >
                {tab.icon}
                {tab.label}
              </button>
            ))}
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-5">
            {loading ? (
              <div className="flex flex-col items-center justify-center gap-2 py-16 text-[var(--color-text-tertiary)]">
                <Loader2 className="h-5 w-5 animate-spin text-[var(--color-accent)]" />
                <span className="text-sm">加载配置中…</span>
              </div>
            ) : activeTab === 'model' ? (
              <div className="space-y-5">
                <div className="rounded-xl border border-[var(--color-border-light)] bg-[var(--color-bg-subtle)] p-4">
                  <div className="mb-3 flex items-center gap-2">
                    <Cpu className="h-4 w-4 text-[var(--color-accent)]" />
                    <span className="text-sm font-medium text-[var(--color-text-primary)]">模型提供商</span>
                  </div>

                  <SecretField
                    label="API Key"
                    placeholder="请输入 DeepSeek API Key"
                    mode={draft.provider.apiKeyMode}
                    value={draft.provider.api_key}
                    maskedValue={view?.provider.api_key_masked}
                    onModeChange={(m) => updateDraft('provider', 'apiKeyMode', m)}
                    onValueChange={(v) => updateDraft('provider', 'api_key', v)}
                    onClear={() => {
                      updateDraft('provider', 'api_key', '')
                      updateDraft('provider', 'apiKeyMode', 'empty')
                    }}
                  />

                  <div className="mt-4">
                    <label className="mb-1.5 block text-xs font-medium text-[var(--color-text-secondary)]">
                      模型名称
                    </label>
                    <input
                      type="text"
                      value={draft.provider.model}
                      onChange={(e) => updateDraft('provider', 'model', e.target.value)}
                      placeholder="deepseek-chat"
                      className="w-full rounded-lg border border-[var(--color-border)] bg-white px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-placeholder)] focus:border-[var(--color-accent)] focus:ring-2 focus:ring-[var(--color-accent-soft)]"
                    />
                  </div>

                  <div className="mt-4">
                    <label className="mb-1.5 block text-xs font-medium text-[var(--color-text-secondary)]">
                      Base URL
                    </label>
                    <input
                      type="text"
                      value={draft.provider.base_url}
                      onChange={(e) => updateDraft('provider', 'base_url', e.target.value)}
                      placeholder="https://api.deepseek.com"
                      className="w-full rounded-lg border border-[var(--color-border)] bg-white px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-placeholder)] focus:border-[var(--color-accent)] focus:ring-2 focus:ring-[var(--color-accent-soft)]"
                    />
                  </div>

                  <div className="mt-4 flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="thinking"
                      checked={draft.provider.thinking}
                      onChange={(e) => updateDraft('provider', 'thinking', e.target.checked)}
                      className="h-4 w-4 rounded border-[var(--color-border)] text-[var(--color-accent)] focus:ring-[var(--color-accent)]"
                    />
                    <label htmlFor="thinking" className="text-sm text-[var(--color-text-primary)] cursor-pointer">
                      开启思考模式
                    </label>
                  </div>

                  <div
                    className={cn(
                      'mt-4 transition-all',
                      !draft.provider.thinking && 'opacity-60 grayscale',
                    )}
                  >
                    <label className="mb-1.5 block text-xs font-medium text-[var(--color-text-secondary)]">
                      思考深度
                    </label>
                    <select
                      disabled={!draft.provider.thinking}
                      value={draft.provider.reasoning_effort}
                      onChange={(e) => updateDraft('provider', 'reasoning_effort', e.target.value as ReasoningEffort)}
                      className="w-full rounded-lg border border-[var(--color-border)] bg-white px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none focus:border-[var(--color-accent)] focus:ring-2 focus:ring-[var(--color-accent-soft)] disabled:cursor-not-allowed"
                    >
                      <option value="low">low（经济模式）</option>
                      <option value="medium">medium（平衡模式）</option>
                      <option value="high">high（深度模式）</option>
                    </select>
                  </div>
                </div>

                <div>
                  <button
                    type="button"
                    onClick={handleTestLlm}
                    disabled={testingLlm === 'loading'}
                    className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-white px-4 py-2 text-sm font-medium text-[var(--color-text-primary)] hover:bg-[var(--color-bg-hover)] disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
                  >
                    {testingLlm === 'loading' ? (
                      <Loader2 className="h-4 w-4 animate-spin text-[var(--color-accent)]" />
                    ) : (
                      <Wand2 className="h-4 w-4 text-[var(--color-accent)]" />
                    )}
                    {testingLlm === 'loading' ? '测试中…' : '测试连通性'}
                  </button>

                  {testingLlm !== false && testingLlm !== 'loading' && llmResult && (
                    <div
                      className={cn(
                        'mt-3 rounded-lg border px-4 py-3 text-sm',
                        testingLlm === 'ok'
                          ? 'border-green-200 bg-green-50 text-green-700'
                          : 'border-red-200 bg-red-50 text-red-700',
                      )}
                    >
                      {testingLlm === 'ok' ? (
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <Check className="h-4 w-4" />
                            <span className="font-medium">连通成功</span>
                          </div>
                          <div className="ml-6 text-xs text-green-600 space-y-0.5">
                            <div>模型：{llmResult.model}</div>
                            <div>延迟：{llmResult.latency_ms}ms</div>
                            <div>Token 用量：{llmResult.usage?.total_tokens ?? '-'}</div>
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-start gap-2">
                          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                          <div>
                            <div className="font-medium">连通失败</div>
                            <div className="text-xs text-red-600 mt-0.5">{llmResult.message}</div>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ) : activeTab === 'notify' ? (
              <div className="space-y-5">
                <div className="rounded-xl border border-[var(--color-border-light)] bg-[var(--color-bg-subtle)] p-4">
                  <div className="mb-3 flex items-center gap-2">
                    <MessageSquarePlus className="h-4 w-4 text-[var(--color-accent)]" />
                    <span className="text-sm font-medium text-[var(--color-text-primary)]">飞书 Webhook</span>
                  </div>

                  <div className="mb-4 flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="feishu-enabled"
                      checked={draft.feishu.enabled}
                      onChange={(e) => updateDraft('feishu', 'enabled', e.target.checked)}
                      className="h-4 w-4 rounded border-[var(--color-border)] text-[var(--color-accent)] focus:ring-[var(--color-accent)]"
                    />
                    <label htmlFor="feishu-enabled" className="text-sm text-[var(--color-text-primary)] cursor-pointer">
                      启用飞书通知
                    </label>
                  </div>

                  <SecretField
                    label="Webhook URL"
                    placeholder="请输入飞书自定义机器人 Webhook"
                    mode={draft.feishu.webhookUrlMode}
                    value={draft.feishu.webhook_url}
                    maskedValue={view?.feishu.webhook_url_masked}
                    onModeChange={(m) => updateDraft('feishu', 'webhookUrlMode', m)}
                    onValueChange={(v) => updateDraft('feishu', 'webhook_url', v)}
                    onClear={() => {
                      updateDraft('feishu', 'webhook_url', '')
                      updateDraft('feishu', 'webhookUrlMode', 'empty')
                    }}
                  />

                  <div className="mt-4">
                    <SecretField
                      label="签名校验 Secret"
                      placeholder="请输入签名校验密钥（可选）"
                      mode={draft.feishu.secretMode}
                      value={draft.feishu.secret}
                      maskedValue={view?.feishu.secret_masked}
                      onModeChange={(m) => updateDraft('feishu', 'secretMode', m)}
                      onValueChange={(v) => updateDraft('feishu', 'secret', v)}
                      onClear={() => {
                        updateDraft('feishu', 'secret', '')
                        updateDraft('feishu', 'secretMode', 'empty')
                      }}
                    />
                  </div>

                  <div className="mt-4">
                    <label className="mb-1.5 block text-xs font-medium text-[var(--color-text-secondary)]">
                      飞书应用 App ID
                    </label>
                    <input
                      type="text"
                      value={draft.feishu.app_id}
                      onChange={(e) => updateDraft('feishu', 'app_id', e.target.value)}
                      placeholder="cli_xxxxxx"
                      className="w-full rounded-lg border border-[var(--color-border)] bg-white px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-placeholder)] focus:border-[var(--color-accent)] focus:ring-2 focus:ring-[var(--color-accent-soft)]"
                    />
                  </div>

                  <div className="mt-4">
                    <SecretField
                      label="飞书应用 App Secret"
                      placeholder="请输入 App Secret"
                      mode={draft.feishu.appSecretMode}
                      value={draft.feishu.app_secret}
                      maskedValue={view?.feishu.app_secret_masked}
                      onModeChange={(m) => updateDraft('feishu', 'appSecretMode', m)}
                      onValueChange={(v) => updateDraft('feishu', 'app_secret', v)}
                      onClear={() => {
                        updateDraft('feishu', 'app_secret', '')
                        updateDraft('feishu', 'appSecretMode', 'empty')
                      }}
                    />
                  </div>

                  <div className="mt-4 flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="notify-order-only"
                      checked={draft.feishu.notify_on_order_only}
                      onChange={(e) => updateDraft('feishu', 'notify_on_order_only', e.target.checked)}
                      className="h-4 w-4 rounded border-[var(--color-border)] text-[var(--color-accent)] focus:ring-[var(--color-accent)]"
                    />
                    <label htmlFor="notify-order-only" className="text-sm text-[var(--color-text-primary)] cursor-pointer">
                      仅在交易信号时通知
                    </label>
                  </div>

                  <div className="mt-4">
                    <button
                      type="button"
                      onClick={handleTestFeishu}
                      disabled={testingNotify.feishu === 'loading'}
                      className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-white px-4 py-2 text-sm font-medium text-[var(--color-text-primary)] hover:bg-[var(--color-bg-hover)] disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
                    >
                      {testingNotify.feishu === 'loading' ? (
                        <Loader2 className="h-4 w-4 animate-spin text-[var(--color-accent)]" />
                      ) : (
                        <RefreshCw className="h-4 w-4 text-[var(--color-accent)]" />
                      )}
                      {testingNotify.feishu === 'loading' ? '测试中…' : '测试飞书'}
                    </button>
                    {testingNotify.feishu !== false && testingNotify.feishu !== 'loading' && notifyResult.feishu && (
                      <div
                        className={cn(
                          'mt-2 rounded-lg border px-3 py-2 text-xs',
                          testingNotify.feishu === 'ok'
                            ? 'border-green-200 bg-green-50 text-green-700'
                            : 'border-red-200 bg-red-50 text-red-700',
                        )}
                      >
                        {testingNotify.feishu === 'ok' ? (
                          <div className="flex items-center gap-1.5">
                            <Check className="h-3.5 w-3.5" />
                            <span>{notifyResult.feishu.message}</span>
                          </div>
                        ) : (
                          <div className="flex items-start gap-1.5">
                            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                            <span>{notifyResult.feishu.message}</span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                <div className="rounded-xl border border-[var(--color-border-light)] bg-[var(--color-bg-subtle)] p-4">
                  <div className="mb-3 flex items-center gap-2">
                    <Bell className="h-4 w-4 text-[var(--color-accent)]" />
                    <span className="text-sm font-medium text-[var(--color-text-primary)]">PushPlus</span>
                  </div>

                  <div className="mb-4 flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="pushplus-enabled"
                      checked={draft.pushplus.enabled}
                      onChange={(e) => updateDraft('pushplus', 'enabled', e.target.checked)}
                      className="h-4 w-4 rounded border-[var(--color-border)] text-[var(--color-accent)] focus:ring-[var(--color-accent)]"
                    />
                    <label htmlFor="pushplus-enabled" className="text-sm text-[var(--color-text-primary)] cursor-pointer">
                      启用 PushPlus 通知
                    </label>
                  </div>

                  <SecretField
                    label="PushPlus Token"
                    placeholder="请输入 PushPlus Token"
                    mode={draft.pushplus.tokenMode}
                    value={draft.pushplus.token}
                    maskedValue={view?.pushplus.token_masked}
                    onModeChange={(m) => updateDraft('pushplus', 'tokenMode', m)}
                    onValueChange={(v) => updateDraft('pushplus', 'token', v)}
                    onClear={() => {
                      updateDraft('pushplus', 'token', '')
                      updateDraft('pushplus', 'tokenMode', 'empty')
                    }}
                  />

                  <div className="mt-4">
                    <button
                      type="button"
                      onClick={handleTestPushplus}
                      disabled={testingNotify.pushplus === 'loading'}
                      className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-white px-4 py-2 text-sm font-medium text-[var(--color-text-primary)] hover:bg-[var(--color-bg-hover)] disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
                    >
                      {testingNotify.pushplus === 'loading' ? (
                        <Loader2 className="h-4 w-4 animate-spin text-[var(--color-accent)]" />
                      ) : (
                        <RefreshCw className="h-4 w-4 text-[var(--color-accent)]" />
                      )}
                      {testingNotify.pushplus === 'loading' ? '测试中…' : '测试 PushPlus'}
                    </button>
                    {testingNotify.pushplus !== false && testingNotify.pushplus !== 'loading' && notifyResult.pushplus && (
                      <div
                        className={cn(
                          'mt-2 rounded-lg border px-3 py-2 text-xs',
                          testingNotify.pushplus === 'ok'
                            ? 'border-green-200 bg-green-50 text-green-700'
                            : 'border-red-200 bg-red-50 text-red-700',
                        )}
                      >
                        {testingNotify.pushplus === 'ok' ? (
                          <div className="flex items-center gap-1.5">
                            <Check className="h-3.5 w-3.5" />
                            <span>{notifyResult.pushplus.message}</span>
                          </div>
                        ) : (
                          <div className="flex items-start gap-1.5">
                            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                            <span>{notifyResult.pushplus.message}</span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <div className="space-y-5">
                <div className="rounded-xl border border-[var(--color-border-light)] bg-[var(--color-bg-subtle)] p-4">
                  <div className="mb-3 flex items-center gap-2">
                    <Sliders className="h-4 w-4 text-[var(--color-accent)]" />
                    <span className="text-sm font-medium text-[var(--color-text-primary)]">Tushare 数据源</span>
                  </div>

                  <SecretField
                    label="Tushare Token"
                    placeholder="请输入 Tushare Token"
                    mode={draft.tushare.tokenMode}
                    value={draft.tushare.token}
                    maskedValue={view?.tushare.token_masked}
                    onModeChange={(m) => updateDraft('tushare', 'tokenMode', m)}
                    onValueChange={(v) => updateDraft('tushare', 'token', v)}
                    onClear={() => {
                      updateDraft('tushare', 'token', '')
                      updateDraft('tushare', 'tokenMode', 'empty')
                    }}
                  />
                </div>

                <div className="rounded-xl border border-[var(--color-border-light)] bg-[var(--color-bg-subtle)] p-4">
                  <div className="mb-3 flex items-center gap-2">
                    <RefreshCw className="h-4 w-4 text-[var(--color-accent)]" />
                    <span className="text-sm font-medium text-[var(--color-text-primary)]">定时任务 Scheduler</span>
                  </div>

                  <div className="mb-4 flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="scheduler-enabled"
                      checked={draft.scheduler.enabled}
                      onChange={(e) => updateDraft('scheduler', 'enabled', e.target.checked)}
                      className="h-4 w-4 rounded border-[var(--color-border)] text-[var(--color-accent)] focus:ring-[var(--color-accent)]"
                    />
                    <label htmlFor="scheduler-enabled" className="text-sm text-[var(--color-text-primary)] cursor-pointer">
                      启用定时任务
                    </label>
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-[var(--color-text-secondary)]">
                      市场数据同步 Cron
                    </label>
                    <input
                      type="text"
                      value={draft.scheduler.market_sync_cron}
                      onChange={(e) => updateDraft('scheduler', 'market_sync_cron', e.target.value)}
                      placeholder="0 9 * * 1-5"
                      className="w-full rounded-lg border border-[var(--color-border)] bg-white px-3 py-2 text-sm font-mono text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-placeholder)] focus:border-[var(--color-accent)] focus:ring-2 focus:ring-[var(--color-accent-soft)]"
                    />
                  </div>

                  <div className="mt-4">
                    <label className="mb-1.5 block text-xs font-medium text-[var(--color-text-secondary)]">
                      新闻资讯同步 Cron
                    </label>
                    <input
                      type="text"
                      value={draft.scheduler.news_sync_cron}
                      onChange={(e) => updateDraft('scheduler', 'news_sync_cron', e.target.value)}
                      placeholder="0 10 * * 1-5"
                      className="w-full rounded-lg border border-[var(--color-border)] bg-white px-3 py-2 text-sm font-mono text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-placeholder)] focus:border-[var(--color-accent)] focus:ring-2 focus:ring-[var(--color-accent-soft)]"
                    />
                  </div>

                  <div className="mt-4">
                    <label className="mb-1.5 block text-xs font-medium text-[var(--color-text-secondary)]">
                      时区
                    </label>
                    <input
                      type="text"
                      value={draft.scheduler.timezone}
                      onChange={(e) => updateDraft('scheduler', 'timezone', e.target.value)}
                      placeholder="Asia/Shanghai"
                      className="w-full rounded-lg border border-[var(--color-border)] bg-white px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-placeholder)] focus:border-[var(--color-accent)] focus:ring-2 focus:ring-[var(--color-accent-soft)]"
                    />
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="flex h-16 items-center justify-between border-t border-[var(--color-border-light)] px-6">
            <div className="text-xs">
              {dirty ? (
                <span className="text-[var(--color-text-tertiary)]">未保存更改</span>
              ) : (
                <span className="text-[var(--color-text-tertiary)]">
                  <Check className="mr-1 inline h-3 w-3 text-[var(--color-success)]" />
                  已同步至最新
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg border border-[var(--color-border)] bg-white px-4 py-2 text-sm font-medium text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)] transition-colors"
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleSave}
                disabled={!dirty || saving}
                className={cn(
                  'flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors',
                  dirty
                    ? 'bg-[var(--color-accent)] text-white hover:opacity-90'
                    : 'bg-[var(--color-accent)] opacity-50 cursor-not-allowed text-white',
                )}
              >
                {saving ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Save className="h-4 w-4" />
                )}
                {saving ? '保存中…' : '保存'}
              </button>
            </div>
          </div>
        </div>
      </div>

      {toast && (
        <div
          className={cn(
            'fixed bottom-6 right-6 z-[60] rounded-lg px-4 py-2.5 shadow-xl text-sm text-white',
            toast.type === 'success' ? 'bg-[var(--color-success)]' : 'bg-[var(--color-danger)]',
          )}
        >
          {toast.msg}
        </div>
      )}
    </>
  )
}
