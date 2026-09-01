<template>
  <Teleport to="body">
    <div class="voice-config-overlay" @click.self="$emit('close')">
      <div class="voice-config">
        <div class="config-card">
          <!-- 头部 -->
          <div class="config-header">
            <div class="config-logo">🎙️</div>
            <h2>配置中心</h2>
            <p class="config-desc">管理大模型接口 Provider，不同功能可独立配置不同模型</p>
          </div>

          <!-- 加载中 -->
          <div v-if="loading" class="loading-state">
            <div class="spinner" />
            <p>加载配置中...</p>
          </div>

          <template v-if="!loading">
            <!-- Tab 导航栏 -->
            <div class="config-tabs">
              <button v-for="tab in tabs" :key="tab.id" class="config-tab" :class="{ active: activeTab === tab.id }" @click="activeTab = tab.id">
                <span class="tab-icon">{{ tab.icon }}</span>
                <span class="tab-label">{{ tab.label }}</span>
              </button>
            </div>

            <!-- Tab 1: 概览 — 服务状态仪表盘 + 功能开关 -->
            <div v-if="activeTab === 'overview'" class="tab-content">
              <div class="status-section">
                <div class="status-item" :class="{ ok: backendReachable }">
                  <span class="status-icon">{{ backendReachable ? '✅' : '❌' }}</span>
                  <span class="status-label">后端服务</span>
                  <span class="status-value">{{ backendReachable ? '已连接' : '未连接' }}</span>
                </div>
                <div class="status-item" :class="{ ok: config.default_provider?.api_key_configured }">
                  <span class="status-icon">{{ config.default_provider?.api_key_configured ? '☁️' : '🖥️' }}</span>
                  <span class="status-label">默认模型</span>
                  <span class="status-value">{{ defaultModelDisplay }}</span>
                </div>
                <div class="status-item" :class="{ ok: config.enable_voice_dialogue }">
                  <span class="status-icon">{{ config.enable_voice_dialogue ? '✅' : '❌' }}</span>
                  <span class="status-label">语音对话</span>
                  <span class="status-value">{{ config.enable_voice_dialogue ? '已开启' : '已关闭' }}</span>
                </div>
                <!-- 智能体状态 -->
                <div class="status-item" :class="{ ok: enabledAgentCount > 0 }">
                  <span class="status-icon">🧠</span>
                  <span class="status-label">多智能体</span>
                  <span class="status-value">{{ enabledAgentCount > 0 ? `${enabledAgentCount} 个在线` : '待加载' }}</span>
                </div>
                <!-- Provider 数量 -->
                <div class="status-item" :class="{ ok: providers.length > 0 }">
                  <span class="status-icon">🔌</span>
                  <span class="status-label">模型接口</span>
                  <span class="status-value">{{ providers.length > 0 ? `${providers.length} 个已配置` : '未配置' }}</span>
                </div>
              </div>

              <!-- 语音对话开关 -->
              <div class="form-section">
                <h3>功能开关</h3>
                <div class="toggle-row">
                  <span class="toggle-label">语音对话模式</span>
                  <label class="toggle-switch">
                    <input type="checkbox" v-model="enableVoiceDialogue" />
                    <span class="toggle-slider" />
                  </label>
                </div>
              </div>
            </div>

            <!-- Tab 2: 模型接口 — LLM Provider 管理 -->
            <div v-if="activeTab === 'providers'" class="tab-content">
              <div class="form-section">
                <h3>
                  模型接口 Provider
                  <span class="section-hint">（配置大模型 API 接口地址、Key 和模型，各智能体可选择使用哪个 Provider）</span>
                </h3>

                <!-- Provider 列表 -->
                <div class="provider-list">
                  <div v-for="provider in providers" :key="provider.name" class="provider-item" :class="{ 'provider-default': provider.name === 'default' }">
                    <div class="provider-header" @click="toggleProviderExpand(provider)">
                      <div class="provider-info">
                        <span class="provider-icon">{{ getProviderIcon(provider.api_base) }}</span>
                        <span class="provider-name">{{ provider.name }}</span>
                        <span v-if="provider.name === 'default'" class="provider-badge provider-badge-default">默认</span>
                      </div>
                      <div class="provider-actions">
                        <span v-if="provider.api_key_configured" class="provider-key-badge">🔑 已配置</span>
                        <span v-else class="provider-key-badge no-key">🔓 无密钥</span>
                        <button v-if="provider.name !== 'default'" class="provider-delete-btn" @click.stop="deleteProvider(provider)" title="删除此 Provider">🗑️</button>
                        <span class="provider-expand-icon">{{ provider._expanded ? '▲' : '▼' }}</span>
                      </div>
                    </div>
                    <div class="provider-sub">
                      <span class="provider-model">{{ provider.model || '未配置模型' }}</span>
                      <span class="provider-api-base">{{ provider.api_base || '' }}</span>
                    </div>

                    <!-- 配置表单 -->
                    <div v-if="provider._expanded" class="provider-config-form">
                      <label class="form-label">
                        <span>API Base URL</span>
                        <input v-model="provider._edit.api_base" placeholder="https://api.openai.com/v1" />
                      </label>
                      <label class="form-label">
                        <span>API Key</span>
                        <input v-model="provider._edit.api_key" type="password" placeholder="sk-... 留空则无需密钥" />
                      </label>
                      <label class="form-label">
                        <span>模型名称</span>
                        <input v-model="provider._edit.model" placeholder="gpt-4 / deepseek-chat / qwen2.5:7b" />
                      </label>
                      <div class="form-row">
                        <label class="form-label form-label-inline">
                          <span>温度 ({{ provider._edit.temperature }})</span>
                          <input type="range" v-model.number="provider._edit.temperature" class="form-range" min="0" max="2" step="0.05" />
                        </label>
                        <label class="form-label form-label-inline">
                          <span>最大 Tokens</span>
                          <input type="number" v-model.number="provider._edit.max_tokens" class="form-input-narrow" min="128" max="8192" step="128" />
                        </label>
                      </div>
                      <div class="provider-form-actions">
                        <button class="save-btn provider-save-btn" @click="saveProvider(provider)" :disabled="provider._saving">
                          {{ provider._saving ? '保存中...' : '保存' }}
                        </button>
                        <span v-if="provider._saved" class="provider-saved-hint">✅ 已保存</span>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- 添加新 Provider -->
                <button class="add-provider-btn" @click="showAddProvider = !showAddProvider">
                  {{ showAddProvider ? '取消' : '+ 添加 Provider' }}
                </button>

                <!-- 新增 Provider 表单 -->
                <div v-if="showAddProvider" class="add-provider-form">
                  <label class="form-label">
                    <span>名称</span>
                    <input v-model="newProvider.name" placeholder="如: deepseek, local-ollama" />
                  </label>
                  <label class="form-label">
                    <span>API Base URL</span>
                    <input v-model="newProvider.api_base" placeholder="https://api.openai.com/v1" />
                  </label>
                  <label class="form-label">
                    <span>API Key</span>
                    <input v-model="newProvider.api_key" type="password" placeholder="sk-... 留空则无需密钥" />
                  </label>
                  <label class="form-label">
                    <span>模型名称</span>
                    <input v-model="newProvider.model" placeholder="gpt-4 / deepseek-chat" />
                  </label>
                  <div class="form-row">
                    <label class="form-label form-label-inline">
                      <span>温度 ({{ newProvider.temperature }})</span>
                      <input type="range" v-model.number="newProvider.temperature" class="form-range" min="0" max="2" step="0.05" />
                    </label>
                    <label class="form-label form-label-inline">
                      <span>最大 Tokens</span>
                      <input type="number" v-model.number="newProvider.max_tokens" class="form-input-narrow" min="128" max="8192" step="128" />
                    </label>
                  </div>
                  <button class="save-btn" @click="createProvider" :disabled="!newProvider.name || newProvider._creating">
                    {{ newProvider._creating ? '创建中...' : '创建 Provider' }}
                  </button>
                </div>

                <!-- 快速模板：一键填入常见 Provider 的 API 地址和模型 -->
                <div class="provider-templates">
                  <span class="provider-template-label">快速模板：</span>
                  <button class="provider-template-btn" @click="applyProviderTemplate('openai')">🤖 OpenAI</button>
                  <button class="provider-template-btn" @click="applyProviderTemplate('anthropic')">🔮 Anthropic</button>
                  <button class="provider-template-btn" @click="applyProviderTemplate('deepseek')">🌊 DeepSeek</button>
                  <button class="provider-template-btn" @click="applyProviderTemplate('gemini')">🔷 Gemini</button>
                  <button class="provider-template-btn" @click="applyProviderTemplate('groq')">⚡ Groq</button>
                  <button class="provider-template-btn" @click="applyProviderTemplate('together')">🎯 Together</button>
                  <button class="provider-template-btn" @click="applyProviderTemplate('siliconflow')">💠 SiliconFlow</button>
                  <button class="provider-template-btn" @click="applyProviderTemplate('azure')">☁️ Azure</button>
                  <button class="provider-template-btn" @click="applyProviderTemplate('ollama')">🦙 Ollama 本地</button>
                </div>
              </div>
            </div>

            <!-- Tab 3: 语音 — 语音 Provider 配置 -->
            <div v-if="activeTab === 'voice'" class="tab-content">
              <!-- 语音合成模型配置 — 多 Provider 列表管理 -->
              <div class="form-section">
                <h3>
                  语音合成模型配置
                  <span class="section-hint">（管理多个语音合成 Provider，可添加 / 编辑 / 删除，默认使用 zhipu-glm）</span>
                </h3>

                <!-- 语音 Provider 列表 -->
                <div class="provider-list">
                  <div v-for="vp in voiceProviders" :key="vp.name" class="provider-item" :class="{ 'provider-default': vp.enabled }">
                    <div class="provider-header" @click="toggleVoiceProviderExpand(vp)">
                      <div class="provider-info">
                        <span class="provider-name">{{ vp.name }}</span>
                        <span v-if="vp.enabled" class="provider-badge provider-badge-default">当前</span>
                        <span class="provider-model">{{ vp.model || '未配置' }}</span>
                        <span class="provider-voice-tag">{{ vp.voice }}</span>
                      </div>
                      <div class="provider-actions">
                        <span v-if="vp.api_key_configured" class="provider-key-badge">🔑 已配置</span>
                        <span v-else class="provider-key-badge no-key">🔓 无密钥</span>
                        <button class="provider-delete-btn" @click.stop="deleteVoiceProvider(vp)" title="删除此语音 Provider">🗑️</button>
                        <span class="provider-expand-icon">{{ vp._expanded ? '▲' : '▼' }}</span>
                      </div>
                    </div>

                    <!-- 配置表单 -->
                    <div v-if="vp._expanded" class="provider-config-form">
                      <label class="form-label">
                        <span>API Base URL</span>
                        <input v-model="vp._edit.api_base" placeholder="https://open.bigmodel.cn/api/paas/v4" />
                      </label>
                      <label class="form-label">
                        <span>API Key</span>
                        <input v-model="vp._edit.api_key" type="password" placeholder="留空则不修改" />
                      </label>
                      <label class="form-label">
                        <span>模型名称</span>
                        <input v-model="vp._edit.model" placeholder="glm-tts / tts-1 / tts-1-hd" />
                      </label>
                      <!-- 音色类型选择器 -->
                      <label class="form-label">
                        <span>音色类型</span>
                        <div class="voice-type-radio">
                          <label class="voice-type-option" :class="{ active: vp._edit.voice_type === 'preset' }">
                            <input type="radio" v-model="vp._edit.voice_type" value="preset" />
                            <span>预设音色</span>
                          </label>
                          <label class="voice-type-option" :class="{ active: vp._edit.voice_type === 'clone' }">
                            <input type="radio" v-model="vp._edit.voice_type" value="clone" />
                            <span>声音复刻</span>
                          </label>
                        </div>
                      </label>
                      <!-- 预设音色：显示音色下拉选择 -->
                      <template v-if="vp._edit.voice_type === 'preset'">
                        <label class="form-label">
                          <span>语音音色</span>
                          <select v-model="vp._edit.voice" class="form-select">
                            <!-- 智谱 GLM-TTS 音色 -->
                            <option value="female">female（女声，中文优化）</option>
                            <option value="male">male（男声，中文优化）</option>
                            <option value="child">child（童声）</option>
                            <option value="female-wellbeing">female-wellbeing（温暖关怀）</option>
                            <option value="male-journey">male-journey（沉稳叙事）</option>
                            <option value="female-candidate">female-candidate（正式播报）</option>
                            <!-- OpenAI 标准音色 -->
                            <option value="alloy">alloy（中性）</option>
                            <option value="echo">echo（深沉）</option>
                            <option value="fable">fable（柔和）</option>
                            <option value="onyx">onyx（坚定）</option>
                            <option value="nova">nova（温暖）</option>
                            <option value="shimmer">shimmer（明亮）</option>
                          </select>
                        </label>
                      </template>
                      <!-- 声音复刻：显示 clone 配置 -->
                      <template v-if="vp._edit.voice_type === 'clone'">
                        <label class="form-label">
                          <span>复刻音色名称</span>
                          <input v-model="vp._edit.clone_settings.voice_name" placeholder="如: 我的声音" />
                        </label>
                        <label class="form-label">
                          <span>参考音频 URL</span>
                          <input v-model="vp._edit.clone_settings.reference_audio_url" placeholder="https://example.com/sample.wav" />
                        </label>
                        <label class="form-label">
                          <span>参考文本</span>
                          <input v-model="vp._edit.clone_settings.reference_text" placeholder="参考音频中的文本内容" />
                        </label>
                        <label class="form-label">
                          <span>复刻音色 ID</span>
                          <input v-model="vp._edit.clone_settings.clone_voice_id" placeholder="API 返回的克隆音色 ID" />
                        </label>
                      </template>
                      <div class="form-row">
                        <label class="form-label form-label-inline" style="flex: 1">
                          <span>语速 ({{ vp._edit.speed.toFixed(1) }})</span>
                          <input type="range" v-model.number="vp._edit.speed" class="form-range" min="0.5" max="2.0" step="0.1" />
                        </label>
                        <label class="form-label form-label-inline" style="flex: 1">
                          <span>音量 ({{ vp._edit.volume.toFixed(1) }})</span>
                          <input type="range" v-model.number="vp._edit.volume" class="form-range" min="0.5" max="2.0" step="0.1" />
                        </label>
                      </div>
                      <div class="form-row">
                        <label class="form-label form-label-inline" style="flex: 1">
                          <span>音频格式</span>
                          <select v-model="vp._edit.response_format" class="form-select">
                            <option value="pcm">PCM（智谱默认）</option>
                            <option value="mp3">MP3（通用）</option>
                            <option value="wav">WAV</option>
                          </select>
                        </label>
                        <label class="form-label form-label-inline" style="flex: 1">
                          <span>编码格式</span>
                          <select v-model="vp._edit.encode_format" class="form-select">
                            <option value="base64">base64（智谱流式）</option>
                            <option value="raw">raw（原始二进制）</option>
                          </select>
                        </label>
                      </div>
                      <div class="form-row" style="display: flex; justify-content: space-between; align-items: center; margin-top: 8px">
                        <label class="toggle-row" style="margin: 0; padding: 0; gap: 6px">
                          <span class="toggle-label" style="font-size: 12px">设为当前使用</span>
                          <label class="toggle-switch" style="width: 34px; height: 18px">
                            <input type="checkbox" :checked="vp.enabled" @change="setActiveVoiceProvider(vp)" />
                            <span class="toggle-slider" />
                          </label>
                        </label>
                        <div class="provider-form-actions" style="margin: 0">
                          <button class="save-btn provider-save-btn" @click="saveVoiceProvider(vp)" :disabled="vp._saving">
                            {{ vp._saving ? '保存中...' : '保存' }}
                          </button>
                          <span v-if="vp._saved" class="provider-saved-hint">✅ 已保存</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- 添加新语音 Provider -->
                <button class="add-provider-btn" @click="showAddVoiceProvider = !showAddVoiceProvider">
                  {{ showAddVoiceProvider ? '取消' : '+ 添加语音 Provider' }}
                </button>

                <!-- 新增语音 Provider 表单（默认展示智谱 GLM-TTS） -->
                <div v-if="showAddVoiceProvider" class="add-provider-form">
                  <label class="form-label">
                    <span>名称</span>
                    <input v-model="newVoiceProvider.name" placeholder="如: zhipu-glm, openai-tts" />
                  </label>
                  <label class="form-label">
                    <span>API Base URL</span>
                    <input v-model="newVoiceProvider.api_base" placeholder="https://open.bigmodel.cn/api/paas/v4" />
                  </label>
                  <label class="form-label">
                    <span>API Key</span>
                    <input v-model="newVoiceProvider.api_key" type="password" placeholder="sk-..." />
                  </label>
                  <label class="form-label">
                    <span>模型名称</span>
                    <input v-model="newVoiceProvider.model" placeholder="glm-4v-voice" />
                  </label>
                  <!-- 音色类型选择器 -->
                  <label class="form-label">
                    <span>音色类型</span>
                    <div class="voice-type-radio">
                      <label class="voice-type-option" :class="{ active: newVoiceProvider.voice_type === 'preset' }">
                        <input type="radio" v-model="newVoiceProvider.voice_type" value="preset" />
                        <span>预设音色</span>
                      </label>
                      <label class="voice-type-option" :class="{ active: newVoiceProvider.voice_type === 'clone' }">
                        <input type="radio" v-model="newVoiceProvider.voice_type" value="clone" />
                        <span>声音复刻</span>
                      </label>
                    </div>
                  </label>
                  <!-- 预设音色 -->
                  <template v-if="newVoiceProvider.voice_type === 'preset'">
                    <label class="form-label">
                      <span>语音音色</span>
                      <select v-model="newVoiceProvider.voice" class="form-select">
                        <option value="alloy">alloy（中性）</option>
                        <option value="echo">echo（深沉）</option>
                        <option value="fable">fable（柔和）</option>
                        <option value="onyx">onyx（坚定）</option>
                        <option value="nova">nova（温暖）</option>
                        <option value="shimmer">shimmer（明亮）</option>
                      </select>
                    </label>
                  </template>
                  <!-- 声音复刻 -->
                  <template v-if="newVoiceProvider.voice_type === 'clone'">
                    <label class="form-label">
                      <span>复刻音色名称</span>
                      <input v-model="newVoiceProvider.clone_settings.voice_name" placeholder="如: 我的声音" />
                    </label>
                    <label class="form-label">
                      <span>参考音频 URL</span>
                      <input v-model="newVoiceProvider.clone_settings.reference_audio_url" placeholder="https://example.com/sample.wav" />
                    </label>
                    <label class="form-label">
                      <span>参考文本</span>
                      <input v-model="newVoiceProvider.clone_settings.reference_text" placeholder="参考音频中的文本内容" />
                    </label>
                    <label class="form-label">
                      <span>复刻音色 ID</span>
                      <input v-model="newVoiceProvider.clone_settings.clone_voice_id" placeholder="API 返回的克隆音色 ID" />
                    </label>
                  </template>
                  <button class="save-btn" @click="createVoiceProvider" :disabled="!newVoiceProvider.name || newVoiceProvider._creating">
                    {{ newVoiceProvider._creating ? '创建中...' : '创建语音 Provider' }}
                  </button>
                </div>

                <p v-if="voiceProviders.length === 0" class="no-voice-provider">⚠️ 暂无语音 Provider，点击上方按钮添加一个。</p>
              </div>
            </div>

            <!-- Tab 4: 语义识别 — NLU 模型配置（独立于对话用的 Provider） -->
            <div v-if="activeTab === 'nlu'" class="tab-content">
              <!-- 语义识别（NLU）模型配置 — 独立配置，直接输入 -->
              <div class="form-section">
                <h3>
                  语义识别模型配置
                  <span class="section-hint">（配置用于意图识别的大模型，可使用免费本地模型如 Ollama）</span>
                </h3>

                <!-- 当前状态 -->
                <div class="nlu-status-bar">
                  <div class="nlu-status-item">
                    <span class="nlu-status-dot" :class="{ connected: nluConfig._configured }"></span>
                    <span class="nlu-status-label">状态：{{ nluConfig._configured ? '已配置' : '未配置' }}</span>
                  </div>
                  <div class="nlu-status-item" v-if="nluConfig._configured">
                    <span class="nlu-status-label">模型：</span>
                    <span class="nlu-status-value">{{ nluConfig.model || '未设置' }}</span>
                  </div>
                  <div class="nlu-status-item" v-if="nluConfig._configured && nluConfig.api_base">
                    <span class="nlu-status-label">接口：</span>
                    <span class="nlu-status-value nlu-status-url">{{ nluConfig.api_base }}</span>
                  </div>
                </div>

                <!-- 配置表单 -->
                <div class="nlu-config-form">
                  <label class="form-label">
                    <span class="nlu-field-label">API 接口地址</span>
                    <input v-model="nluConfig.api_base" placeholder="http://localhost:11434/v1" class="nlu-input" />
                    <span class="nlu-field-desc">
                      免费推荐：Ollama 本地地址
                      <code>http://localhost:11434/v1</code>
                      ，或使用 DeepSeek 等远程 API
                    </span>
                  </label>
                  <label class="form-label">
                    <span class="nlu-field-label">
                      API Key
                      <span class="nlu-optional">（可选）</span>
                    </span>
                    <input v-model="nluConfig.api_key" type="password" placeholder="免费本地模型可留空" class="nlu-input" />
                    <span class="nlu-field-desc">本地模型（如 Ollama）无需密钥；远程 API 需要填入对应 Key</span>
                  </label>
                  <label class="form-label">
                    <span class="nlu-field-label">模型名称</span>
                    <input v-model="nluConfig.model" placeholder="qwen2.5:7b / deepseek-chat / gpt-4o-mini" class="nlu-input" />
                    <span class="nlu-field-desc">
                      推荐免费模型：
                      <code>qwen2.5:7b</code>
                      （Ollama）、
                      <code>deepseek-chat</code>
                      、
                      <code>gpt-4o-mini</code>
                    </span>
                  </label>
                  <div class="nlu-form-actions">
                    <button class="save-btn" @click="saveNluConfig" :disabled="nluConfig._saving || !nluConfig.api_base">
                      {{ nluConfig._saving ? '保存配置中...' : '保存并应用' }}
                    </button>
                    <span v-if="nluConfig._saved" class="nlu-saved-hint">✅ 配置已保存并生效</span>
                    <span v-if="nluConfig._error" class="nlu-error-hint">❌ {{ nluConfig._error }}</span>
                  </div>
                </div>

                <!-- 快速模板提示 -->
                <div class="nlu-templates">
                  <span class="nlu-template-label">快速模板：</span>
                  <button class="nlu-template-btn" @click="applyNluTemplate('ollama')">🦙 Ollama 本地</button>
                  <button class="nlu-template-btn" @click="applyNluTemplate('deepseek')">🌊 DeepSeek</button>
                  <button class="nlu-template-btn" @click="applyNluTemplate('openai')">🤖 OpenAI</button>
                </div>
              </div>
            </div>

            <!-- Tab 5: 智能体 — 多智能体配置 -->
            <div v-if="activeTab === 'agents'" class="tab-content">
              <!-- 多智能体配置 -->
              <div class="form-section" v-if="agents.length > 0">
                <h3>
                  多智能体配置
                  <span class="section-hint">（每个智能体可指定使用的 Provider 和模型覆盖参数，留空则继承 Provider 的默认配置）</span>
                </h3>
                <div class="agent-list">
                  <div v-for="agent in agents" :key="agent.name" class="agent-item" :class="{ enabled: agent.enabled, specialist: agent.name !== 'coordinator' }">
                    <div class="agent-header">
                      <span class="agent-icon">{{ getAgentIcon(agent.name) }}</span>
                      <span class="agent-name">{{ agent.display_name || agent.name }}</span>
                      <span class="agent-badge" :class="agent.enabled ? 'badge-on' : 'badge-off'">
                        {{ agent.enabled ? '启用' : '禁用' }}
                      </span>
                      <label class="toggle-switch agent-toggle" :class="{ 'toggle-disabled': !agentHasConfig(agent) && !agent.enabled }">
                        <input type="checkbox" :checked="agent.enabled" @change="toggleAgent(agent)" :disabled="!agentHasConfig(agent) && !agent.enabled" />
                        <span class="toggle-slider" />
                      </label>
                    </div>
                    <p class="agent-desc">{{ agent.description || '' }}</p>
                    <div class="agent-meta">
                      <span v-if="agent.model" class="meta-tag">模型: {{ agent.model }}</span>
                      <span v-else class="meta-tag meta-tag-default">模型: 继承 Provider</span>
                      <span v-if="agent.api_base" class="meta-tag">接口: {{ agent.api_base }}</span>
                      <span v-else class="meta-tag meta-tag-default">接口: 继承 Provider</span>
                      <span v-if="agent.name === 'coordinator'" class="meta-tag">路由器</span>
                    </div>

                    <!-- 无模型配置警告 -->
                    <p v-if="!agentHasConfig(agent)" class="agent-config-warning">⚠️ 未指定 Provider，将使用默认接口（default）</p>

                    <!-- 展开/收起按钮 -->
                    <button class="agent-expand-btn" @click="toggleExpand(agent)">
                      {{ agent._expanded ? '收起配置 ▲' : '展开配置 ▼' }}
                    </button>

                    <!-- 配置表单 -->
                    <div v-if="agent._expanded" class="agent-config-form">
                      <!-- Provider 选择器：从已配置的 Provider 列表中选择 -->
                      <div class="form-row">
                        <label class="form-label">使用 Provider</label>
                        <select class="form-select" :value="agent._edit._providerName || ''" @change="onAgentProviderChange(agent, $event.target.value)">
                          <option value="">-- 默认 Provider（模型接口 Tab 中配置）--</option>
                          <option v-for="p in providersForAgent" :key="p.name" :value="p.name">{{ p.name }} ({{ p.model || '未配置' }})</option>
                        </select>
                      </div>
                      <div class="form-row">
                        <label class="form-label">
                          模型（覆盖）
                          <span class="form-label-hint">留空则使用所选 Provider 的默认模型</span>
                        </label>
                        <input class="form-input" v-model="agent._edit.model" placeholder="留空 = 继承 Provider 的模型" />
                      </div>
                      <div class="form-row">
                        <label class="form-label">
                          API Base（覆盖）
                          <span class="form-label-hint">通常留空，只有需要不同接口地址时才填写</span>
                        </label>
                        <input class="form-input" v-model="agent._edit.api_base" placeholder="留空 = 继承 Provider 的接口地址" />
                      </div>
                      <div class="form-row">
                        <label class="form-label">温度（覆盖: {{ agent._edit.temperature || 0.7 }}）</label>
                        <input type="range" v-model.number="agent._edit.temperature" class="form-range" min="0" max="2" step="0.05" />
                      </div>
                      <!-- 性格/风格配置（用户可自定义助理的性格特点） -->
                      <div class="form-row">
                        <label class="form-label">
                          性格特点
                          <span class="form-label-hint">（可选，如：幽默风趣、严谨认真、温柔体贴）</span>
                        </label>
                        <textarea v-model="agent._edit.personality" class="form-textarea" placeholder="例如：你性格幽默风趣，喜欢用轻松的语气说话，偶尔会讲冷笑话。" rows="3"></textarea>
                      </div>
                      <!-- 技能配置：为智能体装配可用技能 -->
                      <div class="form-row">
                        <label class="form-label">
                          装配技能
                          <span class="form-label-hint">（选择该智能体可调用的技能，LLM 将自主决定何时调用）</span>
                        </label>
                        <div class="skill-checkbox-list">
                          <label v-for="skill in skills" :key="skill.name" class="skill-checkbox-item" :class="{ equipped: agent.equipped_skills?.includes(skill.name) }">
                            <input type="checkbox" :checked="agent.equipped_skills?.includes(skill.name)" @change="toggleAgentSkill(agent, skill.name)" />
                            <span class="skill-checkbox-name">{{ skill.display_name }}</span>
                            <span class="skill-checkbox-desc">{{ skill.description }}</span>
                          </label>
                          <p v-if="skills.length === 0" class="skill-empty-hint">暂无可装配的技能</p>
                        </div>
                      </div>
                      <div class="form-row" style="display: flex; justify-content: flex-end; align-items: center; gap: 8px">
                        <span v-if="agent._saved" class="agent-saved-hint">✅ 已保存</span>
                        <button class="save-agent-btn" @click="saveAgentConfig(agent)" :disabled="agent._saving">
                          {{ agent._saving ? '保存中...' : '保存配置' }}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Tab 5: 性格 — 全局 AI 性格配置 -->
            <div v-if="activeTab === 'personality'" class="tab-content">
              <div class="form-section">
                <h3>
                  全局 AI 性格
                  <span class="section-hint">（自定义 AI 助手的性格特点，将应用于所有智能体）</span>
                </h3>
                <p class="section-desc">
                  你希望 AI 助手以什么样的性格与你交流？写下性格描述后点击"保存性格"。
                </p>

                <!-- 性格预设快速选择 -->
                <div class="preset-section">
                  <label class="form-label">快速选择性格预设</label>
                  <div class="preset-buttons">
                    <button
                      v-for="preset in personalityPresets"
                      :key="preset.label"
                      class="preset-btn"
                      :class="{ active: assistantPersonality === preset.value }"
                      @click="selectPreset(preset)"
                    >
                      {{ preset.label }}
                    </button>
                  </div>
                </div>

                <!-- 自定义性格输入 -->
                <div class="form-row">
                  <label class="form-label">
                    自定义性格描述
                    <span class="form-label-hint">（详细描述你希望 AI 表现出的性格特质）</span>
                  </label>
                  <textarea
                    v-model="assistantPersonality"
                    class="form-textarea personality-textarea"
                    placeholder="例如：你性格温柔体贴，语气亲切友善，说话时像一位知心朋友。你善于倾听，懂得共情，在回答问题时既能展现专业性，又不会显得冰冷生硬。"
                    rows="5"
                  ></textarea>
                </div>

                <!-- 操作按钮 -->
                <div class="form-row" style="display: flex; justify-content: flex-end; align-items: center; gap: 8px">
                  <span v-if="saveSuccess" class="save-success-hint">✅ 性格配置已保存</span>
                  <span v-if="assistantPersonality !== (config.assistant_personality || '')" class="unsaved-hint">⚠️ 未保存</span>
                  <button class="save-agent-btn" @click="savePersonality" :disabled="saving">
                    {{ saving ? '保存中...' : '保存性格' }}
                  </button>
                </div>

                <!-- 提示信息 -->
                <div class="personality-info">
                  <p>💡 配置的性格将自动注入到所有智能体的系统提示词中，影响 AI 助手的回答风格和语气。即使切换不同智能体，性格设定也会保持一致。</p>
                </div>
              </div>
            </div>

            <!-- Tab 6: 外观 — 月夜单主题 -->
            <div v-if="activeTab === 'appearance'" class="tab-content">
              <div class="form-section">
                <h3>主题模式</h3>
                <p class="section-desc">当前版本采用「月夜 · 明珠」暗色主题</p>
                <div class="theme-static">
                  <span class="theme-static-seal">玥</span>
                  <p>深潭墨蓝为底，月光暖金为魂，青瓷冷绿为客。</p>
                </div>
              </div>
            </div>

            <!-- 操作按钮 -->
            <div class="action-row">
              <button class="save-btn" @click="saveDialogueToggle" :disabled="saving">
                {{ saving ? '保存中...' : '保存开关设置' }}
              </button>
              <button class="close-btn" @click="$emit('close')">关闭</button>
            </div>

            <!-- 保存成功提示 -->
            <Transition name="fade">
              <p v-if="saveSuccess" class="save-success">✅ 设置已保存</p>
            </Transition>

            <!-- 错误信息 -->
            <Transition name="fade">
              <p v-if="error" class="error-msg">{{ error }}</p>
            </Transition>
          </template>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
