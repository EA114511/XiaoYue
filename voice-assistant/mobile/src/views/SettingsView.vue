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
          <span class="status-badge" :class="{ connected: isConnected }">
            {{ isConnected ? '已连接' : '未连接' }}
          </span>
        </div>
      </section>

      <!-- LLM Provider -->
      <section class="setting-group">
        <div class="group-header">
          <h2 class="group-title">LLM Provider</h2>
          <button class="add-btn" @click="showAddProvider = true" v-if="isConnected">
            <van-icon name="plus" size="16" />
          </button>
        </div>
        <div v-if="!isConnected" class="empty-tip">连接服务器后可管理</div>
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
          <button class="add-btn" @click="showAddVoiceProvider = true" v-if="isConnected">
            <van-icon name="plus" size="16" />
          </button>
        </div>
        <div v-if="!isConnected" class="empty-tip">连接服务器后可管理</div>
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
    </div>

    <!-- 添加/编辑 Provider 弹窗 -->
    <van-popup
      v-model:show="showAddProvider"
      position="bottom"
      :style="{ background: 'var(--ink-1)' }"
      round
    >
      <div class="popup-content">
        <h3 class="popup-title">{{ editingProvider ? '编辑' : '添加' }} LLM Provider</h3>
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
        <div class="popup-actions">
          <button class="btn-cancel" @click="showAddProvider = false">取消</button>
          <button class="btn-confirm" @click="saveProvider">保存</button>
        </div>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores'
import { voiceApi } from '@/api'
import { STORAGE_KEYS } from '@/utils/constants'
import NightSky from '@/components/NightSky.vue'

const router = useRouter()
const store = useAppStore()

// 服务器配置
const nasUrl = ref('')
const apiToken = ref('')
const isConnected = ref(false)

// LLM Provider
const llmProviders = ref([])
const currentProvider = ref('')
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

function goBack() {
  router.back()
}

function saveNasUrl() {
  if (nasUrl.value.startsWith('http')) {
    store.setNasUrl(nasUrl.value)
    checkConnection()
  }
}

function saveApiToken() {
  localStorage.setItem(STORAGE_KEYS.API_TOKEN, apiToken.value)
}

async function checkConnection() {
  try {
    await voiceApi.health()
    isConnected.value = true
    loadProviders()
  } catch (e) {
    isConnected.value = false
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
  }
}

function editProvider(provider) {
  editingProvider.value = provider
  providerForm.value = { ...provider }
  showAddProvider.value = true
}

async function saveProvider() {
  try {
    if (editingProvider.value) {
      await voiceApi.updateProvider(providerForm.value.name, providerForm.value)
    } else {
      await voiceApi.createProvider(providerForm.value)
    }
    showAddProvider.value = false
    editingProvider.value = null
    providerForm.value = { name: '', api_base: '', api_key: '', model: '', max_tokens: 2048, temperature: 0.7 }
    loadProviders()
  } catch (e) {
    console.error('保存 Provider 失败:', e)
  }
}

async function deleteProvider(name) {
  try {
    await voiceApi.deleteProvider(name)
    loadProviders()
  } catch (e) {
    console.error('删除 Provider 失败:', e)
  }
}

async function toggleVoiceProvider(provider) {
  try {
    await voiceApi.updateVoiceProvider(provider.name, { enabled: !provider.enabled })
    loadProviders()
  } catch (e) {
    console.error('切换语音 Provider 失败:', e)
  }
}

onMounted(() => {
  nasUrl.value = store.nasUrl
  apiToken.value = localStorage.getItem(STORAGE_KEYS.API_TOKEN) || ''
  checkConnection()
})
</script>

<style scoped>
.settings-view {
  position: relative;
  min-height: 100vh;
  min-height: 100dvh;
}

/* ---------- 顶栏 ---------- */
.top-bar {
  position: relative;
  z-index: 10;
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
  padding: 16px 20px;
  padding-bottom: calc(20px + env(safe-area-inset-bottom));
}

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

/* ---------- 弹窗 ---------- */
.popup-content {
  padding: 24px 20px;
  padding-bottom: calc(24px + env(safe-area-inset-bottom));
}

.popup-title {
  font-family: 'Noto Serif SC', 'SimSun', serif;
  font-size: 18px;
  font-weight: 600;
  color: var(--pearl);
  margin: 0 0 20px;
  text-align: center;
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
  margin-top: 24px;
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

.btn-confirm {
  background: var(--gold);
  border-color: var(--gold);
  color: var(--ink-0);
}

.btn-confirm:active {
  background: var(--gold-2);
}
</style>
