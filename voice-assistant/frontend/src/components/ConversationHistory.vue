<template>
  <!--
    history-root 作为 flex 子项，通过 .open 控制 width: 0 ↔ sidebar-width
    内部 history-panel 固定宽度 300px，由父容器 overflow:hidden 裁剪
  -->
  <div class="history-root" :class="{ open: isOpen }">
    <div class="history-panel">
      <!-- 侧边栏头部 -->
      <div class="history-header">
        <div class="history-title">
          <svg class="history-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10" />
            <polyline points="12 6 12 12 16 14" />
          </svg>
          <span>对话历史</span>
        </div>
        <button class="close-btn" @click="$emit('close')" title="关闭历史">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      <!-- 新对话按钮 -->
      <button class="new-chat-btn" @click="$emit('close')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
        <span>新对话</span>
      </button>

      <!-- 加载状态 -->
      <div v-if="loading" class="history-loading">
        <div class="loading-spinner"></div>
        <span>加载中...</span>
      </div>

      <!-- 空状态 -->
      <div v-else-if="conversations.length === 0" class="history-empty">
        <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
        <p>暂无对话记录</p>
      </div>

      <!-- 对话列表 -->
      <div v-else class="history-list">
        <div v-for="conv in conversations" :key="conv.id" class="history-item" :class="{ active: conv.id === selectedId }" @click="selectConversation(conv.id)">
          <div class="item-title">{{ conv.title || '新对话' }}</div>
          <div class="item-meta">
            <span class="item-time">{{ formatTime(conv.updated_at || conv.created_at) }}</span>
            <button class="delete-btn" @click.stop="confirmDelete(conv.id)" title="删除此对话">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
              </svg>
            </button>
          </div>
          <!-- 消息预览 -->
          <div v-if="conv.id === expandedId && conv.messages" class="item-preview">
            <div v-for="msg in conv.messages.slice(-3)" :key="msg.id" class="preview-msg" :class="msg.role">
              <span class="preview-label">{{ msg.role === 'user' ? '你' : 'AI' }}</span>
              <span class="preview-text">{{ truncate(msg.content, 60) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 遮罩层（移动端） -->
    <div v-if="isOpen" class="overlay" @click="$emit('close')"></div>
  </div>
</template>

<script setup>
/**
 * ConversationHistory.vue — 对话历史侧边栏
 *
 * 从后端 API 获取对话列表，支持点击展开详情、删除对话。
 * 点击对话条目填充到主聊天区。
 */

import { ref, watch, onMounted } from 'vue'

const props = defineProps({
  /** 侧边栏是否打开 */
  isOpen: { type: Boolean, default: false },
  /** 后端 API 基础地址（HTTP） */
  apiBase: { type: String, default: '' }
})

const emit = defineEmits(['close', 'load-conversation'])

/** @type {Ref<Array>} 对话列表 */
const conversations = ref([])
/** @type {Ref<boolean>} 是否正在加载 */
const loading = ref(false)
/** @type {Ref<string|null>} 当前选中的对话 ID */
const selectedId = ref(null)
/** @type {Ref<string|null>} 已展开详情的对话 ID */
const expandedId = ref(null)

/** 计算 API 基础地址 */
function getApiBase() {
  return props.apiBase || 'http://localhost:8000'
}

/** 加载对话列表 */
async function loadConversations() {
  loading.value = true
  try {
    const base = getApiBase()
    const res = await fetch(`${base}/api/v1/conversation/history?limit=50`)
    const data = await res.json()
    conversations.value = data.conversations || []
  } catch (e) {
    console.error('[ConversationHistory] 加载失败:', e)
  } finally {
    loading.value = false
  }
}

/** 选中/展开对话 */
async function selectConversation(id) {
  selectedId.value = id
  // 如果已展开，折叠预览并加载此对话到主聊天区
  if (expandedId.value === id) {
    expandedId.value = null
    // 加载完整详情后通知父组件切换对话
    try {
      const base = getApiBase()
      const res = await fetch(`${base}/api/v1/conversation/history/${id}`)
      const data = await res.json()
      emit('load-conversation', data)
    } catch (e) {
      console.error('[ConversationHistory] 加载详情失败:', e)
    }
    // 关闭侧边栏
    emit('close')
    return
  }
  // 首次点击：加载详情并展开预览
  try {
    const base = getApiBase()
    const res = await fetch(`${base}/api/v1/conversation/history/${id}`)
    const data = await res.json()
    // 更新列表中的对应项
    const idx = conversations.value.findIndex(c => c.id === id)
    if (idx !== -1) {
      conversations.value[idx] = { ...conversations.value[idx], ...data }
    }
    expandedId.value = id
  } catch (e) {
    console.error('[ConversationHistory] 加载详情失败:', e)
  }
}

/** 确认删除 */
async function confirmDelete(id) {
  if (!confirm('确定要删除此对话吗？')) return
  try {
    const base = getApiBase()
    const res = await fetch(`${base}/api/v1/conversation/history/${id}`, { method: 'DELETE' })
    if (!res.ok) throw new Error('删除失败')
    conversations.value = conversations.value.filter(c => c.id !== id)
    if (selectedId.value === id) {
      selectedId.value = null
      expandedId.value = null
    }
  } catch (e) {
    console.error('[ConversationHistory] 删除失败:', e)
  }
}

/** 格式化时间 */
function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diff = now - d
  // 今天内显示时间
  if (diff < 86400000 && d.getDate() === now.getDate()) {
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  }
  // 昨天
  const yesterday = new Date(now)
  yesterday.setDate(yesterday.getDate() - 1)
  if (d.getDate() === yesterday.getDate() && d.getMonth() === yesterday.getMonth()) {
    return '昨天'
  }
  // 更早
  return `${d.getMonth() + 1}/${d.getDate()}`
}

/** 截断文本 */
function truncate(text, maxLen) {
  if (!text) return ''
  return text.length > maxLen ? text.slice(0, maxLen) + '...' : text
}

// 打开时自动加载
watch(
  () => props.isOpen,
  val => {
    if (val) {
      loadConversations()
    }
  }
)

onMounted(() => {
  if (props.isOpen) {
    loadConversations()
  }
})
</script>

<style scoped>
/* ============================================================
   对话历史侧边栏 — 「月夜 · 明珠」暗色玻璃拟态抽屉
   原理：.history-root 作为 flex 子项通过宽度过渡展开/收起
   ============================================================ */

.history-root {
  flex-shrink: 0;
  overflow: hidden;
  width: 0;
  transition: width var(--duration-normal) var(--ease);
}

.history-root.open {
  width: var(--sidebar-width);
}

/* ---- 面板容器：暗色玻璃 + 发丝金线 ---- */
.history-panel {
  width: var(--sidebar-width);
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg-sidebar);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  border-right: 1px solid var(--hair-warm);
}