/**
 * VoiceConfig.vue — 语音助手配置面板
 *
 * 弹窗式设置面板，允许用户管理：
 * - LLM Provider（接口地址、Key、模型等）
 * - 语音对话功能开关
 * - 多智能体配置
 *
 * 所有 Provider 通过独立 CRUD API 管理，不再有"本地/远程"自动切换。
 */
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'

/** 发射事件：关闭配置面板 */
const emit = defineEmits(['close'])

// ============================================================
// API 路径
// ============================================================

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const SETTINGS_API = `${API_BASE}/api/v1/settings`
const PROVIDERS_API = `${API_BASE}/api/v1/providers`
const AGENTS_API = `${API_BASE}/api/v1/agents`
const VOICE_PROVIDERS_API = `${API_BASE}/api/v1/voice-providers`
const SKILLS_API = `${API_BASE}/api/v1/skills`

/** API Key 掩码占位符 — 已配置 Key 时展示此值，不暴露真实密钥 */
const API_KEY_MASK = '*'.repeat(16)

// ============================================================
// 状态
// ============================================================

const loading = ref(true)
const saving = ref(false)
const backendReachable = ref(false)
const saveSuccess = ref(false)
const error = ref('')

/** 当前激活的 Tab */
const activeTab = ref('overview')

/** Tab 导航定义 */
const tabs = [
  { id: 'overview', label: '概览', icon: '📊' },
  { id: 'providers', label: '模型接口', icon: '🔌' },
  { id: 'voice', label: '语音', icon: '🎤' },
  { id: 'nlu', label: '语义识别', icon: '🧠' },
  { id: 'agents', label: '智能体', icon: '🤖' },
  { id: 'personality', label: '性格', icon: '🎭' },
  { id: 'appearance', label: '外观', icon: '🎨' }
]

