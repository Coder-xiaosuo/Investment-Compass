import axios from 'axios'
import { useCallback } from 'react'

/** 冷启动问卷题（后端 /api/style_profile/questions） */
export interface QuizOption {
  label: string
  text: string
}
export interface QuizQuestion {
  id: string
  scenario: string
  dimension: string
  options: QuizOption[]
}

/** 雷达图数据点（后端 /api/style_profile） */
export interface RadarPoint {
  dimension: string
  label: string
  axis_label: string
  score: number // [-1, 1]
  score_0_100: number // [0, 100]
  matched_style: string
  evidence_count: number
}

/** 六维雷达图完整数据 */
export interface RadarProfile {
  user_id: string
  stable: boolean
  quiz_completed_count: number
  conversation_count: number
  points: RadarPoint[]
  summary: string
}

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

export function useStyleProfile() {
  /** 拉取冷启动题库（30 题）+ 维度定义 */
  const fetchQuestions = useCallback(async (): Promise<{
    questions: QuizQuestion[]
    dimensions: Record<string, { label: string; axis_label: string }>
  }> => {
    const res = await api.get<ApiResponse<any>>('/style_profile/questions')
    return {
      questions: res.data.data?.cold_start_questions ?? [],
      dimensions: res.data.data?.dimensions ?? {},
    }
  }, [])

  /** 拉取当前用户雷达图画像（未测试时后端返回默认 0 分画像） */
  const fetchProfile = useCallback(async (): Promise<RadarProfile | null> => {
    const res = await api.get<ApiResponse<RadarProfile>>('/style_profile')
    return res.data.data ?? null
  }, [])

  /** 提交问卷答案（≥6 题）生成画像 */
  const submitAnswers = useCallback(
    async (answers: { question_id: string; selected_label: string }[]): Promise<any> => {
      const res = await api.post<ApiResponse<any>>('/style_profile/cold_start', { answers })
      if (res.data.code !== 0) throw new Error(res.data.message || '提交失败')
      return res.data.data
    },
    [],
  )

  return { fetchQuestions, fetchProfile, submitAnswers }
}
