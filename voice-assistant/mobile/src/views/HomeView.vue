<template>
  <div class="home-view">
    <!-- 顶栏 -->
    <van-nav-bar title="小玥" fixed placeholder>
      <template #right>
        <van-icon name="setting-o" size="20" @click="goSettings" />
      </template>
    </van-nav-bar>

    <!-- 光球区域 -->
    <div class="orb-section">
      <VoiceOrb :state="orbState" />
      <p class="status-text">{{ statusText }}</p>
      <p class="hint-text">{{ hintText }}</p>
    </div>

    <!-- 最近消息 -->
    <div class="messages-section" v-if="messages.length > 0">
      <div class="section-title">
        <span>最近对话</span>
        <van-button
          v-if="messages.length > 3"
          size="mini"
          plain
          @click="clearMessages"
        >
          清空
        </van-button>
      </div>
      <div class="messages-list">
        <MessageCard
          v-for="msg in recentMessages"
          :key="msg.id"
          :message="msg"
        />
      </div>
    </div>

    <!-- 底部操作区 -->
    <div class="action-bar safe-area-bottom">
      <VoiceButton
        :recording="isRecording"
        :processing="isProcessing"
        :disabled="!isConnected"
        @touchstart="startRecording"
        @touchend="stopRecording"
      />
      <p class="connection-status" :class="{ connected: isConnected }">
        {{ isConnected ? '已连接' : '未连接' }}
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores'
import { useVoiceChat } from '@/composables/useVoiceChat'
import { STATE_TEXT, HINTS } from '@/utils/constants'
import VoiceOrb from '@/components/VoiceOrb.vue'
import VoiceButton from '@/components/VoiceButton.vue'
import MessageCard from '@/components/MessageCard.vue'

const router = useRouter()
const store = useAppStore()

// 语音对话
const {
  isRecording,
  isProcessing,
  isPlaying,
  isConnected,
  status,
  startRecording,
  stopRecording,
  sendText
} = useVoiceChat({
  onTranscript: (text) => {
    store.addMessage('user', text)
  },
  onResponse: (text, isStream, isEnd) => {
    if (isStream) {
      // 流式响应：更新最后一条消息
      const lastMsg = store.messages[store.messages.length - 1]
      if (lastMsg?.role === 'assistant') {
        lastMsg.content += text
      } else {
        store.addMessage('assistant', text)
      }
    } else {
      store.addMessage('assistant', text)
    }
  },
  onError: (err) => {
    console.error('[Home] 错误:', err)
  },
  onStatusChange: (status) => {
    store.setConnected(status === 'connected')
  }
})

// 计算属性
const messages = computed(() => store.messages)
const recentMessages = computed(() => store.recentMessages)

const orbState = computed(() => status.value)

const statusText = computed(() => STATE_TEXT[status.value]?.verb || '待机')

const hintText = computed(() => {
  if (!isConnected.value) return HINTS.ERROR
  return HINTS[status.value.toUpperCase()] || HINTS.IDLE
})

// 方法
function goSettings() {
  router.push('/settings')
}

function clearMessages() {
  store.clearMessages()
}

onMounted(() => {
  // 加载历史
  store.loadHistory()
})
</script>

<style scoped>
.home-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
  height: 100dvh;
  background: var(--ink-0);
}

.orb-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.status-text {
  margin-top: 24px;
  font-size: 24px;
  font-weight: 500;
  letter-spacing: 0.2em;
  color: var(--pearl);
}

.hint-text {
  margin-top: 12px;
  font-size: 14px;
  color: var(--mist);
}

.messages-section {
  flex-shrink: 0;
  max-height: 30vh;
  padding: 0 16px;
  overflow-y: auto;
}

.section-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  font-size: 13px;
  color: var(--mist);
}

.messages-list {
  display: flex;
  flex-direction: column;
}

.action-bar {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px;
  padding-bottom: calc(20px + var(--safe-area-bottom));
}

.connection-status {
  margin-top: 12px;
  font-size: 12px;
  color: var(--faint);
}

.connection-status.connected {
  color: var(--celadon);
}
</style>