// ============================================================
// 主题 — 「月夜 · 明珠」单暗色主题，无需切换逻辑
// ============================================================

/** 运行时配置（来自后端） */
const config = reactive({
  enable_voice_dialogue: true,
  voice_dialogue_ready: true,
  default_provider: null
})

/** 语音对话功能开关 */
const enableVoiceDialogue = ref(true)

/** 全局 AI 性格配置 */
const assistantPersonality = ref('')

/** 性格预设模板 */
const personalityPresets = [
  { label: '温柔友善', value: '你性格温柔体贴，语气亲切友善，像一位知心朋友一样与用户交流。' },
  { label: '专业严谨', value: '你性格专业严谨，回答问题时逻辑清晰、精确可靠，像一位资深专家。' },
  { label: '幽默风趣', value: '你性格幽默风趣，喜欢用轻松诙谐的语气说话，偶尔会讲一些有趣的段子。' },
  { label: '热情活泼', value: '你性格热情活泼，充满活力，用积极向上的态度与用户互动，让人感到愉快。' },
  { label: '冷静理性', value: '你性格冷静理性，客观中立，注重事实和逻辑分析，不带情感倾向。' },
]

/**
 * NLU 语义识别模型配置（独立配置，无需先在 Provider 列表中创建）
 * 保存时会自动创建/更新名为 "nlu-model" 的 Provider 并绑定
 */