/* ---- 头部 ---- */
.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-lg) var(--space-lg) var(--space-sm);
  border-bottom: 1px solid var(--hair-cool);
  flex-shrink: 0;
}

.history-title {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  font-family: var(--serif);
  font-size: var(--text-base);
  font-weight: var(--weight-semibold);
  letter-spacing: 0.22em;
  color: var(--pearl);
}

.history-icon {
  width: 18px;
  height: 18px;
  color: var(--gold-2);
}

.close-btn {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  color: var(--mist);
  cursor: pointer;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--duration-fast) var(--ease);
}

.close-btn:hover {
  background: rgba(228, 181, 106, 0.06);
  color: var(--gold-2);
}

.close-btn svg {
  width: 18px;
  height: 18px;
}

/* ---- 新对话按钮 ---- */
.new-chat-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-sm);
  margin: var(--space-md) var(--space-lg);
  padding: 10px;
  border: 1px solid var(--hair-cool);
  border-radius: var(--radius-md);
  background: var(--glass-2);
  color: var(--pearl-dim);
  font-size: var(--text-sm);
  font-weight: var(--weight-medium);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease);
  flex-shrink: 0;
}

.new-chat-btn:hover {
  background: rgba(228, 181, 106, 0.06);
  border-color: var(--hair-warm);
  color: var(--gold-2);
}

