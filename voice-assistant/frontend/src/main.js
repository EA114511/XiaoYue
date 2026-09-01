import { createApp } from 'vue'
import App from './App.vue'
import './assets/styles/main.css'

// ============================================================
// 全局 fetch 包装：给所有请求自动附加 X-API-Token 鉴权头
// 后端对写操作（POST/PATCH/DELETE）校验该 Token，避免逐个调用点修改
// ============================================================
const API_TOKEN = import.meta.env.VITE_API_TOKEN || ''
const _originalFetch = window.fetch.bind(window)
window.fetch = (input, init = {}) => {
  if (!API_TOKEN) {
    return _originalFetch(input, init)
  }
  // 兼容 Headers 对象与普通对象两种 headers 形式
  const headers = new Headers(init.headers || {})
  headers.set('X-API-Token', API_TOKEN)
  return _originalFetch(input, { ...init, headers })
}

const app = createApp(App)
app.mount('#app')