const nluConfig = reactive({
  api_base: '',
  api_key: '',
  model: '',
  _saving: false,
  _saved: false,
  _error: '',
  _configured: false // 后端是否存在已配置的 nlu-model Provider
})

/** 语音 Provider 列表（含前端附加状态） */
const voiceProviders = ref([])

/** 是否显示新增语音 Provider 表单 */
const showAddVoiceProvider = ref(false)

/** 新增语音 Provider 表单数据（默认智谱 GLM-TTS 配置） */
const newVoiceProvider = reactive({
  name: 'zhipu-glm',
  api_base: 'https://open.bigmodel.cn/api/paas/v4',
  api_key: '',
  model: 'glm-tts',
  voice: 'female',
  voice_type: 'preset', // 'preset' | 'clone'
  clone_settings: {
    reference_audio_url: '',
    reference_text: '',
    clone_voice_id: '',
    voice_name: ''
  },
  response_format: 'pcm',
  encode_format: 'base64',
  speed: 1.0,
  volume: 1.0,
  _creating: false
})

/** Provider 列表（含前端附加状态） */
const providers = ref([])

/** 是否显示新增 Provider 表单 */
const showAddProvider = ref(false)

/** 新增 Provider 表单数据 */
const newProvider = reactive({
  name: '',
  api_base: 'https://api.openai.com/v1',
  api_key: '',
  model: 'gpt-3.5-turbo',
  temperature: 0.7,
  max_tokens: 2048,
  _creating: false
})

/** @type {Ref<Array>} 智能体列表 */
const agents = ref([])

/** @type {Ref<Array>} 技能列表 */
const skills = ref([])

/** 已启用的智能体数量 */
const enabledAgentCount = computed(() => {
  return agents.value.filter(a => a.enabled).length
})

/** 可用于智能体的 Provider 列表（排除 nlu-model） */
const providersForAgent = computed(() => {
  return providers.value.filter(p => p.name !== 'nlu-model')
})

// ============================================================
// 计算属性
// ============================================================

/** 默认 Provider 的模型显示文本 */
const defaultModelDisplay = computed(() => {
  const dp = config.default_provider
  if (!dp) return '未配置'
  return dp.api_key_configured ? dp.model || '远程模型' : dp.model || '本地模型'
})

// ============================================================
// Provider 管理
// ============================================================

/**
 * 加载所有 Provider 列表
 */
async function loadProviders() {
  try {
    const resp = await fetch(PROVIDERS_API)
    if (!resp.ok) return
    const data = await resp.json()
    providers.value = (data.providers || []).map(p => ({
      ...p,
      _expanded: p.name === 'default', // 默认展开
      _saving: false,
      _saved: false,
      _edit: {
        api_base: p.api_base || '',
        // 如果已配置 Key 则用占位符展示，不暴露真实密钥
        api_key: p.api_key_configured ? API_KEY_MASK : '',
        model: p.model || '',
        max_tokens: p.max_tokens ?? 2048,
        temperature: p.temperature ?? 0.7
      }
    }))
  } catch (e) {
    console.warn('[Config] 加载 Provider 失败:', e.message)
  }
}

/**
 * 展开/收起 Provider 配置表单
 */
function toggleProviderExpand(provider) {
  provider._expanded = !provider._expanded
  if (provider._expanded) {
    // 展开时同步最新数据到编辑副本
    provider._edit.api_base = provider.api_base || ''
    // 如果已配置 Key 则用占位符展示，不暴露真实密钥
    provider._edit.api_key = provider.api_key_configured ? API_KEY_MASK : ''
    provider._edit.model = provider.model || ''
    provider._edit.max_tokens = provider.max_tokens ?? 2048
    provider._edit.temperature = provider.temperature ?? 0.7
    provider._saved = false
  }
}

/**
 * 保存单个 Provider 配置
 */
