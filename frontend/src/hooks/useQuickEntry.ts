import axios from 'axios'
import { useCallback } from 'react'

export interface HotSector {
  name: string
  change: number
  reason: string
}

export interface CalendarEvent {
  date: string
  name: string
  desc: string
}

export interface RankingItem {
  title: string
  desc: string
  stocks: string[]
}

export interface StrategyItem {
  name: string
  annual: number
  total: number
  drawdown: number
}

const api = axios.create({ baseURL: '/api/demo', timeout: 8000 })

export function useQuickEntry() {
  const fetchHotSectors = useCallback(async (): Promise<HotSector[]> => {
    const res = await api.get<{ code: number; data: HotSector[] }>('/hot-sectors')
    return res.data.data ?? []
  }, [])

  const fetchCalendarEvents = useCallback(async (): Promise<CalendarEvent[]> => {
    const res = await api.get<{ code: number; data: CalendarEvent[] }>('/calendar-events')
    return res.data.data ?? []
  }, [])

  const fetchRankings = useCallback(async (): Promise<RankingItem[]> => {
    const res = await api.get<{ code: number; data: RankingItem[] }>('/rankings')
    return res.data.data ?? []
  }, [])

  const fetchStrategies = useCallback(async (): Promise<StrategyItem[]> => {
    const res = await api.get<{ code: number; data: StrategyItem[] }>('/strategies')
    return res.data.data ?? []
  }, [])

  return { fetchHotSectors, fetchCalendarEvents, fetchRankings, fetchStrategies }
}
