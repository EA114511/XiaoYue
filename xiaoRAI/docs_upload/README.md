# 小玥 AI 语音助手 — 操作文档

> 智能语音交互系统，支持语音识别（ASR）、语音合成（TTS）、自然语言理解（NLU）、多轮对话管理及智能功能调用。

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

- **语音对话**：通过 WebSocket 实时传输音频，实现「说话→识别→理解→回复→语音合成」的完整闭环
- **智能问答**：支持远程大模型（OpenAI 兼容 API）和本地大模型（Ollama）自动切换
- **功能调用**：天气查询、设备控制等技能扩展
- **本地/远程 AI 自动切换**：配置了 API Key 则使用远程大模型，未配置时自动切换到本地 Ollama

### 核心设计理念

| 原则 | 说明 |
|------|------|
| **非阻塞** | AI Key 未配置时自动使用本地大模型，不阻塞用户使用 |
| **热更新** | 运行时通过 API 修改配置，无需重启服务 |
| **低延迟** | ASR 缓存、TTS 缓存、LLM 响应缓存、熔断器、并发控制等多层优化 |
| **模块化** | ASR / TTS / NLU / 对话管理 各自独立，可替换实现 |

### 界面设计「月夜 · 明珠」

v1.1.0 起，前端采用语音优先的全新设计：助手化身舞台中央的呼吸光球（玥珠），
待机 / 聆听 / 思索 / 应答四态各有专属动效；对话流去气泡化，以月光暖金（小玥）
与青瓷冷绿（用户）区分声部。

![界面设计总览](docs/assets/design-overview.png)

- 设计系统说明：[docs/design-moonlight.md](docs/design-moonlight.md)
- 前端开发指南：[docs/frontend.md](docs/frontend.md)
- 更新记录：[CHANGELOG.md](CHANGELOG.md)

---

## 2. 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                       前端 (Vue 3 + Vite)                    │
│  ┌───────────┐  ┌──────────────┐  ┌────────────────────┐   │
│  │VoiceConfig│  │VoiceAssistant│  │  AudioVisualizer   │   │
│  │ (配置面板) │  │ (语音交互UI)  │  │  (音频可视化)      │   │
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
│  │ REST API  │  │ WebSocket │  │  Settings │  │  Database  │  │
│  │endpoints  │  │  handler  │  │  Config   │  │  Service   │  │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘  └──────┬─────┘  │
│        └──────┬──────┘              │               │        │
│          ┌────┴────┐                │               │        │
│          │ Dialog  │◄───────────────┘               │        │
│          │Manager  │                                │        │
│          └────┬────┘                                │        │
│     ┌─────────┼─────────┐                           │        │
│     ▼         ▼         ▼                           │        │
│  ┌──────┐ ┌──────┐ ┌──────┐                         │        │
│  │ NLU  │ │ ASR  │ │ TTS  │                         │        │
│  │Service│ │Service│ │Service│                       │        │
│  └──┬───┘ └──┬───┘ └──┬───┘                         │        │
│     │        │         │                            │        │
│     ▼        ▼         ▼                            │        │
│  ┌──────┐ ┌──────┐ ┌────────┐                      │        │
│  │ LLM  │ │Whisper│ │Edge TTS│                      │        │
│  │ API  │ │  ASR  │ │        │                      │        │
│  └──────┘ └──────┘ └────────┘                      │        │
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
                                    ├─ 意图路由（天气/设备/闲聊）
                                    └─ LLM 生成回复
                                          ↓
                                   TTS 合成（后台并行）
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
| **TTS** | Edge TTS (`edge-tts`) | 微软在线语音合成，17 种中文音色 |
| **NLU** | 规则引擎 + LLM 兜底 | 正则匹配（阈值 0.60）→ LLM 调用 |
| **LLM** | OpenAI 兼容 API / Ollama | 有 Key → 远程模型；无 Key → 本地模型 |
| **前端框架** | Vue 3 (Composition API) | `script setup` + Vite |
| **前端状态** | Pinia | 状态管理 |
| **WebSocket** | FastAPI WebSocket | 二进制帧传输音频 |
| **部署** | Docker Compose | backend + frontend 双容器 |

