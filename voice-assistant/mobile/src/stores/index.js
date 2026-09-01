// Pinia 状态管理

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { voiceApi, getBaseUrl, setBaseUrl } from '@/api'

export const useAppStore = defineStore('app', () => {
  // 状态
  const nasUrl = ref(getBaseUrl())
  const isConnected = ref(false)
  const messages = ref([])
  const currentConversationId = ref(null)

  // 计算属性
  const recentMessages = computed(() => messages.value.slice(-3))

  // 方法
  function setNasUrl(url) {
    nasUrl.value = url
    setBaseUrl(url)
  }

  function addMessage(role, content, audio = null) {
    const message = {
      id: Date.now(),
      role,
      content,
      audio,
      time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    }
    messages.value.push(message)
    return message
  }

  function clearMessages() {
    messages.value = []
  }

  function setConnected(status) {
    isConnected.value = status
  }

  function setConversationId(id) {
    currentConversationId.value = id
  }

  async function loadHistory() {
    try {
      const data = await voiceApi.getHistory(20)
      if (data && data.conversations) {
        // 加载最近的对话
        return data.conversations
      }
    } catch (error) {
      console.error('[Store] 加载历史失败:', error)
    }
    return []
  }

  return {
    // 状态
    nasUrl,
    isConnected,
    messages,
    currentConversationId,
    // 计算属性
    recentMessages,
    // 方法
    setNasUrl,
    addMessage,
    clearMessages,
    setConnected,
    setConversationId,
    loadHistory
  }
})
