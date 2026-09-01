<template>
  <div class="settings-view">
    <!-- 星野背景 -->
    <NightSky />

    <!-- 顶栏 -->
    <header class="top-bar">
      <button class="back-btn" @click="goBack" aria-label="返回">
        <van-icon name="arrow-left" size="20" />
      </button>
      <h1 class="page-title">设置</h1>
      <div class="placeholder"></div>
    </header>

    <div class="settings-content">
      <!-- 未连接状态 -->
      <div v-if="!isConnected" class="not-connected">
        <div class="not-connected-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M12 2L2 7l10 5 10-5-10-5z" />
            <path d="M2 17l10 5 10-5" />
            <path d="M2 12l10 5 10-5" />
          </svg>
        </div>
        <h2 class="not-connected-title">未连接到服务器</h2>
        <p class="not-connected-desc">
          请先配置 NAS 地址并连接后端服务，<br />
          连接成功后可管理 Provider 和配置。
        </p>
      </div>

      <!-- 已连接状态 -->
      <template v-else>
        <!-- 服务器配置 -->
        <section class="setting-group">
          <h2 class="group-title">服务器配置</h2>
          <div class="setting-item">
            <label class="item-label">NAS 地址</label>
            <input
              v-model="nasUrl"
              type="text"
              class="item-input"
              placeholder="http://192.168.5.5:8000"
              @blur="saveNasUrl"
            />
          </div>
          <div class="setting-item">
            <label class="item-label">API Token</label>
            <input
              v-model="apiToken"
              type="password"
              class="item-input"
              placeholder="可选，用于写操作鉴权"
              @blur="saveApiToken"
            />
          </div>
          <div class="setting-item">
            <label class="item-label">连接状态</label>
            <span class="status-badge connected">已连接</span>
          </div>
        </section>

        <!-- LLM Provider -->
        <section class="setting-group">
          <div class="group-header">
            <h2 class="group-title">LLM Provider</h2>
            <button class="add-btn" @click="openAddProvider">
              <van-icon name="plus" size="16" />
            </button>
          </div>
          <div v-if="loading" class="loading-tip">加载中...</div>
          <div v-else-if="llmProviders.length === 0" class="empty-tip">暂无配置</div>
          <div v-else class="provider-list">
            <div
              v-for="provider in llmProviders"
              :key="provider.name"
              class="provider-item"
              :class="{ active: provider.name === currentProvider }"
            >
              <div class="provider-info">
                <span class="provider-name">{{ provider.name }}</span>
                <span class="provider-model">{{ provider.model }}</span>
              </div>
              <div class="provider-actions">
                <button class="action-btn" @click="editProvider(provider)">编辑</button>
                <button
                  v-if="provider.name !== 'default'"
                  class="action-btn delete"
                  @click="deleteProvider(provider.name)"
                >
                  删除
                </button>
              </div>
            </div>
          </div>
        </section>

        <!-- 语音 Provider -->
        <section class="setting-group">
          <div class="group-header">
            <h2 class="group-title">语音 Provider</h2>
            <button class="add-btn" @click="showAddVoiceProvider = true">
              <van-icon name="plus" size="16" />
            </button>
          </div>
          <div v-if="loading" class="loading-tip">加载中...</div>
          <div v-else-if="voiceProviders.length === 0" class="empty-tip">暂无配置</div>
          <div v-else class="provider-list">
            <div
              v-for="provider in voiceProviders"
              :key="provider.name"
              class="provider-item"
              :class="{ active: provider.enabled }"
            >
              <div class="provider-info">
                <span class="provider-name">{{ provider.name }}</span>
                <span class="provider-model">{{ provider.model }} · {{ provider.voice }}</span>
              </div>
              <label class="switch">
                <input
                  type="checkbox"
                  :checked="provider.enabled"
                  @change="toggleVoiceProvider(provider)"
                />
                <span class="slider"></span>
              </label>
            </div>
          </div>
        </section>

        <!-- 语音设置 -->
        <section class="setting-group">
          <h2 class="group-title">语音设置</h2>
          <div class="setting-item">
            <label class="item-label">唤醒词</label>
            <span class="item-value">小玥小玥</span>
          </div>
          <div class="setting-item">
            <label class="item-label">语音打断</label>
            <label class="switch">
              <input type="checkbox" v-model="bargeInEnabled" />
              <span class="slider"></span>
            </label>
          </div>
          <div class="setting-item">
            <label class="item-label">VAD 自动断句</label>
            <label class="switch">
              <input type="checkbox" v-model="vadEnabled" />
              <span class="slider"></span>
            </label>
          </div>
        </section>

        <!-- 关于 -->
        <section class="setting-group">
          <h2 class="group-title">关于</h2>
          <div class="setting-item">
            <label class="item-label">版本</label>
            <span class="item-value">1.0.0</span>
          </div>
          <div class="setting-item">
            <label class="item-label">设计主题</label>
            <span class="item-value">月夜 · 明珠</span>
          </div>
        </section>
      </template>
    </div>

    <!-- 添加/编辑 Provider 弹窗 -->
    <teleport to="body">
      <div v-if="showAddProvider" class="custom-popup-overlay" @click.self="closePopup">
        <div class="custom-popup">
          <div class="popup-header">
            <h3 class="popup-title">{{ editingProvider ? '编辑' : '添加' }} LLM Provider</h3>
            <button class="popup-close" @click="closePopup" aria-label="关闭">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div class="popup-body">
            <div class="form-item">
              <label>名称</label>
              <input v-model="providerForm.name" :disabled="editingProvider" placeholder="provider 名称" />
            </div>
            <div class="form-item">
              <label>API Base</label>
              <input v-model="providerForm.api_base" placeholder="https://api.example.com/v1" />
            </div>
            <div class="form-item">
              <label>API Key</label>
              <input v-model="providerForm.api_key" type="password" placeholder="sk-..." />
            </div>
            <div class="form-item">
              <label>模型</label>
              <input v-model="providerForm.model" placeholder="gpt-3.5-turbo" />
            </div>
          </div>
          <div class="popup-actions">
            <button class="btn-cancel" @click="closePopup">取消</button>
            <button class="btn-confirm" @click="saveProvider">保存</button>
          </div>
        </div>
      </div>
    </teleport>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { showToast, showSuccessToast, showFailToast } from 'vant'