---

## 4. 功能特性

### 4.1 已实现功能

| 功能 | 状态 | 说明 |
|------|------|------|
| 语音识别（ASR） | ✅ 已完成 | Whisper 本地模型，支持流式识别，VAD 检测 |
| 语音合成（TTS） | ✅ 已完成 | Edge TTS 在线合成，17 种中文音色，音频队列播放 |
| NLU 意图识别 | ✅ 已完成 | 规则引擎（问候/感谢/告别/能力）+ LLM 兜底 |
| 多轮对话 | ✅ 已完成 | 会话上下文管理（10 轮历史，30 分钟超时） |
| 天气查询 | ✅ 已完成 | 通过 OpenWeatherMap API 查询实时天气 |
| 设备控制 | ✅ 已完成 | 智能家居设备模拟控制（灯/空调/窗帘等） |
| 远程 LLM | ✅ 已完成 | OpenAI 兼容 API（可切换 GPT / DeepSeek 等） |
| 本地 LLM | ✅ 已完成 | Ollama 本地大模型自动切换 |
| 运行时配置 | ✅ 已完成 | 通过 REST API 热更新配置，无需重启 |
| 语音对话开关 | ✅ 已完成 | 可在运行时开启/关闭语音对话功能 |
| 熔断器 | ✅ 已完成 | TTS 熔断器（5 次失败阈值，30s 恢复） |
| 响应缓存 | ✅ 已完成 | ASR 缓存（128 条）、TTS 缓存（256 条）、LLM 语义缓存（256 条，TTL 300s） |
| 并发控制 | ✅ 已完成 | ASR 并发数 2、TTS 并发数 2、LLM 连接池 5 |
| 二进制帧传输 | ✅ 已完成 | WebSocket 二进制帧传输 TTS 音频，节省 ~33% 带宽 |
| 音频可视化 | ✅ 已完成 | 实时频率柱状图（录制模式）+ 音量指示条（播放模式） |
| 前端模型状态指示 | ✅ 已完成 | 顶部指示条显示当前使用本地模型还是远程 AI |

### 4.2 功能模块说明

#### 语音对话（核心）
- 长按录音按钮说话，松手自动发送
- 后端流式接收音频 → ASR 识别 → NLU 理解 → LLM 生成 → TTS 合成
- TTS 音频通过 WebSocket 二进制帧实时返回
- 前端 AudioQueue 顺序播放，不重叠

#### 意图识别
- **规则引擎**：快速匹配问候、感谢、告别、能力介绍等高频场景
- **LLM 兜底**：规则匹配置信度低于 0.60 时，调用 LLM 进行意图分类
- 支持实体抽取：城市、日期、时间、设备名、操作类型、歌手、流派

#### 本地/远程 LLM 自动切换
- 用户在配置面板填写了有效的 API Key → 使用远程 LLM
- 未填写 API Key → 自动切换到本地 Ollama（`http://localhost:11434/v1`）
- 切换过程无需重启服务，前端实时显示当前模式

---

## 5. 环境准备

### 5.1 系统要求

| 依赖 | 版本要求 | 用途 |
|------|---------|------|
| Python | 3.11+ | 后端运行环境 |
| Node.js | 18+ | 前端构建运行 |
| FFmpeg | 任意版本 | 音频格式转换（Whisper 需要） |
| Ollama（可选） | 最新版 | 本地大模型推理 |
| Docker（可选） | 24+ | 容器化部署 |

### 5.2 安装 Ollama（本地大模型）

如需要使用本地大模型，请安装并启动 Ollama：

```bash
# 下载安装：https://ollama.com/download

# 拉取推荐模型（至少 7B 以获得较好效果）
ollama pull qwen2.5:7b

# 启动 Ollama 服务（默认监听 11434 端口）
ollama serve
```

验证 Ollama 是否正常工作：