async function saveProvider(provider) {
  provider._saving = true
  provider._saved = false
  try {
    const payload = {
      name: provider.name,
      api_base: provider._edit.api_base || provider.api_base,
      // 如果输入的是掩码占位符，说明用户未修改 Key，传空让后端保留原有值
      api_key: provider._edit.api_key === API_KEY_MASK ? '' : provider._edit.api_key || '',
      model: provider._edit.model || '',
      max_tokens: provider._edit.max_tokens,
      temperature: provider._edit.temperature
    }

    const resp = await fetch(`${PROVIDERS_API}/${provider.name}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })

    if (!resp.ok) {
      const errData = await resp.json().catch(() => ({}))
      throw new Error(errData.detail || `HTTP ${resp.status}`)
    }

    const result = await resp.json()
    // 同步到 provider 对象
    provider.api_base = result.api_base
    provider.model = result.model
    provider.api_key_configured = result.api_key_configured
    // 保存后同步 _edit.api_key：已配置 → 占位符，否则置空
    provider._edit.api_key = result.api_key_configured ? API_KEY_MASK : ''

    // 同步到 config.default_provider（如果是 default）
    if (provider.name === 'default' && config.default_provider) {
      config.default_provider.api_base = result.api_base
      config.default_provider.model = result.model
      config.default_provider.api_key_configured = result.api_key_configured
    }

    provider._saved = true
    setTimeout(() => {
      provider._saved = false
    }, 3000)
  } catch (e) {
    console.warn('[Config] 保存 Provider 失败:', e.message)
    alert(`保存 Provider "${provider.name}" 失败: ${e.message}`)
  } finally {
    provider._saving = false
  }
}

/**
 * 创建新的 Provider
 */
async function createProvider() {
  if (!newProvider.name) return
  newProvider._creating = true
  try {
    const resp = await fetch(PROVIDERS_API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: newProvider.name,
        api_base: newProvider.api_base,
        api_key: newProvider.api_key,
        model: newProvider.model,
        max_tokens: newProvider.max_tokens,
        temperature: newProvider.temperature
      })
    })

    if (!resp.ok) {
      const errData = await resp.json().catch(() => ({}))
      throw new Error(errData.detail || `HTTP ${resp.status}`)
    }

    await loadProviders()
    // 创建成功后，重新匹配所有已展开的智能体的 Provider（同步更新 _providerName）
    agents.value.forEach(agent => {
      if (agent._expanded) {
        agent._edit._providerName = matchProviderByApiBase(agent._edit.api_base)
      }
    })
    showAddProvider.value = false
    // 重置表单
    newProvider.name = ''
    newProvider.api_base = 'https://api.openai.com/v1'
    newProvider.api_key = ''
    newProvider.model = 'gpt-3.5-turbo'
  } catch (e) {
    console.warn('[Config] 创建 Provider 失败:', e.message)
    alert(`创建 Provider 失败: ${e.message}`)
  } finally {
    newProvider._creating = false
  }
}

/**
 * 快速模板：一键填入常用 Provider 配置
 * 支持 OpenAI / Anthropic / DeepSeek / Ollama 等主流服务商
 */
function applyProviderTemplate(template) {
  const templates = {
    openai: { api_base: 'https://api.openai.com/v1', api_key: '', model: 'gpt-4o' },
    anthropic: { api_base: 'https://api.anthropic.com/v1', api_key: '', model: 'claude-sonnet-4-20250514' },
    deepseek: { api_base: 'https://api.deepseek.com/v1', api_key: '', model: 'deepseek-chat' },
    gemini: { api_base: 'https://generativelanguage.googleapis.com/v1beta/openai', api_key: '', model: 'gemini-2.0-flash' },
    groq: { api_base: 'https://api.groq.com/openai/v1', api_key: '', model: 'llama-3.3-70b-versatile' },
    together: { api_base: 'https://api.together.xyz/v1', api_key: '', model: 'meta-llama/Llama-3.3-70B-Instruct-Turbo' },
    siliconflow: { api_base: 'https://api.siliconflow.cn/v1', api_key: '', model: 'Qwen/Qwen2.5-7B-Instruct' },
    azure: { api_base: 'https://YOUR_RESOURCE.openai.azure.com', api_key: '', model: 'gpt-4o' },
    ollama: { api_base: 'http://localhost:11434/v1', api_key: '', model: 'qwen2.5:7b' }
  }
  const tpl = templates[template]
  if (!tpl) return

  // 填入新增表单
  newProvider.api_base = tpl.api_base
  newProvider.api_key = tpl.api_key
  newProvider.model = tpl.model
  newProvider.name = template === 'openai' ? 'default' : template

  // 同时填入第一个 Provider（default）的编辑表单（如果已展开）
  const defaultProvider = providers.value.find(p => p.name === 'default')
  if (defaultProvider && defaultProvider._expanded) {
    defaultProvider._edit.api_base = tpl.api_base
    defaultProvider._edit.api_key = tpl.api_key
    defaultProvider._edit.model = tpl.model
  }
}

/**
 * 根据 API Base 自动识别 Provider 类型并返回对应的 emoji 图标
 */
function getProviderIcon(apiBase) {
  if (!apiBase) return '☁️'
  const url = apiBase.toLowerCase()
  if (url.includes('openai.com')) return '🤖'
  if (url.includes('anthropic.com')) return '🔮'
  if (url.includes('deepseek')) return '🌊'
  if (url.includes('google') || url.includes('generativelanguage')) return '🔷'
  if (url.includes('groq')) return '⚡'
  if (url.includes('together')) return '🎯'
  if (url.includes('siliconflow')) return '💠'
  if (url.includes('azure')) return '☁️'
  if (url.includes('localhost') || url.includes('127.0.0.1')) return '🦙'
  if (url.includes('openbigmodel') || url.includes('bigmodel')) return '🧪'
  if (url.includes('moonshot') || url.includes('kimi')) return '🌙'
  if (url.includes('zhipu') || url.includes('glm')) return '🔵'
  if (url.includes('baidu') || url.includes('qianfan')) return '📘'
  if (url.includes('aliyun') || url.includes('tongyi') || url.includes('dashscope')) return '🟠'
  return '☁️'
}

/**
 * 删除 Provider
 */
async function deleteProvider(provider) {
  if (!confirm(`确定要删除 Provider "${provider.name}" 吗？`)) return
  try {
    const resp = await fetch(`${PROVIDERS_API}/${provider.name}`, {
      method: 'DELETE'
    })

    if (!resp.ok) {
      const errData = await resp.json().catch(() => ({}))
      throw new Error(errData.detail || `HTTP ${resp.status}`)
    }

    await loadProviders()
  } catch (e) {
    console.warn('[Config] 删除 Provider 失败:', e.message)
    alert(`删除 Provider 失败: ${e.message}`)
  }
}

// ============================================================
// 检查后端服务状态
// ============================================================

async function checkBackend() {
  try {
    const resp = await fetch(SETTINGS_API)
    if (resp.ok) {
      backendReachable.value = true
      return true
    }
  } catch {
    // 后端不可达
  }
  backendReachable.value = false
  return false
}

// ============================================================
// 加载配置
// ============================================================

async function loadConfig() {
  loading.value = true
  error.value = ''

  try {
    const reachable = await checkBackend()
    if (!reachable) {
      loading.value = false
      return
    }

    const resp = await fetch(SETTINGS_API)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)

    const data = await resp.json()
    Object.assign(config, data)
    enableVoiceDialogue.value = data.enable_voice_dialogue
    assistantPersonality.value = data.assistant_personality || ''

    // 加载 Provider 列表
    await loadProviders()

    // 检测 NLU 专用 Provider 是否已配置
    const nluProvider = providers.value.find(p => p.name === 'nlu-model')
    if (nluProvider) {
      nluConfig.api_base = nluProvider.api_base || ''
      nluConfig.model = nluProvider.model || ''
      nluConfig._configured = true
    } else {
      nluConfig.api_base = ''
      nluConfig.api_key = ''
      nluConfig.model = ''
      nluConfig._configured = false
    }

    // 加载智能体列表
    await loadAgents()

    // 加载技能列表
    await loadSkills()

    // 加载语音 Provider
    await loadVoiceProvider()
  } catch (e) {
    error.value = `无法加载配置: ${e.message}`
  } finally {
    loading.value = false
  }
}

// ============================================================
// 保存语音对话开关（独立保存，不涉及 Provider）
// ============================================================

async function saveDialogueToggle() {
  saving.value = true
  error.value = ''
  saveSuccess.value = false

  try {
    const body = {
      enable_voice_dialogue: enableVoiceDialogue.value
    }

    const resp = await fetch(SETTINGS_API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })

    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)

    const data = await resp.json()
    Object.assign(config, data)

    saveSuccess.value = true
    setTimeout(() => {
      saveSuccess.value = false
    }, 3000)
  } catch (e) {
    error.value = `保存失败: ${e.message}`
  } finally {
    saving.value = false
  }
}

/** 选择性格预设 */
function selectPreset(preset) {
  assistantPersonality.value = preset.value
}

/** 保存性格配置 */
async function savePersonality() {
  saving.value = true
  error.value = ''
  saveSuccess.value = false

  try {
    const body = {
      assistant_personality: assistantPersonality.value
    }

    const resp = await fetch(SETTINGS_API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })

    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)

    const data = await resp.json()
    Object.assign(config, data)

    saveSuccess.value = true
    setTimeout(() => {
      saveSuccess.value = false
    }, 3000)
  } catch (e) {
    error.value = `保存性格配置失败: ${e.message}`
  } finally {
    saving.value = false
  }
}

// ============================================================
// 语义识别（NLU）模型配置 — 独立保存
// ============================================================

/**
 * 保存 NLU 语义识别模型配置
 *
 * 自动创建/更新名为 "nlu-model" 的 Provider，并绑定到语义识别功能。
 * 用户无需先在 Provider 列表中创建，直接填写即可生效。
 */
async function saveNluConfig() {
  nluConfig._saving = true
  nluConfig._saved = false
  nluConfig._error = ''

  try {
    // 第一步：创建/更新名为 "nlu-model" 的 Provider
    const providerPayload = {
      name: 'nlu-model',
      api_base: nluConfig.api_base,
      api_key: nluConfig.api_key,
      model: nluConfig.model,
      max_tokens: 2048,
      temperature: 0.3 // NLU 使用较低温度以获得更确定的结果
    }

    // 尝试 PATCH 更新（Provider 已存在），失败则 POST 创建
    let providerResp = await fetch(`${PROVIDERS_API}/nlu-model`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(providerPayload)
    })

    if (!providerResp.ok && providerResp.status === 404) {
      // Provider 不存在，创建新的
      providerResp = await fetch(PROVIDERS_API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(providerPayload)
      })
    }

    if (!providerResp.ok) {
      const errData = await providerResp.json().catch(() => ({}))
      throw new Error(errData.detail || `HTTP ${providerResp.status}`)
    }

    // 第二步：设置 nlu_provider_name 指向 nlu-model
    const settingsResp = await fetch(SETTINGS_API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nlu_provider_name: 'nlu-model' })
    })

    if (!settingsResp.ok) {
      throw new Error(`设置 NLU Provider 失败: HTTP ${settingsResp.status}`)
    }

    // 更新状态
    nluConfig._configured = true
    nluConfig._saved = true
    setTimeout(() => {
      nluConfig._saved = false
    }, 3000)

    // 刷新 Provider 列表
    await loadProviders()

    console.log('[NLU] 语义识别模型配置已保存:', nluConfig.api_base, nluConfig.model)
  } catch (e) {
    nluConfig._error = e.message
    console.warn('[NLU] 保存配置失败:', e.message)
    setTimeout(() => {
      nluConfig._error = ''
    }, 5000)
  } finally {
    nluConfig._saving = false
  }
}

/**
 * 快速填入常用 NLU 模型模板
 */
function applyNluTemplate(template) {
  const templates = {
    ollama: {
      api_base: 'http://localhost:11434/v1',
      api_key: '',
      model: 'qwen2.5:7b'
    },
    deepseek: {
      api_base: 'https://api.deepseek.com/v1',
      api_key: '',
      model: 'deepseek-chat'
    },
    openai: {
      api_base: 'https://api.openai.com/v1',
      api_key: '',
      model: 'gpt-4o-mini'
    }
  }
  const tpl = templates[template]
  if (tpl) {
    nluConfig.api_base = tpl.api_base
    nluConfig.api_key = tpl.api_key
    nluConfig.model = tpl.model
  }
}

// ============================================================
// 语音 Provider 管理
// ============================================================

/**
 * 加载所有语音 Provider 列表
 */
async function loadVoiceProvider() {
  try {
    const resp = await fetch(VOICE_PROVIDERS_API)
    if (!resp.ok) return
    const data = await resp.json()
    voiceProviders.value = (data.providers || []).map(vp => ({
      ...vp,
      _expanded: false,
      _saving: false,
      _saved: false,
      _edit: {
        api_base: vp.api_base || '',
        api_key: '',
        model: vp.model || '',
        voice: vp.voice || 'female',
        voice_type: vp.voice_type || 'preset',
        clone_settings: { ...(vp.clone_settings || { reference_audio_url: '', reference_text: '', clone_voice_id: '', voice_name: '' }) },
        response_format: vp.response_format || 'pcm',
        encode_format: vp.encode_format || 'base64',
        speed: vp.speed ?? 1.0,
        volume: vp.volume ?? 1.0
      }
    }))
  } catch (e) {
    console.warn('[Config] 加载语音 Provider 列表失败:', e.message)
  }
}

/**
 * 保存语音 Provider 配置（参数为列表中的单个 Provider）
 */
async function saveVoiceProvider(vp) {
  vp._saving = true
  vp._saved = false
  try {
    const payload = {
      name: vp.name,
      api_base: vp._edit.api_base,
      api_key: vp._edit.api_key,
      model: vp._edit.model,
      voice: vp._edit.voice,
      voice_type: vp._edit.voice_type,
      clone_settings: vp._edit.clone_settings,
      response_format: vp._edit.response_format,
      encode_format: vp._edit.encode_format,
      speed: vp._edit.speed,
      volume: vp._edit.volume,
      enabled: vp.enabled
    }

    const resp = await fetch(`${VOICE_PROVIDERS_API}/${vp.name}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })

    if (!resp.ok) {
      const errData = await resp.json().catch(() => ({}))
      throw new Error(errData.detail || `HTTP ${resp.status}`)
    }

    const result = await resp.json()
    // 同步更新到列表
    vp.api_base = result.api_base
    vp.model = result.model
    vp.voice = result.voice
    vp.api_key_configured = result.api_key_configured

    vp._saved = true
    setTimeout(() => {
      vp._saved = false
    }, 3000)
    // 刷新列表以同步状态
    await loadVoiceProvider()
  } catch (e) {
    console.warn('[Config] 保存语音 Provider 失败:', e.message)
    alert(`保存语音 Provider 失败: ${e.message}`)
  } finally {
    vp._saving = false
  }
}

/**
 * 展开 / 收起语音 Provider 配置表单
 */
function toggleVoiceProviderExpand(vp) {
  vp._expanded = !vp._expanded
  if (vp._expanded) {
    vp._edit.api_base = vp.api_base || ''
    vp._edit.api_key = ''
    vp._edit.model = vp.model || ''
    vp._edit.voice = vp.voice || 'female'
    vp._edit.voice_type = vp.voice_type || 'preset'
    vp._edit.clone_settings = { ...(vp.clone_settings || { reference_audio_url: '', reference_text: '', clone_voice_id: '', voice_name: '' }) }
    vp._edit.response_format = vp.response_format || 'pcm'
    vp._edit.encode_format = vp.encode_format || 'base64'
    vp._edit.speed = vp.speed ?? 1.0
    vp._edit.volume = vp.volume ?? 1.0
    vp._saved = false
  }
}

/**
 * 创建新语音 Provider（默认智谱 GLM-TTS）
 */