import { useAppStore } from '@/stores'
import { voiceApi, setBaseUrl, setSessionApiToken, clearSessionApiToken } from '@/api'
import NightSky from '@/components/NightSky.vue'

const router = useRouter()
const store = useAppStore()

// 服务器配置
const nasUrl = ref('')
const apiToken = ref('')
const isConnected = ref(false)
const loading = ref(false)

// LLM Provider
const llmProviders = ref([])
const currentProvider = ref('')
// 确保弹窗默认关闭
const showAddProvider = ref(false)
const editingProvider = ref(null)
const providerForm = ref({
  name: '',
  api_base: '',
  api_key: '',
  model: '',
  max_tokens: 2048,
  temperature: 0.7
})

// 语音 Provider
const voiceProviders = ref([])
const showAddVoiceProvider = ref(false)

// 语音设置
const bargeInEnabled = ref(true)
const vadEnabled = ref(true)

// 键盘事件处理
function handleKeydown(e) {
  if (e.key === 'Escape' && showAddProvider.value) {
    showAddProvider.value = false
    editingProvider.value = null
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
  nasUrl.value = store.nasUrl
  // 延迟检查连接，避免页面加载时闪烁
  setTimeout(() => {
    checkConnection()
  }, 100)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
})

function goBack() {
  router.back()
}