```bash
curl http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5:7b","messages":[{"role":"user","content":"你好"}]}'
```

### 5.3 安装 FFmpeg

```bash
# Windows (使用 winget)
winget install ffmpeg

# 或访问 https://ffmpeg.org/download.html 下载安装

# 验证安装
ffmpeg -version
```

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

前端默认运行在 `http://localhost:5173`。

### 6.3 验证启动

```bash
# 检查后端健康状态
curl http://localhost:8000/api/v1/health/status

# 预期返回
# {"status":"healthy","version":"1.0.0","ai_key_configured":false,"enable_voice_dialogue":true}
```

浏览器打开 `http://localhost:5173`，应能看到：
- 顶部标题「小玥 AI 语音助手」
- 模型状态指示条（绿色=远程 AI / 橙色=本地模型）
- 中央录音按钮
- 右下角⚙️设置按钮

---

## 7. 配置说明

### 7.1 环境变量配置（.env 文件）

后端 `.env` 文件位于 `voice-assistant/backend/.env`，从 `.env.example` 复制后修改：

```ini
# ---------- 服务器配置 ----------
HOST=0.0.0.0
PORT=8000
DEBUG=true

# ---------- OpenAI API 配置 ----------
OPENAI_API_KEY=sk-your-openai-api-key-here
OPENAI_MODEL=gpt-3.5-turbo

# ---------- 本地大模型配置（无 API Key 时自动启用） ----------
# LOCAL_LLM_API_BASE=http://localhost:11434/v1
# LOCAL_LLM_MODEL=qwen2.5:7b

# ---------- 语音识别 (ASR) 配置 ----------
ASR_ENGINE=whisper
WHISPER_MODEL_SIZE=base
ASR_DEFAULT_LANGUAGE=zh
VAD_SENSITIVITY=2

# ---------- 语音合成 (TTS) 配置 ----------
TTS_ENGINE=edge-tts
TTS_VOICE=zh-CN-XiaoxiaoNeural
TTS_SPEED=1.0
TTS_VOLUME=1.0

# ---------- 天气 API 配置 ----------
WEATHER_API_KEY=your-weather-api-key-here
WEATHER_API_URL=http://api.openweathermap.org/data/2.5
WEATHER_UNITS=metric

# ---------- 功能开关 ----------
ENABLE_VOICE_DIALOGUE=true

# ---------- 数据库配置 ----------
DATABASE_URL=sqlite:///./data/voice_assistant.db

# ---------- 日志配置 ----------
LOG_LEVEL=INFO
LOG_FILE=logs/voice_assistant.log
```

### 7.2 运行时配置（通过 API 热更新）

无需修改 `.env` 文件，通过 REST API 动态修改配置：

**获取当前配置：**

```bash
curl http://localhost:8000/api/v1/settings
```

**更新配置：**

```bash
curl -X POST http://localhost:8000/api/v1/settings \
  -H "Content-Type: application/json" \
  -d '{
    "enable_voice_dialogue": true,
    "openai_api_key": "sk-xxx",
    "openai_api_base": "https://api.openai.com/v1",
    "local_llm_api_base": "http://localhost:11434/v1",
    "local_llm_model": "qwen2.5:7b"
  }'
```

**注意**：
- `openai_api_base` 默认使用 OpenAI 官方地址，可改为任何兼容 OpenAI API 的服务地址（如 DeepSeek、通义千问等）
- `openai_api_key` 为空时，系统自动使用本地大模型（Ollama）
- `enable_voice_dialogue` 设为 `false` 时，WebSocket 语音连接将被拒绝
- 所有修改实时生效，无需重启服务

### 7.3 前端配置

前端配置文件位于 `voice-assistant/frontend/.env`：

```ini
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000/ws/voice
```

生产环境配置在 `voice-assistant/frontend/.env.production` 中设置。

### 7.4 配置优先级

```
运行时配置 (POST /api/v1/settings)  >  环境变量 (.env)  >  代码默认值
```

---

## 8. API 参考