async function createVoiceProvider() {
  newVoiceProvider._creating = true
  try {
    const payload = {
      name: newVoiceProvider.name,
      api_base: newVoiceProvider.api_base,
      api_key: newVoiceProvider.api_key,
      model: newVoiceProvider.model,
      voice: newVoiceProvider.voice,
      voice_type: newVoiceProvider.voice_type,
      clone_settings: newVoiceProvider.clone_settings,
      response_format: newVoiceProvider.response_format,
      encode_format: newVoiceProvider.encode_format,
      speed: newVoiceProvider.speed,
      volume: newVoiceProvider.volume,
      enabled: true
    }

    const resp = await fetch(VOICE_PROVIDERS_API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })

    if (!resp.ok) {
      const errData = await resp.json().catch(() => ({}))
      throw new Error(errData.detail || `HTTP ${resp.status}`)
    }

    await loadVoiceProvider()
    showAddVoiceProvider.value = false
    // 重置为 GLM-TTS 默认值
    newVoiceProvider.name = 'zhipu-glm'
    newVoiceProvider.api_base = 'https://open.bigmodel.cn/api/paas/v4'
    newVoiceProvider.api_key = ''
    newVoiceProvider.model = 'glm-tts'
    newVoiceProvider.voice = 'female'
    newVoiceProvider.voice_type = 'preset'
    newVoiceProvider.clone_settings = { reference_audio_url: '', reference_text: '', clone_voice_id: '', voice_name: '' }
    newVoiceProvider.response_format = 'pcm'
    newVoiceProvider.encode_format = 'base64'
    newVoiceProvider.speed = 1.0
    newVoiceProvider.volume = 1.0
  } catch (e) {
    console.warn('[Config] 创建语音 Provider 失败:', e.message)
    alert(`创建语音 Provider 失败: ${e.message}`)
  } finally {
    newVoiceProvider._creating = false
  }
}

/**
 * 删除语音 Provider
 */
async function deleteVoiceProvider(vp) {
  if (!confirm(`确定要删除语音 Provider "${vp.name}" 吗？`)) return
  try {
    const resp = await fetch(`${VOICE_PROVIDERS_API}/${vp.name}`, {
      method: 'DELETE'
    })
    if (!resp.ok) {
      const errData = await resp.json().catch(() => ({}))
      throw new Error(errData.detail || `HTTP ${resp.status}`)
    }
    await loadVoiceProvider()
  } catch (e) {
    console.warn('[Config] 删除语音 Provider 失败:', e.message)
    alert(`删除语音 Provider 失败: ${e.message}`)
  }
}

/**
 * 设置当前启用的语音 Provider
 * 取消其他 Provider 的启用状态，只启用当前选中的
 */
async function setActiveVoiceProvider(vp) {
  const newEnabled = !vp.enabled
  // 先取消所有 Provider 的启用
  for (const p of voiceProviders.value) {
    if (p.name !== vp.name && p.enabled) {
      p.enabled = false
    }
  }
  vp.enabled = newEnabled
  // 保存到后端
  try {
    const payload = {
      name: vp.name,
      api_base: vp.api_base,
      api_key: '',
      model: vp.model,
      voice: vp.voice,
      voice_type: vp.voice_type || 'preset',
      clone_settings: vp.clone_settings || {},
      response_format: vp.response_format || 'pcm',
      encode_format: vp.encode_format || 'base64',
      speed: vp.speed ?? 1.0,
      volume: vp.volume ?? 1.0,
      enabled: vp.enabled
    }
    const resp = await fetch(`${VOICE_PROVIDERS_API}/${vp.name}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    if (!resp.ok) {
      console.warn('[Config] 切换语音 Provider 失败')
      // 刷新回后端状态
      await loadVoiceProvider()
    } else {
      // 刷新同步所有 Provider 状态
      await loadVoiceProvider()
    }
  } catch (e) {
    console.warn('[Config] 切换语音 Provider 失败:', e.message)
    await loadVoiceProvider()
  }
}

// ============================================================
// 加载智能体列表
// ============================================================

async function loadAgents() {
  try {
    const resp = await fetch(AGENTS_API)
    if (!resp.ok) return
    const data = await resp.json()
    // 为每个智能体添加前端状态（_expanded, _edit, _saving, _saved）
    agents.value = (data.agents || []).map(a => ({
      ...a,
      _expanded: false,
      _saving: false,
      _saved: false,
      _edit: {
        model: a.model || '',
        api_base: a.api_base || '',
        temperature: a.temperature ?? 0.7,
        max_tokens: a.max_tokens ?? 2048,
        personality: a.personality || '',
        // 根据 api_base 自动匹配关联的 Provider
        _providerName: matchProviderByApiBase(a.api_base)
      }
    }))
  } catch (e) {
    console.warn('[Config] 加载智能体列表失败:', e.message)
  }
}

// ============================================================
// 加载技能列表
// ============================================================

async function loadSkills() {
  try {
    const resp = await fetch(SKILLS_API)
    if (!resp.ok) return
    const data = await resp.json()
    skills.value = data.skills || []
  } catch (e) {
    console.warn('[Config] 加载技能列表失败:', e.message)
  }
}

// ============================================================
// 切换智能体启用状态
// ============================================================

async function toggleAgent(agent) {
  const newEnabled = !agent.enabled
  agent.enabled = newEnabled
  try {
    const resp = await fetch(`${AGENTS_API}/${agent.name}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: newEnabled })
    })
    if (!resp.ok) {
      // 回退
      agent.enabled = !newEnabled
      // 尝试获取后端详细错误
      try {
        const errData = await resp.json()
        console.warn('[Config] 切换智能体状态失败:', errData.detail || resp.statusText)
        if (resp.status === 400) {
          alert(errData.detail || '配置不完整，无法启用')
        }
      } catch {
        console.warn('[Config] 切换智能体状态失败: HTTP', resp.status)
      }
    }
  } catch (e) {
    agent.enabled = !newEnabled
    console.warn('[Config] 切换智能体状态失败:', e.message)
  }
}

// ============================================================
// 切换智能体技能装配
// ============================================================

async function toggleAgentSkill(agent, skillName) {
  // 获取当前已装配的技能列表
  const current = agent.equipped_skills || []
  let updated

  if (current.includes(skillName)) {
    // 移除技能
    updated = current.filter(s => s !== skillName)
  } else {
    // 添加技能
    updated = [...current, skillName]
  }

  // 乐观更新前端状态
  agent.equipped_skills = updated

  try {
    const resp = await fetch(`${AGENTS_API}/${agent.name}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ equipped_skills: updated })
    })
    if (!resp.ok) {
      // 回退
      agent.equipped_skills = current
      console.warn('[Config] 更新技能装配失败: HTTP', resp.status)
    }
  } catch (e) {
    agent.equipped_skills = current
    console.warn('[Config] 更新技能装配失败:', e.message)
  }
}

// ============================================================
// 展开/收起智能体配置表单
// ============================================================

/**
 * 根据 api_base 自动匹配关联的 Provider 名称
 * @param {string} apiBase - 智能体配置的 api_base
 * @returns {string} 匹配到的 Provider 名称，未匹配返回空字符串
 */
function matchProviderByApiBase(apiBase) {
  if (!apiBase) return ''
  const provider = providers.value.find(p => p.api_base && p.api_base === apiBase && p.name !== 'nlu-model')
  return provider ? provider.name : ''
}

function onAgentProviderChange(agent, providerName) {
  agent._edit._providerName = providerName
  if (providerName) {
    const provider = providers.value.find(p => p.name === providerName)
    if (provider) {
      agent._edit.model = provider.model || ''
      agent._edit.api_base = provider.api_base || ''
    }
  }
}

function toggleExpand(agent) {
  agent._expanded = !agent._expanded
  if (agent._expanded) {
    // 展开时同步最新数据到编辑副本
    agent._edit.model = agent.model || ''
    agent._edit.api_base = agent.api_base || ''
    agent._edit.temperature = agent.temperature ?? 0.7
    agent._edit.max_tokens = agent.max_tokens ?? 2048
    agent._edit.personality = agent.personality || ''
    // 根据 api_base 自动匹配关联的 Provider
    agent._edit._providerName = matchProviderByApiBase(agent.api_base)
    agent._saved = false
  }
}

// ============================================================
// 保存单个智能体配置
// ============================================================

async function saveAgentConfig(agent) {
  agent._saving = true
  agent._saved = false
  try {
    const payload = {}
    // 只发送有变化的字段
    if (agent._edit.model !== (agent.model || '')) payload.model = agent._edit.model || null
    if (agent._edit.api_base !== (agent.api_base || '')) payload.api_base = agent._edit.api_base || null
    if (agent._edit.temperature !== agent.temperature) payload.temperature = agent._edit.temperature
    if (agent._edit.max_tokens !== agent.max_tokens) payload.max_tokens = agent._edit.max_tokens
    if (agent._edit.personality !== (agent.personality || '')) payload.personality = agent._edit.personality

    if (Object.keys(payload).length === 0) {
      agent._saving = false
      agent._saved = true
      setTimeout(() => {
        agent._saved = false
      }, 2000)
      return
    }

    const resp = await fetch(`${AGENTS_API}/${agent.name}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })

    if (!resp.ok) {
      const errData = await resp.json().catch(() => ({}))
      throw new Error(errData.detail || `HTTP ${resp.status}`)
    }

    // 更新同步到 agent 对象
    agent.model = agent._edit.model || ''
    agent.api_base = agent._edit.api_base || ''
    agent.temperature = agent._edit.temperature
    agent.max_tokens = agent._edit.max_tokens
    agent.personality = agent._edit.personality

    agent._saved = true
    setTimeout(() => {
      agent._saved = false
    }, 3000)
  } catch (e) {
    console.warn('[Config] 保存智能体配置失败:', e.message)
    alert(`保存 ${agent.display_name} 配置失败: ${e.message}`)
  } finally {
    agent._saving = false
  }
}

// ============================================================
// 智能体辅助
// ============================================================

/**
 * 判断智能体是否可用（协调者始终可用，其他智能体只要有默认 Provider 即可）
 */
function agentHasConfig(agent) {
  // 协调者始终可启用
  if (agent.name === 'coordinator') return true
  // 只要有默认 Provider，智能体即可工作（使用继承的模型）
  return providers.value.some(p => p.name === 'default')
}

/**
 * 获取智能体图标（根据名称显示不同 emoji）
 */
function getAgentIcon(name) {
  const icons = {
    coordinator: '🧠',
    general_chat: '💬',
    code_expert: '💻',
    creative: '🎨',
    analyst: '📊',
    translator: '🌐'
  }
  return icons[name] || '🤖'
}

// ============================================================
// 初始化
// ============================================================

onMounted(() => {
  loadConfig()
})

onBeforeUnmount(() => {
  /* 无全局监听器需要清理 */
})
</script>

<style scoped>
/* ================================================================
   VoiceConfig.vue — 配置面板样式
   基于设计系统 tokens，无 CSS fallback，统一的间距/圆角/颜色系统
   ================================================================ */

/* ---- 遮罩层 ---- */
.voice-config-overlay {
  position: fixed;
  z-index: 9999;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-overlay);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  animation: overlayFadeIn var(--duration-normal) var(--ease-out);
}

@keyframes overlayFadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

.voice-config {
  width: 100%;
  max-width: 440px;
  margin: var(--space-lg);
}

/* ---- 卡片主体 ---- */
.config-card {
  width: 100%;
  max-height: 85vh;
  overflow-y: auto;
  overflow-x: hidden;
  -webkit-overflow-scrolling: touch;
  scroll-behavior: smooth;
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-xl);
  padding: var(--space-2xl) var(--space-xl);
  box-shadow: var(--shadow-elevated);
}

.config-card::-webkit-scrollbar {
  width: 4px;
}
.config-card::-webkit-scrollbar-thumb {
  background: var(--text-quaternary);
  border-radius: var(--radius-full);
}