async function saveNasUrl() {
  if (!nasUrl.value.startsWith('http')) {
    showFailToast('请输入正确的 URL，以 http:// 或 https:// 开头')
    return
  }
  setBaseUrl(nasUrl.value)
  showSuccessToast('已保存')
  await checkConnection()
}

function saveApiToken() {
  // 存储到会话，不保存到 localStorage
  if (apiToken.value) {
    setSessionApiToken(apiToken.value)
    showSuccessToast('API Token 已设置')
  } else {
    clearSessionApiToken()
    showToast('API Token 已清除')
  }
}

async function checkConnection() {
  loading.value = true
  try {
    await voiceApi.health()
    isConnected.value = true
    showSuccessToast('连接成功')
    await loadProviders()
  } catch (e) {
    isConnected.value = false
    showFailToast('连接失败，请检查地址')
    console.error('连接失败:', e)
  } finally {
    loading.value = false
  }
}

async function loadProviders() {
  try {
    const [llmData, voiceData] = await Promise.all([
      voiceApi.getProviders(),
      voiceApi.getVoiceProviders()
    ])
    llmProviders.value = llmData.providers || llmData || []
    voiceProviders.value = voiceData.providers || voiceData || []

    // 获取当前使用的 provider
    const settings = await voiceApi.getSettings()
    currentProvider.value = settings.dialog_provider_name || settings.nlu_provider_name || 'default'
  } catch (e) {
    console.error('加载 Provider 失败:', e)
    showFailToast('加载配置失败')
  }
}

function editProvider(provider) {
  editingProvider.value = provider
  providerForm.value = { ...provider }
  showAddProvider.value = true
}

function openAddProvider() {
  editingProvider.value = null
  providerForm.value = {
    name: '',
    api_base: '',
    api_key: '',
    model: '',
    max_tokens: 2048,
    temperature: 0.7
  }
  showAddProvider.value = true
}

function closePopup() {
  showAddProvider.value = false
  editingProvider.value = null
  providerForm.value = {
    name: '',
    api_base: '',
    api_key: '',
    model: '',
    max_tokens: 2048,
    temperature: 0.7
  }
}

async function saveProvider() {
  // 验证表单
  if (!providerForm.value.name.trim()) {
    showFailToast('请输入 Provider 名称')
    return
  }
  if (!providerForm.value.api_base.trim()) {
    showFailToast('请输入 API Base')
    return
  }
  if (!providerForm.value.model.trim()) {
    showFailToast('请输入模型名称')
    return
  }

  try {
    if (editingProvider.value) {
      await voiceApi.updateProvider(providerForm.value.name, providerForm.value)
      showSuccessToast('Provider 已更新')
    } else {
      await voiceApi.createProvider(providerForm.value)
      showSuccessToast('Provider 已添加')
    }
    closePopup()
    await loadProviders()
  } catch (e) {
    console.error('保存 Provider 失败:', e)
    showFailToast('保存失败: ' + (e.message || '未知错误'))
  }
}

async function deleteProvider(name) {
  try {
    await voiceApi.deleteProvider(name)
    showSuccessToast('Provider 已删除')
    await loadProviders()
  } catch (e) {
    console.error('删除 Provider 失败:', e)
    showFailToast('删除失败')
  }
}

async function toggleVoiceProvider(provider) {
  try {
    await voiceApi.updateVoiceProvider(provider.name, { enabled: !provider.enabled })
    showSuccessToast(provider.enabled ? '已禁用' : '已启用')
    await loadProviders()
  } catch (e) {
    console.error('切换语音 Provider 失败:', e)
    showFailToast('操作失败')
  }
}
</script>

<style scoped>
.settings-view {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
}

/* ---------- 顶栏 ---------- */
.top-bar {
  position: relative;
  z-index: 10;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  padding-top: calc(12px + env(safe-area-inset-top));
}

.back-btn {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  color: var(--mist);
  border-radius: 10px;
  border: 1px solid var(--hair-cool);
  background: linear-gradient(160deg, rgba(27, 35, 64, 0.4), rgba(13, 18, 32, 0.3));
  transition: all 0.25s ease;
}