### 8.1 REST 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 根路径重定向到 /docs |
| GET | `/health` | 健康检查（Docker 健康检查用） |
| GET | `/api/v1/health/status` | 详细健康状态（含版本、配置状态） |
| GET | `/api/v1/settings` | 获取当前运行时配置 |
| POST | `/api/v1/settings` | 更新运行时配置 |
| POST | `/api/v1/voice/transcribe` | 语音文件转文字 |
| POST | `/api/v1/voice/synthesize` | 文字转语音 |
| POST | `/api/v1/conversation/start` | 开始新对话 |
| POST | `/api/v1/conversation/message` | 发送文本消息 |
| GET | `/api/v1/functions/weather` | 查询天气 |
| POST | `/api/v1/functions/device/control` | 设备控制 |

### 8.2 详细接口说明

#### 健康检查

```
GET /api/v1/health/status

响应:
{
  "status": "healthy",
  "version": "1.0.0",
  "ai_key_configured": false,
  "enable_voice_dialogue": true,
  "using_local_llm": true,
  "voice_dialogue_ready": true
}
```

#### 获取配置

```
GET /api/v1/settings

响应:
{
  "enable_voice_dialogue": true,
  "voice_dialogue_ready": true,
  "ai_key_configured": false,
  "using_local_llm": true,
  "local_llm_api_base": "http://localhost:11434/v1",
  "local_llm_model": "qwen2.5:7b",
  "effective_api_base": "http://localhost:11434/v1",
  "effective_model": "qwen2.5:7b",
  "openai_api_base": "https://api.openai.com/v1",
  "whisper_model_size": "base",
  "tts_voice": "zh-CN-XiaoxiaoNeural",
  "vad_sensitivity": 2
}
```

#### 语音识别

```
POST /api/v1/voice/transcribe
Content-Type: multipart/form-data

参数:
  - file: 音频文件（支持 wav, mp3, ogg 等）

响应:
{
  "text": "今天天气怎么样",
  "duration_ms": 1234,
  "language": "zh"
}
```

#### 语音合成

```
POST /api/v1/voice/synthesize
Content-Type: application/json

请求体:
{
  "text": "你好，我是小玥"
}

响应: 二进制音频数据（WAV 格式，Content-Type: audio/wav）
```

#### 对话消息

```
POST /api/v1/conversation/message
Content-Type: application/json

请求体:
{
  "conversation_id": "uuid-string",
  "content": "今天天气怎么样",
  "user_id": "default"
}

响应:
{
  "conversation_id": "uuid-string",
  "reply": "今天北京的天气是晴天，气温25°C...",
  "intent": "weather_query",
  "entities": {"city": "北京"}
}
```

#### 天气查询

```
GET /api/v1/functions/weather?city=北京&date=today

响应:
{
  "city": "北京",
  "date": "2024-01-15",
  "temperature": 25,
  "description": "晴天",
  "humidity": 45,
  "wind_speed": 3.5,
  "feels_like": 24
}
```

#### 设备控制

```
POST /api/v1/functions/device/control
Content-Type: application/json

请求体:
{
  "device": "灯",
  "action": "打开",
  "value": null
}

响应:
{
  "success": true,
  "message": "灯已打开",
  "device": "灯",
  "status": "on"
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

**音频帧示例：**

```
字节 [0]       = 0x01        (类型：音频数据)
字节 [1-4]     = 头部长度 (大端序 uint32)
字节 [5..HL]   = JSON 头     (包含 session_id, sequence, is_end 等信息)
字节 [HL+1..]  = Opus 编码的音频数据
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
  │                        │── LLM 生成回复
  │                        │── TTS 合成（后台）
  │                        │
  │←── status(listening) ─┤  状态：正在识别
  │←── status(processing) ─┤  状态：正在处理
  │←── text({"text":...}) ─┤  文本回复（先返回）
  │←── [二进制音频帧 0x01] ┤  TTS 音频块（后台返回）
  │←── [二进制音频帧 0x02] ┤  TTS 传输结束
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

# 编辑 .env 填写配置
notepad backend\.env

