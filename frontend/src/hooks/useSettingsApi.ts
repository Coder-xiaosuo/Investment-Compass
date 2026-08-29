import axios from 'axios'
import { useCallback } from 'react'
import type {
  SettingsView,
  SettingsPatch,
  ReasoningEffort,
  ValidateLlmResult,
  TestNotificationResult,
} from '../types'

const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
})

export function useSettingsApi() {
  const get = useCallback(async (): Promise<SettingsView> => {
    const res = await api.get<{ code: number; data: SettingsView; message?: string }>('/settings')
    if (res.data.code !== 0) throw new Error(res.data.message || 'GET /settings failed')
    return res.data.data
  }, [])

  const update = useCallback(
    async (
      patch: SettingsPatch,
    ): Promise<{ version: number; settings: SettingsView }> => {
      const res = await api.put<{
        code: number
        message?: string
        data: { version: number; settings: SettingsView }
      }>('/settings', patch)
      if (res.data.code !== 0) throw new Error(res.data.message || 'PUT /settings failed')
      return res.data.data
    },
    [],
  )

  const validateLlm = useCallback(
    async (body: {
      model?: string
      base_url?: string
      api_key?: string
      thinking?: boolean
      reasoning_effort?: ReasoningEffort
    }): Promise<ValidateLlmResult> => {
      const res = await api.post<{ code: number; data: ValidateLlmResult; message?: string }>(
        '/settings/validate-llm',
        body,
      )
      if (res.data.code !== 0) throw new Error(res.data.message || 'validate-llm failed')
      return res.data.data
    },
    [],
  )

  const testNotification = useCallback(
    async (body: {
      type: 'feishu' | 'pushplus'
      params?: Record<string, any>
    }): Promise<TestNotificationResult> => {
      const res = await api.post<{ code: number; data: TestNotificationResult; message?: string }>(
        '/settings/test-notification',
        body,
      )
      if (res.data.code !== 0) throw new Error(res.data.message || 'test-notification failed')
      return res.data.data
    },
    [],
  )

  return { get, update, validateLlm, testNotification }
}
