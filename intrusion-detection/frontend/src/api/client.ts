import axios from 'axios'

export const http = axios.create({ baseURL: '/api', timeout: 30000 })

export interface DetectionTask {
  id: number
  dataset_id: number
  model_id: number
  status: string
  processed_rows: number
  total_rows?: number
  error?: string
}

export interface Dataset { id: number; name: string; row_count: number; label_available: boolean }
export interface Model { id: number; name: string; feature_count: number }
export function errorText(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    return typeof detail === 'string' ? detail : '请求失败，请检查后台服务后重试'
  }
  return '操作失败，请重试'
}

export const datasetsApi = {
  upload(form: FormData) {
    return http.post('/datasets', form)
  },
}

export const detectionsApi = {
  create(datasetId: number, modelId: number) {
    return http.post<DetectionTask>('/detections', { dataset_id: datasetId, model_id: modelId })
  },
  get(id: number) {
    return http.get<DetectionTask>(`/detections/${id}`)
  },
  results(id: number) {
    return http.get(`/detections/${id}/results`)
  },
  statistics(id: number) {
    return http.get(`/detections/${id}/statistics`)
  },
  report(id: number) {
    return http.get(`/detections/${id}/report`)
  },
}