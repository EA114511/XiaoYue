// API 层封装

import axios from 'axios'
import { API_CONFIG, STORAGE_KEYS } from '@/utils/constants'

// 创建 axios 实例
const api = axios.create({
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器：添加认证头
api.interceptors.request.use(config => {
  const token = localStorage.getItem(STORAGE_KEYS.API_TOKEN)
  if (token) {
    config.headers['X-API-Token'] = token
  }
  return config
})

// 响应拦截器：统一错误处理
api.interceptors.response.use(
  response => response.data,
  error => {
    console.error('[API Error]', error)
    return Promise.reject(error)
  }
)

// 获取 NAS 基础 URL
export function getBaseUrl() {
  return localStorage.getItem(STORAGE_KEYS.NAS_URL) || API_CONFIG.DEFAULT_NAS_URL
}

// 设置 NAS 基础 URL
export function setBaseUrl(url) {
  localStorage.setItem(STORAGE_KEYS.NAS_URL, url)
}

// 获取 WebSocket URL
export function getWsUrl() {
  const baseUrl = getBaseUrl()
  const wsUrl = baseUrl.replace(/^http/, 'ws')
  return `${wsUrl}${API_CONFIG.WS_PATH}`
}

// API 方法
export const voiceApi = {
  // 健康检查
  health: () => api.get(`${getBaseUrl()}${API_CONFIG.API_PATH}/health/status`),

  // 发送文本消息
  sendText: (text, conversationId) => api.post(`${getBaseUrl()}${API_CONFIG.API_PATH}/conversation/message`, {
    conversation_id: conversationId,
    message: text
  }),

  // 获取对话历史
  getHistory: (limit = 20) => api.get(`${getBaseUrl()}${API_CONFIG.API_PATH}/conversation/history`, {
    params: { limit }
  }),

  // 获取对话详情
  getConversation: (id) => api.get(`${getBaseUrl()}${API_CONFIG.API_PATH}/conversation/history/${id}`),

  // 删除对话
  deleteConversation: (id) => api.delete(`${getBaseUrl()}${API_CONFIG.API_PATH}/conversation/history/${id}`)
}

export default api
