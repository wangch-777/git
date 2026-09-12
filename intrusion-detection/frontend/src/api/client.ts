import axios from 'axios'

export const http = axios.create({ baseURL: '/api', timeout: 30000 })

export interface DetectionTask {
  id: number
  status: string
  processed_rows: number
  total_rows?: number
  error?: string
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