.back-btn:active {
  background: rgba(228, 181, 106, 0.15);
  border-color: var(--hair-warm);
  color: var(--gold-2);
}

.page-title {
  font-family: 'Noto Serif SC', 'SimSun', serif;
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0.15em;
  color: var(--pearl);
  margin: 0;
}

.placeholder {
  width: 40px;
}

/* ---------- 设置内容 ---------- */
.settings-content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 16px 20px;
  padding-bottom: calc(20px + env(safe-area-inset-bottom));
  -webkit-overflow-scrolling: touch; /* iOS 平滑滚动 */
}

/* ---------- 未连接状态 ---------- */
.not-connected {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  text-align: center;
}

.not-connected-icon {
  width: 80px;
  height: 80px;
  display: grid;
  place-items: center;
  margin-bottom: 24px;
  border-radius: 50%;
  border: 1px solid var(--hair-cool);
  background: linear-gradient(160deg, rgba(27, 35, 64, 0.4), rgba(13, 18, 32, 0.3));
  color: var(--mist);
}

.not-connected-icon svg {
  width: 40px;
  height: 40px;
}

.not-connected-title {
  font-family: 'Noto Serif SC', 'SimSun', serif;
  font-size: 20px;
  font-weight: 600;
  color: var(--pearl);
  margin: 0 0 12px;
}

.not-connected-desc {
  font-size: 14px;
  line-height: 1.7;
  color: var(--mist);
  margin: 0;
}

/* ---------- 设置组 ---------- */
.setting-group {
  margin-bottom: 24px;
}

.group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 0 0 12px 4px;
}

.group-title {
  font-family: 'Noto Serif SC', 'SimSun', serif;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.15em;
  color: var(--mist);
  margin: 0;
}

.add-btn {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  border: 1px solid var(--hair-warm);
  background: rgba(228, 181, 106, 0.1);
  color: var(--gold);
  transition: all 0.25s ease;
}

.add-btn:active {
  background: var(--gold);
  color: var(--ink-0);
}

.setting-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  background: linear-gradient(160deg, rgba(27, 35, 64, 0.4), rgba(13, 18, 32, 0.3));
  border: 1px solid var(--hair-cool);
  border-radius: 12px;
  margin-bottom: 10px;
}

.item-label {
  font-size: 14px;
  color: var(--pearl);
}

.item-value {
  font-size: 14px;
  color: var(--mist);
}

.item-input {
  flex: 1;
  max-width: 200px;
  padding: 8px 12px;
  font-size: 14px;
  color: var(--pearl);
  background: rgba(9, 12, 20, 0.5);
  border: 1px solid var(--hair-cool);
  border-radius: 8px;
  outline: none;
  transition: border-color 0.25s ease;
}

.item-input:focus {
  border-color: var(--gold);
}

.item-input::placeholder {
  color: var(--faint);
}

/* ---------- 状态徽章 ---------- */
.status-badge {
  padding: 4px 12px;
  font-size: 12px;
  border-radius: 12px;
  background: rgba(126, 142, 166, 0.15);
  color: var(--mist);
}

.status-badge.connected {
  background: rgba(159, 212, 203, 0.15);
  color: var(--celadon);
}

/* ---------- Provider 列表 ---------- */
.loading-tip,
.empty-tip {
  padding: 20px;
  text-align: center;
  color: var(--faint);
  font-size: 13px;
}

.provider-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.provider-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: linear-gradient(160deg, rgba(27, 35, 64, 0.4), rgba(13, 18, 32, 0.3));
  border: 1px solid var(--hair-cool);
  border-radius: 12px;
}

.provider-item.active {
  border-color: var(--gold);
  background: linear-gradient(160deg, rgba(228, 181, 106, 0.12), rgba(228, 181, 106, 0.04));
}

.provider-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.provider-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--pearl);
}

