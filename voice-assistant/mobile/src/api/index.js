// API 层封装

import axios from 'axios'
import { API_CONFIG } from '@/utils/constants'

// 会话级 API Token（不存储到 localStorage，避免泄露）
let sessionApiToken = null

// 创建 axios 实例
const api = axios.create({
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器：添加认证头
api.interceptors.request.use(config => {
  if (sessionApiToken) {
    config.headers['X-API-Token'] = sessionApiToken
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

// 设置会话 API Token
export function setSessionApiToken(token) {
  sessionApiToken = token
}

// 清除会话 API Token
export function clearSessionApiToken() {
  sessionApiToken = null
}

// 获取 NAS 基础 URL（存储在内存中，页面刷新后需重新输入）
let sessionBaseUrl = API_CONFIG.DEFAULT_NAS_URL

export function getBaseUrl() {
  return sessionBaseUrl
}

export function setBaseUrl(url) {
  sessionBaseUrl = url
}

// 获取 WebSocket URL
export function getWsUrl() {
  const wsUrl = sessionBaseUrl.replace(/^http/, 'ws')
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
  deleteConversation: (id) => api.delete(`${getBaseUrl()}${API_CONFIG.API_PATH}/conversation/history/${id}`),

  // 获取运行时配置
  getSettings: () => api.get(`${getBaseUrl()}${API_CONFIG.API_PATH}/settings`),

  // 更新运行时配置
  updateSettings: (settings) => api.post(`${getBaseUrl()}${API_CONFIG.API_PATH}/settings`, settings),

  // ========== LLM Provider ==========
  getProviders: () => api.get(`${getBaseUrl()}${API_CONFIG.API_PATH}/providers`),
  createProvider: (provider) => api.post(`${getBaseUrl()}${API_CONFIG.API_PATH}/providers`, provider),
  updateProvider: (name, provider) => api.patch(`${getBaseUrl()}${API_CONFIG.API_PATH}/providers/${name}`, provider),
  deleteProvider: (name) => api.delete(`${getBaseUrl()}${API_CONFIG.API_PATH}/providers/${name}`),

  // ========== 语音 Provider ==========
  getVoiceProviders: () => api.get(`${getBaseUrl()}${API_CONFIG.API_PATH}/voice-providers`),
  createVoiceProvider: (provider) => api.post(`${getBaseUrl()}${API_CONFIG.API_PATH}/voice-providers`, provider),
  updateVoiceProvider: (name, provider) => api.patch(`${getBaseUrl()}${API_CONFIG.API_PATH}/voice-providers/${name}`, provider),
  deleteVoiceProvider: (name) => api.delete(`${getBaseUrl()}${API_CONFIG.API_PATH}/voice-providers/${name}`),

  // ========== 智能体 ==========
  getAgents: () => api.get(`${getBaseUrl()}${API_CONFIG.API_PATH}/agents`),
  updateAgent: (name, config) => api.patch(`${getBaseUrl()}${API_CONFIG.API_PATH}/agents/${name}`, config),

  // ========== 技能 ==========
  getSkills: () => api.get(`${getBaseUrl()}${API_CONFIG.API_PATH}/skills`),
  getEnabledSkills: () => api.get(`${getBaseUrl()}${API_CONFIG.API_PATH}/skills/enabled`)
}

export default api