/* ---- 头部 ---- */
.config-header {
  text-align: center;
  margin-bottom: var(--space-2xl);
}

.config-logo {
  font-size: 40px;
  margin-bottom: var(--space-sm);
  display: block;
}

.config-header h2 {
  font-size: var(--text-xl);
  font-weight: var(--weight-bold);
  margin: 0 0 var(--space-xs);
  background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.config-desc {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  margin: 0;
  line-height: var(--leading-normal);
}

/* ---- 加载中 ---- */
.loading-state {
  text-align: center;
  padding: var(--space-4xl) 0;
  color: var(--text-tertiary);
}

.spinner {
  width: 32px;
  height: 32px;
  margin: 0 auto var(--space-md);
  border: 3px solid var(--border-color);
  border-top-color: var(--accent-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* ---- Tab 导航 ---- */
.config-tabs {
  display: flex;
  gap: var(--space-2xs);
  margin-bottom: var(--space-lg);
  padding: var(--space-xs);
  background: var(--bg-primary);
  border-radius: var(--radius-md);
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.config-tab {
  flex: 1;
  min-width: 56px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2xs);
  padding: var(--space-sm) var(--space-xs) var(--space-xs);
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-tertiary);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
  white-space: nowrap;
}

.config-tab:hover {
  color: var(--text-secondary);
  background: var(--bg-hover);
}

.config-tab.active {
  color: var(--accent-primary);
  background: var(--accent-primary-light);
}

.config-tab .tab-icon {
  font-size: 18px;
  line-height: 1;
}

.config-tab .tab-label {
  font-weight: var(--weight-medium);
}

/* ---- Tab 内容动画 ---- */
.tab-content {
  contain: content;
  animation: tabFadeIn var(--duration-normal) var(--ease-out);
}

@keyframes tabFadeIn {
  from {
    opacity: 0;
    transform: translateY(var(--space-xs));
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* ---- 状态区域 ---- */
.status-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  margin-bottom: var(--space-xl);
  padding: var(--space-md);
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
}

.status-item {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.status-item .status-icon {
  font-size: var(--text-md);
  width: 20px;
  text-align: center;
}

.status-item .status-label {
  flex: 1;
}

.status-item .status-value {
  font-weight: var(--weight-semibold);
  color: var(--text-tertiary);
}

.status-item.ok .status-value {
  color: var(--accent-green);
}

/* ---- 表单区域 ---- */
.form-section {
  margin-bottom: var(--space-lg);
}

.form-section h3 {
  font-size: var(--text-sm);
  font-weight: var(--weight-semibold);
  color: var(--text-primary);
  margin: 0 0 var(--space-sm);
}

.section-hint {
  font-weight: var(--weight-regular);
  color: var(--text-tertiary);
  font-size: var(--text-xs);
}

.form-label {
  display: flex;
  flex-direction: column;
  gap: var(--space-2xs);
  margin-bottom: var(--space-sm);
}

.form-label > span {
  font-size: var(--text-xs);
  font-weight: var(--weight-medium);
  color: var(--text-secondary);
}

.form-label input,
.form-label select {
  width: 100%;
  height: 38px;
  padding: 0 var(--space-md);
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: var(--text-sm);
  outline: none;
  transition: border-color var(--duration-fast) var(--ease-out), box-shadow var(--duration-fast) var(--ease-out);
  box-sizing: border-box;
}

.form-label input:focus,
.form-label select:focus {
  border-color: var(--border-focus);
  box-shadow: 0 0 0 3px var(--accent-primary-light);
}

.form-label input::placeholder {
  color: var(--text-tertiary);
  font-size: var(--text-xs);
}

.input-tip {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  margin: var(--space-2xs) 0 0;
}

.save-success {
  text-align: center;
  font-size: var(--text-sm);
  color: var(--accent-green);
  margin: var(--space-sm) 0 0;
}

/* ---- Provider 列表 ---- */
.provider-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.provider-item {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: var(--space-sm) var(--space-md);
  transition: border-color var(--duration-fast) var(--ease-out);
}

.provider-item.provider-default {
  border-color: var(--accent-primary-light);
}

.provider-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  user-select: none;
}

.provider-info {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  min-width: 0;
}

.provider-name {
  font-size: var(--text-sm);
  font-weight: var(--weight-semibold);
  color: var(--text-primary);
}

.provider-badge {
  font-size: var(--text-xs);
  font-weight: var(--weight-semibold);
  padding: 1px 6px;
  border-radius: var(--radius-xs);
}

.provider-badge-default {
  color: var(--accent-primary);
  background: var(--accent-primary-light);
}

.provider-model {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.provider-icon {
  font-size: var(--text-lg);
  line-height: 1;
  width: 20px;
  text-align: center;
  flex-shrink: 0;
}

/* Provider 二级信息行 */
.provider-sub {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin-top: var(--space-2xs);
  padding-left: 26px;
}

.provider-api-base {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  opacity: 0.7;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 180px;
  font-family: 'SF Mono', 'Cascadia Code', monospace;
}

.provider-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2xs);
  flex-shrink: 0;
}

.provider-key-badge {
  font-size: var(--text-xs);
  padding: 2px 6px;
  border-radius: var(--radius-xs);
  color: var(--accent-green);
  background: var(--accent-green-light);
}

.provider-key-badge.no-key {
  color: var(--text-tertiary);
  background: var(--bg-tertiary);
}

.provider-delete-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: var(--text-md);
  padding: var(--space-2xs);
  line-height: 1;
  opacity: 0.5;
  transition: opacity var(--duration-fast) var(--ease-out);
}

.provider-delete-btn:hover {
  opacity: 1;
}

.provider-expand-icon {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  margin-left: var(--space-2xs);
}

/* ---- Provider 配置表单 ---- */
.provider-config-form {
  margin-top: var(--space-sm);
  padding: var(--space-md);
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
}

.form-row {
  display: flex;
  gap: var(--space-sm);
  align-items: flex-start;
}

.form-label-inline {
  flex: 1;
}

.form-label-inline span {
  white-space: nowrap;
}

.form-range {
  width: 100%;
  height: 4px;
  accent-color: var(--accent-primary);
  cursor: pointer;
}

.form-input-narrow {
  width: 100% !important;
}

.provider-form-actions {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin-top: var(--space-sm);
}

.provider-save-btn {
  flex: 1;
  height: 34px;
  font-size: var(--text-sm);
  border-radius: var(--radius-sm);
}

.provider-saved-hint {
  font-size: var(--text-xs);
  color: var(--accent-green);
  white-space: nowrap;
}

/* 添加 Provider 按钮 */
.add-provider-btn {
  width: 100%;
  margin-top: var(--space-sm);
  padding: var(--space-sm);
  font-size: var(--text-sm);
  font-weight: var(--weight-medium);
  color: var(--accent-primary);
  background: none;
  border: 1px dashed var(--border-color);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.add-provider-btn:hover {
  border-color: var(--accent-primary);
  background: var(--accent-primary-light);
}

.add-provider-form {
  margin-top: var(--space-sm);
  padding: var(--space-md);
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

/* ---- 开关行 ---- */
.toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-xs) 0;
}

/* ---- 智能体列表 ---- */
.agent-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.agent-item {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: var(--space-sm) var(--space-md);
  transition: border-color var(--duration-fast) var(--ease-out);
}

.agent-item.enabled {
  border-color: var(--accent-primary-light);
}

.agent-header {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  margin-bottom: var(--space-2xs);
}

.agent-icon {
  font-size: var(--text-lg);
}

.agent-name {
  flex: 1;
  font-size: var(--text-sm);
  font-weight: var(--weight-semibold);
  color: var(--text-primary);
}

.agent-badge {
  font-size: var(--text-xs);
  font-weight: var(--weight-semibold);
  padding: 1px 6px;
  border-radius: var(--radius-xs);
}

.badge-on {
  color: var(--accent-green);
  background: var(--accent-green-light);
}

.badge-off {
  color: var(--text-tertiary);
  background: var(--bg-tertiary);
}

.agent-desc {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  margin: 0;
  line-height: var(--leading-normal);
}

.agent-meta {
  display: flex;
  gap: var(--space-xs);
  margin-top: var(--space-2xs);
}

.meta-tag {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  background: var(--bg-tertiary);
  padding: 1px 6px;
  border-radius: var(--radius-xs);
}

.meta-tag-default {
  opacity: 0.55;
  font-style: italic;
}

/* ---- 智能体展开按钮 ---- */
.agent-expand-btn {
  display: block;
  width: 100%;
  margin-top: var(--space-xs);
  padding: var(--space-2xs) 0;
  font-size: var(--text-xs);
  color: var(--accent-primary);
  background: none;
  border: 1px solid transparent;
  border-radius: var(--radius-xs);
  cursor: pointer;
  text-align: center;
  transition: all var(--duration-fast) var(--ease-out);
}

.agent-expand-btn:hover {
  background: var(--bg-tertiary);
  border-color: var(--border-color);
}

/* ---- 智能体配置表单 ---- */
.agent-config-form {
  margin-top: var(--space-sm);
  padding: var(--space-sm);
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.agent-config-form .form-row {
  display: flex;
  flex-direction: column;
  gap: var(--space-2xs);
}

.agent-config-form .form-select {
  width: 100%;
  padding: 5px 8px;
  font-size: var(--text-xs);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-xs);
  background: var(--bg-primary);
  color: var(--text-primary);
  outline: none;
  cursor: pointer;
  transition: border-color var(--duration-fast) var(--ease-out);
  font-family: inherit;
  box-sizing: border-box;
}

.agent-config-form .form-select:focus {
  border-color: var(--border-focus);
}

.agent-config-form .form-label {
  font-size: var(--text-xs);
  font-weight: var(--weight-semibold);
  color: var(--text-secondary);
}

.agent-config-form .form-input {
  padding: 5px 8px;
  font-size: var(--text-xs);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-xs);
  background: var(--bg-primary);
  color: var(--text-primary);
  outline: none;
  transition: border-color var(--duration-fast) var(--ease-out);
}

.agent-config-form .form-input:focus {
  border-color: var(--border-focus);
}

.agent-config-form .form-input-narrow {
  width: 120px;
}

.agent-config-form .form-range {
  width: 100%;
  height: 4px;
  accent-color: var(--accent-primary);
  cursor: pointer;
}

.agent-config-form .form-textarea {
  width: 100%;
  padding: var(--space-sm) var(--space-sm);
  font-size: var(--text-xs);
  line-height: var(--leading-normal);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-xs);
  background: var(--bg-primary);
  color: var(--text-primary);
  outline: none;
  resize: vertical;
  min-height: 60px;
  font-family: inherit;
  transition: border-color var(--duration-fast) var(--ease-out);
  box-sizing: border-box;
}

.agent-config-form .form-textarea:focus {
  border-color: var(--border-focus);
}