.provider-model {
  font-size: 12px;
  color: var(--mist);
}

.provider-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  padding: 4px 12px;
  font-size: 12px;
  border-radius: 6px;
  border: 1px solid var(--hair-cool);
  background: transparent;
  color: var(--mist);
  transition: all 0.25s ease;
}

.action-btn:active {
  border-color: var(--gold);
  color: var(--gold);
}

.action-btn.delete {
  border-color: rgba(255, 107, 107, 0.3);
  color: #ff6b6b;
}

.action-btn.delete:active {
  background: rgba(255, 107, 107, 0.1);
}

/* ---------- 开关 ---------- */
.switch {
  position: relative;
  width: 44px;
  height: 24px;
  display: inline-block;
}

.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(126, 142, 166, 0.3);
  border-radius: 24px;
  transition: 0.3s;
}

.slider::before {
  position: absolute;
  content: '';
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background: var(--pearl);
  border-radius: 50%;
  transition: 0.3s;
}

.switch input:checked + .slider {
  background: var(--gold);
}

.switch input:checked + .slider::before {
  transform: translateX(20px);
  background: var(--ink-0);
}

/* ---------- 自定义弹窗 ---------- */
.custom-popup-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(9, 12, 20, 0.8);
  backdrop-filter: blur(4px);
  z-index: 1000;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding: 20px;
  padding-bottom: calc(20px + env(safe-area-inset-bottom));
  animation: fade-in 0.2s ease;
}

@keyframes fade-in {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

.custom-popup {
  width: 100%;
  max-width: 480px;
  max-height: 80vh;
  background: var(--ink-1);
  border: 1px solid var(--hair-cool);
  border-radius: 20px;
  overflow: hidden;
  animation: slide-up 0.3s ease;
}

@keyframes slide-up {
  from {
    transform: translateY(100%);
    opacity: 0;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}

.popup-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px;
  border-bottom: 1px solid var(--hair-cool);
}

.popup-title {
  font-family: 'Noto Serif SC', 'SimSun', serif;
  font-size: 18px;
  font-weight: 600;
  color: var(--pearl);
  margin: 0;
}

.popup-close {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  color: var(--mist);
  transition: all 0.25s ease;
}

.popup-close:active {
  background: rgba(228, 181, 106, 0.1);
  color: var(--gold);
}

.popup-close svg {
  width: 20px;
  height: 20px;
}

.popup-body {
  padding: 20px;
  max-height: 50vh;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}

.form-item {
  margin-bottom: 16px;
}

.form-item label {
  display: block;
  font-size: 13px;
  color: var(--mist);
  margin-bottom: 6px;
}

.form-item input {
  width: 100%;
  padding: 12px 14px;
  font-size: 14px;
  color: var(--pearl);
  background: rgba(9, 12, 20, 0.5);
  border: 1px solid var(--hair-cool);
  border-radius: 10px;
  outline: none;
  transition: border-color 0.25s ease;
}

.form-item input:focus {
  border-color: var(--gold);
}

.form-item input::placeholder {
  color: var(--faint);
}

.form-item input:disabled {
  opacity: 0.5;
}

.popup-actions {
  display: flex;
  gap: 12px;
  padding: 16px 20px;
  padding-bottom: calc(16px + env(safe-area-inset-bottom));
  border-top: 1px solid var(--hair-cool);
}

.btn-cancel,
.btn-confirm {
  flex: 1;
  padding: 12px;
  font-size: 15px;
  border-radius: 10px;
  border: 1px solid var(--hair-cool);
  transition: all 0.25s ease;
}

.btn-cancel {
  background: transparent;
  color: var(--mist);
}

.btn-cancel:active {
  background: rgba(126, 142, 166, 0.1);
}

.btn-confirm {
  background: var(--gold);
  border-color: var(--gold);
  color: var(--ink-0);
}

.btn-confirm:active {
  background: var(--gold-2);
}
</style>
