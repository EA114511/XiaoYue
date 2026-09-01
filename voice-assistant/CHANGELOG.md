# 更新日志

## [1.2.0] - 2026-09-01

### 第一阶段：自然交互体验

#### 新增
- `useWakeWord.js`：基于浏览器 SpeechRecognition 的唤醒词检测，支持「小玥小玥」/「小月小月」唤醒
- 语音打断（Barge-in）：AI 播报 TTS 时用户说话可立即停止播放并进入录音
- 唤醒提示音：唤醒成功后播放短促提示音
- 打断后免唤醒：打断成功后直接录音，无需再次说唤醒词

#### 变更
- `useVoiceChat.js`：新增打断监听逻辑，支持播放期间实时检测用户语音
- `VoiceAssistant.vue`：集成唤醒词状态管理，更新提示文案
- 优化 VAD 与打断状态的冲突处理，避免误触发

#### 兼容
- 浏览器不支持 SpeechRecognition 时自动降级，保留原有「按住说话」交互
- 语音打断功能默认开启，可通过 `enableBargeIn: false` 关闭

## [1.1.0] - 2026-07-20

### 界面重设计「月夜 · 明珠」

语音优先的全新界面：助手化身中央光球（玥珠），对话流退居侧栏。
详见 [docs/design-moonlight.md](docs/design-moonlight.md)。

#### 新增
- `NightSky.vue`：星野背景（星辰闪烁 + 月轮）
- `OrbCanvas.vue`：玥珠光球，四态语音可视化（待机呼吸 / 聆听涟漪 / 思索粒子轨 / 应答声纹）
- 设计文档 `docs/design-moonlight.md` 与前端指南 `docs/frontend.md`

#### 变更
- `main.css`：重写为「月夜·明珠」Token 体系（墨蓝 + 月光暖金 + 青瓷），单暗色主题
- `App.vue`：印章字标顶栏；模型状态 chip 双色语义（青瓷=本地，暖金=远程）
- `VoiceAssistant.vue`：双栏布局重构；对话流去气泡化，颜色分声部；印章头像标记智能体；语音消息改为波形 pill；流式回复光标
- `ConversationHistory.vue` / `VoiceConfig.vue`：暗色玻璃换肤（逻辑不变）
- 支持 `prefers-reduced-motion` 无障碍减动效

#### 移除
- `AudioVisualizer.vue`：可视化职责由玥珠承担
- 亮/暗双主题切换（统一为「月夜」暗色主题）

#### 修复
- Canvas 重设尺寸导致清空的竞态：尺寸未变不重设、变化时立即补绘，避免光球闪烁/空白
