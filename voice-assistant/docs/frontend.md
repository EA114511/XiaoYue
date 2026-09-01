# 前端开发指南

> 小玥 AI 语音助手前端 — Vue 3 + Vite。界面设计系统见 [design-moonlight.md](design-moonlight.md)。

## 技术栈

| 项 | 版本 | 说明 |
|----|------|------|
| Vue | ^3.4 | Composition API + `<script setup>` |
| Vite | ^5.1 | 开发与构建 |
| vue-router / pinia | ^4.3 / ^2.1 | 已安装，当前单页未启用路由 |

## 目录结构

```
frontend/
├── index.html                  # 入口（含 Google Fonts：Noto Serif SC + Cormorant Garamond）
├── vite.config.js              # 代理 /api 与 /ws 到后端（默认 :8000），别名 @ → src
├── src/
│   ├── main.js
│   ├── App.vue                 # 顶栏（印章字标/模型chip/设置）+ 环境层 + 配置弹窗挂载
│   ├── assets/styles/main.css  # 「月夜·明珠」设计 Tokens（单暗色主题）
│   ├── components/
│   │   ├── NightSky.vue        # 星野背景 Canvas
│   │   ├── OrbCanvas.vue       # 玥珠光球（语音状态可视化核心）
│   │   ├── VoiceAssistant.vue  # 主界面：左舞台 + 右对话流
│   │   ├── ConversationHistory.vue  # 历史对话抽屉
│   │   └── VoiceConfig.vue     # 配置弹窗（语音/模型/智能体/VAD/缓存）
│   └── composables/
│       ├── useVoiceChat.js     # WebSocket 管理、录音、TTS 播放队列
│       └── useVAD.js           # 语音活动检测 (VAD)
```

## 开发

```bash
cd frontend
npm install
npm run dev        # 默认 :3000，自动代理到后端 :8000
```

环境变量（`.env`，全部可选）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `VITE_API_URL` | `http://localhost:8000` | 后端 HTTP 地址（vite 代理目标） |
| `VITE_WS_URL` | `ws://localhost:8000` | 前端 WebSocket 连接地址 |

后端不可用时前端静默容错：界面正常渲染，WebSocket 自动重连。

## 构建

```bash
npm run build      # 输出 dist/（gzip 后 JS ≈ 53 KB，CSS ≈ 8.7 KB）
npm run preview    # 本地预览构建产物
```

## 核心接口：useVoiceChat

```js
const {
  isRecording, isProcessing, isPlaying,  // 布尔状态
  status,        // computed: 'idle' | 'recording' | 'processing'
  transcript,    // 实时识别文本
  response,      // AI 流式回复
  mediaStream,   // 麦克风流
  startRecording, stopRecording, sendText,
  setServerUrl, disconnect
} = useVoiceChat({ onTranscript, onResponse, onAgentInfo, onError, onStatusChange, onAudioReady })
```

界面状态映射（`VoiceAssistant.vue` 的 `orbState`）：

```
status === 'recording'  → listening（聆听）
status === 'processing' → thinking（思索）
isPlaying === true      → speaking（应答）
其他                    → idle（待机）
```

## 样式约定

- 一律使用 `main.css` 中的 Token 变量（`var(--gold)`、`var(--space-md)` 等），不写硬编码色值。
- 组件样式写在 SFC `<style scoped>` 中；全局仅 reset、Token 与环境层。
- 配色只能从 ink / gold / celadon / pearl / mist 色系及其透明度衍生，不引入新色相。
- 中文排版禁用斜体；拉丁强调词用 `.latin` 类（Cormorant Garamond italic）。