.new-chat-btn:active {
  background: rgba(228, 181, 106, 0.1);
}

.new-chat-btn svg {
  width: 16px;
  height: 16px;
}

/* ---- 加载状态 ---- */
.history-loading {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-sm);
  color: var(--mist);
  font-size: var(--text-sm);
}

.loading-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid var(--hair-cool);
  border-top-color: var(--gold);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* ---- 空状态 ---- */
.history-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-sm);
  color: var(--mist);
  font-size: var(--text-sm);
}

.history-empty .empty-icon {
  width: 32px;
  height: 32px;
  opacity: 0.4;
}

/* ---- 对话列表 ---- */
.history-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-xs) var(--space-sm) var(--space-sm);
  scrollbar-width: thin;
  scrollbar-color: var(--ink-3) transparent;
}

.history-list::-webkit-scrollbar {
  width: 4px;
}

.history-list::-webkit-scrollbar-thumb {
  background: var(--ink-3);
  border-radius: 2px;
}

.history-list::-webkit-scrollbar-track {
  background: transparent;
}

.history-item {
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease);
  margin-bottom: 2px;
  position: relative;
}

.history-item:hover {
  background: rgba(239, 231, 211, 0.05);
}

.history-item.active {
  background: rgba(228, 181, 106, 0.08);
}

.history-item.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 20%;
  bottom: 20%;
  width: 3px;
  background: var(--gold);
  border-radius: 0 var(--radius-xs) var(--radius-xs) 0;
}

.item-title {
  font-size: var(--text-sm);
  font-weight: var(--weight-medium);
  color: var(--pearl);
  margin-bottom: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.item-time {
  font-size: var(--text-xs);
  color: var(--faint);
}

.delete-btn {
  width: 22px;
  height: 22px;
  border: none;
  background: transparent;
  color: var(--mist);
  cursor: pointer;
  border-radius: var(--radius-xs);
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition:
    opacity var(--duration-fast) var(--ease),
    background var(--duration-fast) var(--ease);
}

.history-item:hover .delete-btn {
  opacity: 1;
}

.delete-btn:hover {
  background: rgba(228, 181, 106, 0.12);
  color: var(--gold-2);
}

.delete-btn svg {
  width: 14px;
  height: 14px;
}

/* ---- 消息预览 ---- */
.item-preview {
  margin-top: var(--space-xs);
  padding: var(--space-xs) var(--space-sm);
  background: var(--glass-2);
  border: 1px solid var(--hair-cool);
  border-radius: var(--radius-xs);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.preview-msg {
  display: flex;
  gap: var(--space-xs);
  font-size: var(--text-xs);
  line-height: var(--leading-normal);
}

.preview-label {
  flex-shrink: 0;
  font-weight: var(--weight-medium);
  color: var(--gold-2);
  min-width: 18px;
}

.preview-msg.user .preview-label {
  color: var(--celadon);
}

.preview-text {
  color: var(--pearl-dim);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ---- 遮罩层（仅移动端） ---- */
.overlay {
  display: none;
}

@media (max-width: 640px) {
  .history-root {
    position: fixed;
    top: 0;
    left: 0;
    z-index: 30;
    height: 100%;
  }

  .history-root.open {
    width: 100%;
  }

  .history-panel {
    width: 100%;
    max-width: 320px;
  }

  .overlay {
    display: block;
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(5, 7, 12, 0.6);
    z-index: -1;
  }
}
</style>
