# 小玥 AI 语音助手 — 操作文档

> 智能语音交互系统，支持语音识别（ASR）、AI 大模型语音合成（TTS）、自然语言理解（NLU）、多智能体协同对话、技能调用与 MCP 扩展。

---

## 目录

1. [项目概述](#1-项目概述)
2. [系统架构](#2-系统架构)
3. [技术栈](#3-技术栈)
4. [功能特性](#4-功能特性)
5. [环境准备](#5-环境准备)
6. [快速启动](#6-快速启动)
7. [配置说明](#7-配置说明)
8. [API 参考](#8-api-参考)
9. [WebSocket 协议](#9-websocket-协议)
10. [部署指南](#10-部署指南)
11. [常见问题](#11-常见问题)

---

## 1. 项目概述

小玥 AI 语音助手是一个**全栈语音交互系统**，提供以下核心能力：

- **语音对话**：通过 WebSocket 实时传输音频，实现「说话 → 识别 → 理解 → 回复 → 语音合成」的完整闭环
- **多智能体协同**：协调者（Coordinator）根据任务类型自动路由到代码、创意、分析、翻译等专精智能体
- **多 Provider 管理**：LLM 与语音合成都采用可插拔的 Provider 注册表，支持多厂商接口热切换
- **技能与 MCP 扩展**：内置天气、设备控制、日程、音乐、联网搜索、计算器、日期时间、笑话等技能，并支持接入外部 MCP 服务器
- **安全配置**：写接口支持 API Token 鉴权，持久化 API Key 使用 Fernet 加密存储

### 核心设计理念

| 原则 | 说明 |
|------|------|
| **可插拔** | LLM / TTS 均通过 Provider 注册表管理，可随时增删改，无需改代码 |
| **热更新** | 运行时通过 API 修改配置，无需重启服务 |
| **低延迟** | ASR 缓存、TTS 缓存、LLM 响应缓存、熔断器、并发控制、连接池复用等多层优化 |
| **模块化** | ASR / TTS / NLU / 对话 / 多智能体 / 技能各自独立，可替换实现 |

### 界面设计「月夜 · 明珠」

前端采用语音优先的全新设计：助手化身舞台中央的呼吸光球（玥珠），
待机 / 聆听 / 思索 / 应答四态各有专属动效；对话流去气泡化，以月光暖金（小玥）
与青瓷冷绿（用户）区分声部。

- 设计系统说明：[docs/design-moonlight.md](docs/design-moonlight.md)
- 前端开发指南：[docs/frontend.md](docs/frontend.md)
- 功能路线图：[docs/feature-roadmap.md](docs/feature-roadmap.md)
- 更新记录：[CHANGELOG.md](CHANGELOG.md)

---

## 2. 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                       前端 (Vue 3 + Vite)                    │
│  ┌───────────┐  ┌──────────────┐  ┌────────────────────┐   │
│  │VoiceConfig│  │VoiceAssistant│  │ OrbCanvas / NightSky│  │
│  │ (配置面板) │  │ (语音交互UI)  │  │ (光球/星空动效)     │   │
│  └─────┬─────┘  └──────┬───────┘  └────────────────────┘   │
│        └───────┬───────┘                                    │
│           ┌────┴────┐                                       │
│           │useVoiceChat (Composable)                        │
│           │ · WebSocket 管理                                │
│           │ · MediaRecorder 录音                           │
│           │ · AudioQueue TTS 播放                          │
│           └─────────┘                                       │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP REST + WebSocket
                            │
┌───────────────────────────┴─────────────────────────────────┐
│                    后端 (FastAPI + Python)                    │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐  │
│  │ REST API  │  │ WebSocket │  │ Provider  │  │  Database  │  │
│  │endpoints  │  │  handler  │  │ Registries│  │  Service   │  │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘  └──────┬─────┘  │
│        └──────┬──────┘              │               │        │
│          ┌────┴────┐                │               │        │
│          │ Dialog  │◄───────────────┘               │        │
│          │Manager  │                                │        │
│          └────┬────┘                                │        │
│     ┌─────────┼──────────────────────────┐          │        │
│     ▼         ▼          ▼               ▼          │        │
│  ┌──────┐ ┌────────┐ ┌──────────┐ ┌────────────┐   │        │
│  │ NLU  │ │  ASR   │ │ MultiAgent│ │  Skills/MCP│   │        │
│  │Service│ │Service │ │Orchestrator│ │  Registry │   │        │
│  └──┬───┘ └──┬─────┘ └────┬─────┘ └─────┬──────┘   │        │
│     │        │            │              │          │        │
│     ▼        ▼            ▼              ▼          │        │
│  ┌──────┐ ┌────────┐ ┌──────────┐ ┌────────────┐   │        │
│  │ LLM  │ │ Whisper│ │ AI Voice │ │ MCP Servers│   │        │
│  │ API  │ │   ASR  │ │   TTS    │ │ (外部工具) │   │        │
│  └──────┘ └────────┘ └──────────┘ └────────────┘   │        │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 数据流（语音对话）

```
用户说话 → MediaRecorder(Opus编码) → WebSocket二进制帧
                                          ↓
                                   VoiceSession.handle_audio
                                          ↓
                                   ASRService.recognize_stream
                                          ↓
                                   DialogManager.process_message
                                    ├─ NLUService.parse (意图识别)
                                    ├─ 规则引擎 / LLM 兜底
                                    ├─ 多智能体路由（Coordinator → Specialist）
                                    ├─ 技能 / MCP 工具调用
                                    └─ LLM 生成回复
                                          ↓
                                   AI 语音合成（后台并行）
                                   WebSocket 二进制帧返回
                                          ↓
                                   前端 AudioQueue 播放
```

---

## 3. 技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| **后端框架** | Python 3.11+, FastAPI | 异步 Web 框架 |
| **ASR** | OpenAI Whisper (`openai-whisper`) | 本地语音识别，支持 tiny/base/small/medium/large |
| **VAD** | WebRTC VAD (`webrtcvad`) | 语音活动检测，灵敏度 0-3 |
| **TTS** | AI 语音大模型 API | 智谱 GLM-TTS / OpenAI 兼容 TTS，可插拔 Provider |
| **NLU** | 规则引擎 + LLM 兜底 | 正则匹配（阈值 0.60）→ LLM 调用 |
| **LLM** | OpenAI 兼容 API | 多 Provider 注册表，支持 GLM / DeepSeek / Ollama 等 |
| **多智能体** | 自研 AgentRegistry / Orchestrator | 协调者路由 + 专精智能体 |
| **技能扩展** | Skill Registry + MCP Bridge | 内置技能 + 外部 MCP 服务器 |
| **前端框架** | Vue 3 (Composition API) | `script setup` + Vite |
| **前端状态** | Composable（useVoiceChat / useVAD） | 组合式函数管理状态，无全局 store |
| **WebSocket** | FastAPI WebSocket | 二进制帧传输音频 |
| **部署** | Docker Compose | backend + frontend 双容器 |

---

## 4. 功能特性

### 4.1 已实现功能

| 功能 | 状态 | 说明 |
|------|------|------|
| 语音识别（ASR） | ✅ 已完成 | Whisper 本地模型，支持流式识别，VAD 检测 |
| 语音合成（TTS） | ✅ 已完成 | AI 语音大模型合成（智谱 GLM-TTS / OpenAI TTS），音频队列播放 |
| NLU 意图识别 | ✅ 已完成 | 规则引擎（问候/感谢/告别/能力）+ LLM 兜底 |
| 多智能体协同 | ✅ 已完成 | 协调者路由到代码/创意/分析/翻译等专精智能体 |
| 多 Provider 管理 | ✅ 已完成 | LLM / 语音 Provider 注册表，支持增删改查 |
| 技能调用 | ✅ 已完成 | 天气、设备、日程、音乐、搜索、计算器、日期时间、笑话 |
| MCP 扩展 | ✅ 已完成 | 注册外部 MCP 服务器并自动发现工具 |
| 多轮对话 | ✅ 已完成 | 会话上下文管理（10 轮历史，30 分钟超时） |
| 天气查询 | ✅ 已完成 | wttr.in 主 API + OpenWeatherMap 备用 |
| 设备控制 | ✅ 已完成 | 智能家居设备模拟控制（灯/空调/窗帘等） |
| 运行时配置 | ✅ 已完成 | 通过 REST API 热更新配置，无需重启 |
| API Token 鉴权 | ✅ 已完成 | 写接口（POST/PATCH/DELETE）校验 X-API-Token |
| API Key 加密 | ✅ 已完成 | Fernet 加密持久化存储的 API Key |
| 熔断器 | ✅ 已完成 | 熔断器（5 次失败阈值，30s 恢复） |
| 响应缓存 | ✅ 已完成 | ASR 缓存、TTS 缓存、LLM 语义缓存（TTL 300s） |
| 并发控制 | ✅ 已完成 | 信号量 + httpx 连接池复用 |
| 二进制帧传输 | ✅ 已完成 | WebSocket 二进制帧传输 TTS 音频，节省带宽 |
| 音频可视化 | ✅ 已完成 | 呼吸光球（OrbCanvas）+ 星空背景（NightSky） |

### 4.2 功能模块说明

#### 语音对话（核心）
- 长按录音按钮说话，松手自动发送
- 后端流式接收音频 → ASR 识别 → NLU 理解 → 多智能体路由 → LLM 生成 → AI 语音合成
- TTS 音频通过 WebSocket 二进制帧实时返回
- 前端 AudioQueue 顺序播放，不重叠

#### 多智能体协同
- **协调者（Coordinator）**：判别任务类型，路由到合适的专精智能体
- **专精智能体**：`general_chat`（通用聊天）、`code_expert`（代码）、`creative`（创意）、`analyst`（分析）、`translator`（翻译）
- 每个智能体可独立配置 model / api_base / temperature / system_prompt，并装配技能
- 智能体可通过 `/api/v1/agents` 接口动态配置

#### Provider 注册表
- **LLM Provider**：每个 Provider 是一个独立的模型接口（名称、地址、Key、模型），通过 `data/llm_providers.json` 持久化，`/api/v1/providers` 管理
- **语音 Provider**：管理语音合成的接口与音色，通过 `data/voice_providers.json` 持久化，`/api/v1/voice-providers` 管理
- 不再使用「有 Key → 远程 / 无 Key → Ollama」的自动切换逻辑

#### 技能与 MCP
- **内置技能**：天气查询、智能家居、日程管理、音乐播放、联网搜索、计算器、日期时间、讲笑话
- **Function Calling**：技能会以 tools 形式注入到专精智能体，由 LLM 自主决定是否调用
- **MCP Bridge**：注册外部 MCP 服务器后自动发现并注册其工具

---

## 5. 环境准备

### 5.1 系统要求

| 依赖 | 版本要求 | 用途 |
|------|---------|------|
| Python | 3.11+ | 后端运行环境 |
| Node.js | 18+ | 前端构建运行 |
| FFmpeg | 任意版本 | 音频格式转换（Whisper 需要） |
| Docker（可选） | 24+ | 容器化部署 |

### 5.2 安装 FFmpeg

```bash
# Windows (使用 winget)
winget install ffmpeg

# 或访问 https://ffmpeg.org/download.html 下载安装

# 验证安装
ffmpeg -version
```

> 说明：本项目已移除本地 Edge TTS，语音合成使用 AI 语音大模型 API，无需额外安装 TTS 引擎。
> 如需使用本地大模型，可将 Ollama 作为一个 LLM Provider（`api_base=http://localhost:11434/v1`）接入。

---

## 6. 快速启动

### 6.1 后端启动

```bash
cd voice-assistant/backend

# 创建虚拟环境（推荐）
python -m venv venv
venv\Scripts\activate    # Windows
# source venv/bin/activate  # Linux/Mac

# 安装依赖
pip install -r requirements.txt

# 创建配置文件
copy .env.example .env   # Windows
# cp .env.example .env   # Linux/Mac

# 启动开发服务器
python main.py
```

后端服务默认运行在 `http://localhost:8000`。API 文档可访问：
- Swagger UI: `http://localhost:8000/docs`
- Redoc: `http://localhost:8000/redoc`

### 6.2 前端启动

```bash
cd voice-assistant/frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端默认运行在 `http://localhost:3000`。

### 6.3 验证启动

```bash
# 检查后端健康状态
curl http://localhost:8000/api/v1/health/status

# 预期返回
# {"status":"healthy","service":"voice-assistant","version":"1.0.0","active_conversations":0,"expired_conversations":0}
```

浏览器打开 `http://localhost:3000`，应能看到：
- 舞台中央的呼吸光球（玥珠）
- 对话历史区域
- 中央录音按钮
- 配置面板（Provider、智能体、技能、语音等）

---

## 7. 配置说明

### 7.1 环境变量配置（.env 文件）

后端 `.env` 文件位于 `voice-assistant/backend/.env`，从 `.env.example` 复制后修改：

```ini
# ---------- 服务器配置 ----------
HOST=0.0.0.0
PORT=8000
DEBUG=true
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173

# ---------- 安全配置 ----------
# 管理接口鉴权 Token（为空则不启用写接口鉴权）
API_TOKEN=
# 用于加密持久化存储的 API Key（生产环境必须设置）
CRYPTO_KEY=

# ---------- 默认 LLM Provider 初始值 ----------
# 仅作为 "default" Provider 的初始来源，运行时以 data/llm_providers.json 为准
OPENAI_API_KEY=
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL=gpt-3.5-turbo
OPENAI_MAX_TOKENS=2048
OPENAI_TEMPERATURE=0.7

# ---------- 语音识别 (ASR) 配置 ----------
ASR_ENGINE=whisper
WHISPER_MODEL_SIZE=base
ASR_DEFAULT_LANGUAGE=zh
VAD_SENSITIVITY=2

# ---------- 天气 API 配置 ----------
WEATHER_API_KEY=
WEATHER_API_URL=http://api.openweathermap.org/data/2.5
WEATHER_UNITS=metric

# ---------- 数据库配置 ----------
DATABASE_URL=sqlite:///./data/voice_assistant.db

# ---------- 日志配置 ----------
LOG_LEVEL=INFO
LOG_FILE=logs/voice_assistant.log
```

### 7.2 LLM Provider 配置

LLM Provider 持久化在 `backend/data/llm_providers.json`，可通过 `/api/v1/providers` 接口管理：

```json
[
  {
    "name": "default",
    "api_base": "https://open.bigmodel.cn/api/paas/v4",
    "api_key": "",
    "model": "glm-4.5",
    "max_tokens": 2048,
    "temperature": 0.8
  },
  {
    "name": "nlu-model",
    "api_base": "https://api.deepseek.com",
    "api_key": "",
    "model": "deepseek-v4-flash",
    "max_tokens": 2048,
    "temperature": 0.3
  }
]
```

- `default` 为不可删除的默认 Provider，其余 Provider 可自由增删
- NLU、Dialog 等模块可分别通过运行时配置绑定不同的 Provider
- `api_key` 会使用 `CRYPTO_KEY` 加密存储，不会明文落盘

### 7.3 语音 Provider 配置

语音 Provider 持久化在 `backend/data/voice_providers.json`，可通过 `/api/v1/voice-providers` 接口管理：

```json
[
  {
    "name": "zhipu-glm",
    "api_base": "https://open.bigmodel.cn/api/paas/v4",
    "api_key": "",
    "model": "glm-tts",
    "voice": "female",
    "enabled": true,
    "response_format": "pcm",
    "encode_format": "base64",
    "speed": 1.0,
    "volume": 1.0
  }
]
```

- `enabled` 为 `true` 且配置了 `api_base` / `api_key` 时，语音对话才可用
- 支持智谱 GLM-TTS 与 OpenAI 兼容 TTS 两类接口

### 7.4 前端配置

前端配置文件位于 `voice-assistant/frontend/.env`：

```ini
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:3000/ws/voice
VITE_APP_TITLE=AI 语音助手
VITE_API_TOKEN=
```

- `VITE_API_TOKEN` 需与后端 `API_TOKEN` 保持一致，前端会在写请求中自动附带 `X-API-Token`

### 7.5 配置优先级

```
Provider 配置 (data/*.json + API 管理)  >  环境变量 (.env)  >  代码默认值
```

---

## 8. API 参考

### 8.1 REST 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 服务根信息 |
| GET | `/health` | 健康检查（Docker 健康检查用） |
| GET | `/api/v1/health/status` | 详细健康状态 |
| GET | `/api/v1/settings` | 获取当前运行时配置 |
| POST | `/api/v1/settings` | 更新运行时配置 |
| POST | `/api/v1/voice/transcribe` | 语音文件转文字 |
| POST | `/api/v1/voice/synthesize` | 文字转语音 |
| POST | `/api/v1/conversation/start` | 开始新对话 |
| POST | `/api/v1/conversation/message` | 发送文本消息 |
| GET | `/api/v1/conversation/history` | 获取对话历史列表 |
| GET | `/api/v1/conversation/history/{conv_id}` | 获取对话详情 |
| DELETE | `/api/v1/conversation/history/{conv_id}` | 删除对话 |
| GET | `/api/v1/functions/weather` | 查询天气 |
| POST | `/api/v1/functions/device/control` | 设备控制 |
| GET | `/api/v1/providers` | 获取所有 LLM Provider |
| POST | `/api/v1/providers` | 创建 LLM Provider |
| GET | `/api/v1/providers/{name}` | 获取单个 LLM Provider |
| PATCH | `/api/v1/providers/{name}` | 更新 LLM Provider |
| DELETE | `/api/v1/providers/{name}` | 删除 LLM Provider |
| GET | `/api/v1/voice-providers` | 获取所有语音 Provider |
| POST | `/api/v1/voice-providers` | 创建语音 Provider |
| PATCH | `/api/v1/voice-providers/{name}` | 更新语音 Provider |
| DELETE | `/api/v1/voice-providers/{name}` | 删除语音 Provider |
| GET | `/api/v1/agents` | 获取所有智能体 |
| GET | `/api/v1/agents/enabled` | 获取已启用的专精智能体 |
| PATCH | `/api/v1/agents/{agent_name}` | 更新智能体配置 |
| GET | `/api/v1/skills` | 获取所有技能 |
| GET | `/api/v1/skills/enabled` | 获取已启用的技能 |
| GET | `/api/v1/skills/{skill_name}` | 获取技能详情 |
| GET | `/api/v1/skills/mcp/servers` | 获取所有 MCP 服务器 |
| POST | `/api/v1/skills/mcp/servers` | 注册 MCP 服务器 |
| DELETE | `/api/v1/skills/mcp/servers/{server_name}` | 移除 MCP 服务器 |
| POST | `/api/v1/skills/mcp/servers/{server_name}/discover` | 发现 MCP 工具 |

### 8.2 鉴权说明

当后端配置了 `API_TOKEN` 时，所有写操作（POST / PATCH / DELETE）需要携带鉴权头：

```bash
curl -X POST http://localhost:8000/api/v1/providers \
  -H "Content-Type: application/json" \
  -H "X-API-Token: <your-api-token>" \
  -d '{"name":"deepseek","api_base":"https://api.deepseek.com","model":"deepseek-chat"}'
```

### 8.3 详细接口示例

#### 健康检查

```
GET /api/v1/health/status

响应:
{
  "status": "healthy",
  "service": "voice-assistant",
  "version": "1.0.0",
  "active_conversations": 0,
  "expired_conversations": 0
}
```

#### 获取配置

```
GET /api/v1/settings

响应:
{
  "enable_voice_dialogue": true,
  "voice_dialogue_ready": true,
  "nlu_provider_name": "default",
  "dialog_provider_name": "default",
  "assistant_personality": "",
  "enable_headroom_compression": true,
  "default_provider": { ... },
  "providers": [ ... ],
  "voice_provider": { ... }
}
```

#### 对话消息

```
POST /api/v1/conversation/message
Content-Type: application/json

请求体:
{
  "conversation_id": "uuid-string",
  "message": "帮我写一段关于秋天的文案"
}

响应:
{
  "conversation_id": "uuid-string",
  "response": "秋天，是……",
  "intent": "general_chat",
  "confidence": 0.9,
  "agent": "creative"
}
```

#### 天气查询

```
GET /api/v1/functions/weather?city=北京

响应:
{
  "city": "北京",
  "temperature": "25°C",
  "weather": "晴",
  "humidity": "45%",
  "wind": "15km/h"
}
```

---

## 9. WebSocket 协议

### 9.1 连接地址

```
ws://localhost:8000/ws/voice
```

### 9.2 文本消息格式

所有文本消息为 JSON 格式：

```json
{
  "type": "消息类型",
  "payload": {}
}
```

#### 客户端 → 服务端

| type | payload | 说明 |
|------|---------|------|
| `audio_start` | `{ "session_id": "uuid" }` | 开始音频传输 |
| `text` | `{ "text": "...", "session_id": "uuid" }` | 发送文本消息 |
| `ping` | `{}` | 心跳检测 |

#### 服务端 → 客户端

| type | payload | 说明 |
|------|---------|------|
| `text` | `{ "text": "...", "session_id": "uuid" }` | 文本回复 |
| `status` | `{ "state": "listening/processing/responding", "session_id": "uuid" }` | 状态更新 |
| `pong` | `{}` | 心跳响应 |
| `error` | `{ "code": "...", "message": "..." }` | 错误信息 |

### 9.3 二进制帧协议

TTS 音频通过二进制帧传输：

```
[1B 类型] [4B 头部长度] [N 字节 JSON 头] [音频数据]

类型:
  0x01 = BINARY_TYPE_AUDIO (音频数据块)
  0x02 = BINARY_TYPE_END   (音频传输结束)
```

### 9.4 对话流程

```
客户端                    服务端
  │                        │
  │── audio_start ────────→│  开始会话
  │                        │
  │── [二进制音频帧] ──────→│  持续发送录音数据
  │                        │
  │                        │── ASR 识别
  │                        │── NLU 理解
  │                        │── 多智能体路由
  │                        │── LLM 生成回复
  │                        │── AI 语音合成（后台）
  │                        │
  │←── status(listening) ─┤  状态：正在识别
  │←── status(processing) ─┤  状态：正在处理
  │←── text({"text":...}) ─┤  文本回复（先返回）
  │←── [二进制音频帧 0x01] ┤  音频块（后台返回）
  │←── [二进制音频帧 0x02] ┤  传输结束
  │                        │
  │── ping ───────────────→│  心跳
  │←── pong ──────────────┤
```

---

## 10. 部署指南

### 10.1 Docker Compose 部署（推荐）

```bash
cd voice-assistant

# 创建后端配置文件
copy backend\.env.example backend\.env

# 编辑 .env 填写配置（务必设置 CRYPTO_KEY）
notepad backend\.env

# 启动全部服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

服务地址：
- 前端：`http://localhost:3000`
- 后端 API：`http://localhost:8000`
- API 文档：`http://localhost:8000/docs`

### 10.2 手动部署

#### 后端（生产模式）

```bash
cd voice-assistant/backend

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
set DEBUG=false
set CRYPTO_KEY=<your-random-key>
set API_TOKEN=<your-api-token>

# 使用 uvicorn 启动
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

#### 前端（生产模式）

```bash
cd voice-assistant/frontend

# 构建
npm run build

# 产物在 dist/ 目录，部署到 Nginx 即可
# 参考配置文件: nginx.conf
```

### 10.3 Nginx 反向代理配置

项目根目录的 `nginx.conf` 已包含完整的反向代理配置，包含 WebSocket 支持：

```nginx
# WebSocket 支持
location /ws/ {
    proxy_pass http://backend:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

---

## 11. 常见问题

### Q1: 启动后端时提示 ModuleNotFoundError

```bash
# 确保已安装全部依赖
pip install -r requirements.txt

# 常见缺失模块
pip install pydantic-settings  # pydantic v2 需要
```

### Q2: Whisper 模型下载很慢

Whisper 首次运行会自动下载模型。模型大小：

| 模型 | 大小 | 速度 | 准确率 |
|------|------|------|--------|
| tiny | ~75MB | 最快 | 最低 |
| base | ~150MB | 快 | 中等 |
| small | ~500MB | 中等 | 较高 |
| medium | ~1.5GB | 慢 | 高 |
| large | ~3GB | 最慢 | 最高 |

建议首次使用 `base` 模型。可在 `.env` 中修改 `WHISPER_MODEL_SIZE=base`。

### Q3: 语音对话没有声音（TTS 不工作）

1. 确认已在「语音 Provider」中配置并启用一个有效的 Provider（如智谱 GLM-TTS）
2. 确认 `voice_providers.json` 中该 Provider 的 `api_key` 已填写
3. 检查浏览器是否允许音频自动播放
4. 查看后端日志是否有 TTS 错误

### Q4: 如何接入其他 LLM 提供方？

通过 `/api/v1/providers` 创建新的 Provider 即可，无需改代码：

```bash
# DeepSeek
curl -X POST http://localhost:8000/api/v1/providers \
  -H "Content-Type: application/json" \
  -H "X-API-Token: <your-api-token>" \
  -d '{"name":"deepseek","api_base":"https://api.deepseek.com","model":"deepseek-chat","api_key":"sk-xxx"}'

# 本地 Ollama
curl -X POST http://localhost:8000/api/v1/providers \
  -H "Content-Type: application/json" \
  -H "X-API-Token: <your-api-token>" \
  -d '{"name":"local-ollama","api_base":"http://localhost:11434/v1","model":"qwen2.5:7b"}'
```

### Q5: 语音识别准确率低

- 增加 `VAD_SENSITIVITY` 值（0-3，值越大越不敏感）
- 使用更大的 Whisper 模型（`WHISPER_MODEL_SIZE=medium` 或 `large`）
- 确保录音环境安静

### Q6: 如何查看详细日志？

```bash
# 后端日志
# 在 .env 中设置 LOG_LEVEL=DEBUG
# 日志文件在 backend/logs/voice_assistant.log

# Docker 环境
docker-compose logs -f backend
```

### Q7: 前端构建失败

```bash
# 清除缓存后重试
cd frontend
rm -rf node_modules
rm package-lock.json
npm install
npm run build
```

---

## 附录

### 文件结构

```
voice-assistant/
├── backend/                        # Python FastAPI 后端
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # 应用入口 & 生命周期管理
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── endpoints.py        # REST API 路由
│   │   │   └── websocket.py        # WebSocket 语音对话
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py           # 配置系统 (Settings + RuntimeConfig)
│   │   │   ├── asr.py              # 语音识别 (Whisper + VAD + 缓存)
│   │   │   ├── ai_voice.py         # AI 语音大模型合成 (TTS)
│   │   │   ├── nlu.py              # 自然语言理解 (规则 + LLM 兜底)
│   │   │   ├── dialog.py           # 对话管理 (状态机 + 上下文)
│   │   │   ├── multi_agent.py      # 多智能体协同 (Coordinator + Specialist)
│   │   │   ├── llm_providers.py    # LLM Provider 注册表
│   │   │   ├── voice_providers.py  # 语音 Provider 注册表
│   │   │   ├── crypto_utils.py     # API Key 加密 (Fernet)
│   │   │   ├── http_client.py      # 统一 httpx 连接池管理
│   │   │   ├── database.py         # 数据库服务
│   │   │   └── optimization.py     # 优化工具 (熔断器/重试/并发)
│   │   ├── functions/
│   │   │   ├── __init__.py
│   │   │   ├── weather.py          # 天气查询
│   │   │   ├── device.py           # 设备控制
│   │   │   └── services.py         # 函数服务注册
│   │   ├── skills/
│   │   │   ├── __init__.py         # 技能注册表
│   │   │   ├── builtin.py          # 内置技能
│   │   │   └── mcp_bridge.py       # MCP 服务器桥接
│   │   └── utils/
│   │       ├── __init__.py
│   │       └── helpers.py          # 通用工具函数（ID/哈希/时间戳）
│   ├── data/                       # 持久化配置 (Provider / 智能体 / MCP)
│   ├── tests/                      # 单元测试
│   ├── .env.example                # 环境变量模板
│   ├── requirements.txt            # Python 依赖
│   ├── Dockerfile
│   └── main.py
├── frontend/                       # Vue 3 前端
│   ├── src/
│   │   ├── App.vue                 # 根组件 (布局)
│   │   ├── main.js                 # 入口文件
│   │   ├── components/
│   │   │   ├── VoiceAssistant.vue  # 语音助手交互组件
│   │   │   ├── VoiceConfig.vue     # 配置面板
│   │   │   ├── OrbCanvas.vue       # 呼吸光球动效
│   │   │   ├── NightSky.vue        # 星空背景动效
│   │   │   └── ConversationHistory.vue  # 对话历史
│   │   └── composables/
│   │       ├── useVoiceChat.js     # WebSocket + 录音 + TTS 播放
│   │       └── useVAD.js           # 语音活动检测 (VAD)
│   ├── package.json
│   ├── vite.config.js
│   ├── Dockerfile
│   └── nginx.conf
├── docker-compose.yml
├── nginx.conf
└── README.md
```

---

> **最后更新**: 2026-08-19
>
> 如有问题，请查看后端日志或提 Issue。