.agent-config-form .form-label-hint {
  font-weight: var(--weight-regular);
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.save-agent-btn {
  align-self: flex-end;
  padding: 5px 14px;
  font-size: var(--text-xs);
  font-weight: var(--weight-semibold);
  color: var(--text-inverse);
  background: var(--accent-primary);
  border: none;
  border-radius: var(--radius-xs);
  cursor: pointer;
  transition: opacity var(--duration-fast) var(--ease-out);
}

.save-agent-btn:hover {
  opacity: 0.85;
}

.save-agent-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.agent-saved-hint {
  font-size: var(--text-xs);
  color: var(--accent-green);
  align-self: center;
}

/* 智能体启用开关紧凑样式 */
.agent-toggle {
  width: 34px;
  height: 18px;
  flex-shrink: 0;
}

.agent-toggle .toggle-slider::before {
  width: 14px;
  height: 14px;
}

.agent-toggle input:checked + .toggle-slider::before {
  transform: translateX(16px);
}

.agent-toggle input:disabled + .toggle-slider {
  opacity: 0.4;
  cursor: not-allowed;
}

/* 无配置警告提示 */
.agent-config-warning {
  font-size: var(--text-xs);
  color: var(--accent-orange);
  margin: var(--space-xs) 0 0;
  padding: var(--space-2xs) var(--space-xs);
  background: var(--accent-orange-light);
  border-radius: var(--radius-xs);
}

/* ---- 技能选择列表 ---- */
.skill-checkbox-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2xs);
}

.skill-checkbox-item {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  padding: 5px 8px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-xs);
  background: var(--bg-primary);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
  user-select: none;
}

.skill-checkbox-item:hover {
  border-color: var(--accent-primary);
  background: var(--bg-tertiary);
}

.skill-checkbox-item.equipped {
  border-color: var(--accent-primary-light);
  background: var(--accent-primary-light);
}

.skill-checkbox-item input[type='checkbox'] {
  flex-shrink: 0;
  accent-color: var(--accent-primary);
  cursor: pointer;
}

.skill-checkbox-name {
  font-size: var(--text-xs);
  font-weight: var(--weight-semibold);
  color: var(--text-primary);
  min-width: 48px;
}

.skill-checkbox-desc {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  flex: 1;
}

.skill-empty-hint {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  font-style: italic;
}

/* ---- Toggle 开关 ---- */
.toggle-label {
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.toggle-switch {
  position: relative;
  display: inline-block;
  width: 42px;
  height: 22px;
  cursor: pointer;
}

.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-slider {
  position: absolute;
  inset: 0;
  background: var(--border-color);
  border-radius: var(--radius-full);
  transition: background var(--duration-fast) var(--ease-out);
}

.toggle-slider::before {
  content: '';
  position: absolute;
  left: 2px;
  top: 2px;
  width: 18px;
  height: 18px;
  background: var(--pearl);
  border-radius: 50%;
  transition: transform var(--duration-fast) var(--ease-spring);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.35);
}

.toggle-switch input:checked + .toggle-slider {
  background: var(--accent-primary);
}

.toggle-switch input:checked + .toggle-slider::before {
  transform: translateX(20px);
}

/* ---- 操作按钮 ---- */
.action-row {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  margin-top: var(--space-xl);
}

.save-btn {
  width: 100%;
  height: 42px;
  border: none;
  border-radius: var(--radius-md);
  background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
  color: var(--text-inverse);
  font-size: var(--text-md);
  font-weight: var(--weight-semibold);
  cursor: pointer;
  transition: opacity var(--duration-fast) var(--ease-out), transform var(--duration-fast) var(--ease-out);
}

.save-btn:hover {
  opacity: 0.9;
}
.save-btn:active {
  transform: scale(0.98);
}
.save-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.close-btn {
  width: 100%;
  height: 38px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-secondary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.close-btn:hover {
  border-color: var(--accent-primary);
  color: var(--accent-primary);
}
.close-btn:active {
  transform: scale(0.98);
}

/* ---- 错误信息 ---- */
.error-msg {
  text-align: center;
  font-size: var(--text-xs);
  color: var(--accent-red);
  margin: var(--space-sm) 0 0;
}

/* ---- 过渡动画 ---- */
.fade-enter-active,
.fade-leave-active {
  transition: opacity var(--duration-normal);
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* ---- 语音 Provider 标签 ---- */
.provider-voice-tag {
  font-size: var(--text-xs);
  color: var(--accent-secondary);
  background: var(--accent-primary-light);
  padding: 1px 5px;
  border-radius: var(--radius-xs);
  margin-left: var(--space-2xs);
}

.no-voice-provider {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  text-align: center;
  padding: var(--space-lg);
  background: var(--bg-primary);
  border: 1px dashed var(--border-color);
  border-radius: var(--radius-sm);
}

.form-select {
  width: 100%;
  height: 38px;
  padding: 0 var(--space-md);
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: var(--text-sm);
  outline: none;
  cursor: pointer;
  transition: border-color var(--duration-fast) var(--ease-out);
  box-sizing: border-box;
}

.form-select:focus {
  border-color: var(--border-focus);
  box-shadow: 0 0 0 3px var(--accent-primary-light);
}

/* ---- NLU 语义识别模型配置 ---- */
.nlu-status-bar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-md);
  padding: var(--space-sm) var(--space-md);
  background: var(--bg-primary);
  border-radius: var(--radius-sm);
  margin-bottom: var(--space-lg);
  font-size: var(--text-xs);
}

.nlu-status-item {
  display: flex;
  align-items: center;
  gap: var(--space-2xs);
}

.nlu-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent-red);
  display: inline-block;
}

.nlu-status-dot.connected {
  background: var(--accent-green);
}

.nlu-status-label {
  color: var(--text-secondary);
}

.nlu-status-value {
  color: var(--text-primary);
  font-weight: var(--weight-medium);
}

.nlu-status-url {
  font-family: 'SF Mono', 'Cascadia Code', monospace;
  font-size: var(--text-xs);
  color: var(--accent-primary);
  word-break: break-all;
}

.nlu-config-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.nlu-input {
  width: 100%;
  height: 40px;
  padding: 0 var(--space-md);
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: var(--text-sm);
  font-family: 'SF Mono', 'Cascadia Code', monospace;
  outline: none;
  transition: border-color var(--duration-fast) var(--ease-out), box-shadow var(--duration-fast) var(--ease-out);
  box-sizing: border-box;
}

.nlu-input:focus {
  border-color: var(--border-focus);
  box-shadow: 0 0 0 3px var(--accent-primary-light);
}

.nlu-input::placeholder {
  color: var(--text-tertiary);
  font-family: inherit;
}

.nlu-field-label {
  display: block;
  font-size: var(--text-xs);
  font-weight: var(--weight-semibold);
  color: var(--text-primary);
  margin-bottom: var(--space-2xs);
}

.nlu-optional {
  font-weight: var(--weight-regular);
  color: var(--text-tertiary);
  font-size: var(--text-xs);
}

.nlu-field-desc {
  display: block;
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  margin-top: var(--space-2xs);
  line-height: var(--leading-normal);
}

.nlu-field-desc code {
  font-family: 'SF Mono', 'Cascadia Code', monospace;
  font-size: var(--text-xs);
  background: var(--bg-tertiary);
  padding: 1px 4px;
  border-radius: var(--radius-xs);
  color: var(--accent-primary);
}

.nlu-form-actions {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  margin-top: var(--space-2xs);
}

.nlu-saved-hint {
  font-size: var(--text-xs);
  color: var(--accent-green);
  font-weight: var(--weight-medium);
}

.nlu-error-hint {
  font-size: var(--text-xs);
  color: var(--accent-red);
  font-weight: var(--weight-medium);
}

.nlu-templates {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  margin-top: var(--space-md);
  padding-top: var(--space-md);
  border-top: 1px solid var(--border-light);
  flex-wrap: wrap;
}

.nlu-template-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  white-space: nowrap;
}

.nlu-template-btn {
  font-size: var(--text-xs);
  padding: 4px 10px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-xs);
  background: var(--bg-primary);
  color: var(--text-primary);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
  white-space: nowrap;
}

.nlu-template-btn:hover {
  background: var(--accent-primary-light);
  border-color: var(--accent-primary);
  color: var(--accent-primary);
}

/* ---- 外观 / 主题切换 ---- */
.theme-static {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  margin-top: var(--space-sm);
  padding: var(--space-md);
  border: 1px solid var(--hair-warm);
  border-radius: var(--radius-md);
  background: var(--glass-2);
}

.theme-static-seal {
  flex-shrink: 0;
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  font-family: var(--serif);
  font-size: 20px;
  font-weight: 600;
  color: var(--gold-2);
  border: 1px solid var(--hair-warm);
  border-radius: 9px;
  background: linear-gradient(160deg, rgba(228, 181, 106, 0.1), rgba(228, 181, 106, 0.02));
}

.theme-static p {
  font-family: var(--serif);
  font-size: var(--text-sm);
  line-height: 1.9;
  color: var(--pearl-dim);
}

.section-desc {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
  margin-bottom: var(--space-md);
}

/* ---- 音色类型选择器 ---- */
.voice-type-radio {
  display: flex;
  gap: var(--space-sm);
  margin-top: var(--space-2xs);
}

.voice-type-option {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2xs);
  padding: var(--space-xs) var(--space-sm);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  cursor: pointer;
  font-size: var(--text-xs);
  color: var(--text-secondary);
  transition: all var(--duration-fast) var(--ease-out);
}

.voice-type-option:hover {
  border-color: var(--accent-primary);
}

.voice-type-option.active {
  border-color: var(--accent-primary);
  background: var(--accent-primary-light);
  color: var(--accent-primary);
}

.voice-type-option input[type='radio'] {
  display: none;
}

/* ---- Provider 快速模板 ---- */
.provider-templates {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  margin-top: var(--space-md);
  padding-top: var(--space-md);
  border-top: 1px solid var(--border-light);
  flex-wrap: wrap;
}

.provider-template-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  white-space: nowrap;
}

.provider-template-btn {
  font-size: var(--text-xs);
  padding: 4px 10px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-xs);
  background: var(--bg-primary);
  color: var(--text-primary);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
  white-space: nowrap;
}

.provider-template-btn:hover {
  background: var(--accent-primary-light);
  border-color: var(--accent-primary);
  color: var(--accent-primary);
}

/* ============================================================
   性格配置样式
   ============================================================ */

/** 预设选择区域 */
.preset-section {
  margin-bottom: var(--space-lg);
}

/** 预设按钮容器 */
.preset-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
  margin-top: var(--space-xs);
}

/** 单个预设按钮 */
.preset-btn {
  padding: var(--space-xs) var(--space-md);
  border-radius: var(--radius-xl);
  border: 1.5px solid var(--border-color);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.preset-btn:hover {
  border-color: var(--accent-primary);
  color: var(--accent-primary);
  background: var(--accent-primary-light);
}

.preset-btn.active {
  border-color: var(--accent-primary);
  background: var(--accent-primary);
  color: var(--ink-0);
}

/** 性格文本域 */
.personality-textarea {
  min-height: 120px;
  line-height: 1.6;
}

/** 未保存提示 */
.unsaved-hint {
  font-size: var(--text-sm);
  color: var(--warning-color, #f59e0b);
}

/** 保存成功提示（行内） */
.save-success-hint {
  font-size: var(--text-sm);
  color: var(--success-color, #22c55e);
}

/** 性格提示信息 */
.personality-info {
  margin-top: var(--space-lg);
  padding: var(--space-md);
  background: var(--accent-primary-light);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-light);
}

.personality-info p {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: 1.5;
}
</style>
