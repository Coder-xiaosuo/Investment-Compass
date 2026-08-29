import axios from 'axios'
import { useCallback } from 'react'

export interface PreferencesData {
  initialized: boolean
  sections: Record<string, string>
  /** 自进化画像区段原始文本 */
  evolution: string | null
  raw: string
}

const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
})

export function usePreferences() {
  const fetchPreferences = useCallback(async (): Promise<PreferencesData | null> => {
    const res = await api.get<{ code: number; data: PreferencesData }>('/preferences')
    if (res.data.code !== 0) return null
    return res.data.data ?? null
  }, [])

  return { fetchPreferences }
}