# 启动全部服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

服务地址：
- 前端：`http://localhost:5173`
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
set OPENAI_API_KEY=sk-xxx

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

1. 检查网络是否可访问 `edge-tts` 服务
2. 检查浏览器是否允许音频自动播放
3. 查看后端日志是否有 TTS 错误

### Q4: 如何使用其他 LLM 提供方？

修改运行时配置中的 `openai_api_base` 即可：

```bash
# DeepSeek
openai_api_base: "https://api.deepseek.com/v1"

# 通义千问
openai_api_base: "https://dashscope.aliyuncs.com/compatible-mode/v1"

# 本地 Ollama
openai_api_base: "http://localhost:11434/v1"
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
│   │   │   ├── tts.py              # 语音合成 (Edge TTS + 缓存)
│   │   │   ├── nlu.py              # 自然语言理解 (规则 + LLM 兜底)
│   │   │   ├── dialog.py           # 对话管理 (状态机 + 上下文)
│   │   │   ├── database.py         # 数据库服务
│   │   │   └── optimization.py     # 优化工具 (连接池/熔断器/重试)
│   │   ├── functions/
│   │   │   ├── __init__.py
│   │   │   ├── weather.py          # 天气查询
│   │   │   ├── device.py           # 设备控制
│   │   │   └── services.py         # 函数服务注册
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   └── models.py           # 数据模型
│   │   └── utils/
│   │       ├── __init__.py
│   │       └── helpers.py          # 工具函数
│   ├── tests/                      # 单元测试
│   ├── .env.example                # 环境变量模板
│   ├── requirements.txt            # Python 依赖
│   ├── Dockerfile
│   └── main.py
├── frontend/                       # Vue 3 前端
│   ├── src/
│   │   ├── App.vue                 # 根组件 (布局 + 模型状态指示)
│   │   ├── main.js                 # 入口文件
│   │   ├── components/
│   │   │   ├── VoiceAssistant.vue  # 语音助手交互组件
│   │   │   ├── VoiceConfig.vue     # 配置面板
│   │   │   └── AudioVisualizer.vue # 音频可视化
│   │   └── composables/
│   │       └── useVoiceChat.js     # WebSocket + 录音 + TTS 播放
│   ├── package.json
│   ├── vite.config.js
│   ├── Dockerfile
│   └── nginx.conf
├── docker-compose.yml
├── nginx.conf
└── README.md
```

### 支持的 Edge TTS 中文音色

| 音色名称 | 性别 | 风格 |
|---------|------|------|
| zh-CN-XiaoxiaoNeural | 女声 | 自然，推荐 |
| zh-CN-YunxiNeural | 男声 | 自然 |
| zh-CN-YunjianNeural | 男声 | 自然 |
| zh-CN-XiaoyiNeural | 女声 | 活泼 |
| zh-CN-YunyangNeural | 男声 | 新闻播报 |
| zh-CN-XiaochenNeural | 女声 | 轻松 |
| zh-CN-XiaohanNeural | 女声 | 温柔 |
| zh-CN-XiaomengNeural | 女声 | 活泼 |
| zh-CN-XiaomoNeural | 女声 | 亲切 |
| zh-CN-XiaoqiuNeural | 女声 | 自然 |
| zh-CN-XiaoruiNeural | 女声 | 成熟 |
| zh-CN-XiaoshuangNeural | 女声 | 儿童 |
| zh-CN-XiaoyanNeural | 女声 | 自然 |
| zh-CN-XiaoyouNeural | 女声 | 儿童 |
| zh-CN-YunhaoNeural | 男声 | 深沉 |
| zh-CN-YunxiaNeural | 男声 | 自然 |
| zh-HK-HiuGaaiNeural | 女声 | 粤语 |
| zh-HK-HiuMaanNeural | 女声 | 粤语 |
| zh-HK-WanLungNeural | 男声 | 粤语 |

---

> **版本**: 1.0.0 | **最后更新**: 2026-06-23
>
> 如有问题，请查看后端日志或提 Issue。
