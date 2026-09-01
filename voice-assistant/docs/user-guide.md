# 小玥 AI 语音助手 — 使用手册

> 版本：v1.0.0
> 面向对象：终端用户、运维人员
> 技术架构：FastAPI 后端（:8000）+ Vue 3 前端（:3000）

本文档介绍如何安装、配置并使用「小玥 AI 语音助手」。技术细节与架构说明请参考 [README](../README.md)。

---

## 目录

1. [简介](#1-简介)
2. [系统要求](#2-系统要求)
3. [快速开始](#3-快速开始)
4. [配置说明](#4-配置说明)
5. [使用指南](#5-使用指南)
6. [功能说明](#6-功能说明)
7. [管理 API](#7-管理-api)
8. [常见问题](#8-常见问题)
9. [停止服务](#9-停止服务)

---

## 1. 简介

小玥是一个**语音优先**的智能助手，具备以下核心能力：

- **语音对话**：浏览器端录音 → 后端 ASR 识别 → LLM 生成回复 → AI 语音合成播报
- **多智能体协同**：协调者自动把任务路由到「代码专家 / 创意写作 / 数据分析 / 翻译官」等专精智能体
- **多 Provider 管理**：支持任意兼容 OpenAI 协议的 LLM 接口，可动态切换
- **内置技能**：天气查询、智能家居控制、日程、音乐、联网搜索、计算器、日期时间、讲笑话
- **MCP 扩展**：通过 MCP 协议接入外部工具服务器

前端采用「月夜 · 明珠」设计：中心是实时渲染的呼吸光球（玥珠），语音即主角。

---

## 2. 系统要求

| 项 | 要求 |
|----|------|
| 操作系统 | Windows / macOS / Linux |
| Python | 3.10+（推荐 3.11） |
| Node.js | 18+（推荐 20） |
| 网络 | 需要访问 LLM API（以及首次启动下载语音识别模型） |
| 浏览器 | 支持 WebSocket 与麦克风的现代浏览器（Chrome / Edge 推荐） |

> 语音识别首次启动会自动下载 Whisper base 模型（约 150MB），请保持网络畅通。

---

## 3. 快速开始

### 3.1 启动后端

```bash
cd voice-assistant/backend

# 创建并激活虚拟环境（可选，推荐）
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量（首次；若 .env 已存在且已配置密钥则跳过）
copy .env.example .env        # Windows
cp .env.example .env          # macOS / Linux

# 启动服务
python main.py
```

启动成功后应看到：

```
✅ 数据库初始化完成
✅ 语音识别服务初始化完成（Whisper base）
✅ AI 语音大模型服务（TTS）HTTP 客户端创建完成
✅ 内置技能注册完成（8 个）
✅ Application startup complete
✅ Uvicorn running on http://0.0.0.0:8000
```

### 3.2 启动前端

```bash
cd voice-assistant/frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

> 前端环境变量均为可选，仓库已内置 `.env`。如需自定义（如对接远程后端），直接编辑 `frontend/.env` 即可。

启动成功后访问 **http://localhost:3000**。

### 3.3 验证

```bash
# 后端健康检查
curl http://localhost:8000/health
# => {"status":"healthy","service":"voice-assistant",...}

# 后端交互式 API 文档
# 浏览器打开 http://localhost:8000/docs
```

---

## 4. 配置说明

### 4.1 后端环境变量（`backend/.env`）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `HOST` / `PORT` | 后端监听地址与端口 | `0.0.0.0` / `8000` |
| `DEBUG` | 是否开启热重载（开发用） | `true` |
| `ALLOWED_ORIGINS` | CORS 允许的前端来源 | `http://localhost:3000,...` |
| `API_TOKEN` | 写接口鉴权令牌（为空则关闭鉴权） | 随机字符串 |
| `CRYPTO_KEY` | 加密 `data/*.json` 中 API Key 的密钥 | 随机字符串 |
| `OPENAI_API_KEY` | 默认 LLM Provider 初始 API Key | 空 |
| `OPENAI_API_BASE` | 默认 LLM Provider 接口地址 | `https://api.openai.com/v1` |
| `OPENAI_MODEL` | 默认模型名 | `gpt-3.5-turbo` |
| `OPENAI_MAX_TOKENS` | 单次最大生成 token | `2048` |
| `OPENAI_TEMPERATURE` | 生成温度（0-1） | `0.7` |

> `OPENAI_*` 仅作为 `default` Provider 的初始值，运行期以 `data/llm_providers.json` 为准。

### 4.2 前端环境变量（`frontend/.env`）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `VITE_API_URL` | 后端 HTTP 地址 | `http://localhost:8000` |
| `VITE_WS_URL` | 后端 WebSocket 地址 | `ws://localhost:8000` |
| `VITE_API_TOKEN` | 与后端 `API_TOKEN` 一致，前端自动携带 | 空 |

### 4.3 LLM Provider 管理

LLM Provider 配置持久化在 `backend/data/llm_providers.json`，支持两种修改方式：

1. **通过 API**（推荐）：`POST /api/v1/providers`
2. **直接编辑 JSON 文件**：`backend/data/llm_providers.json`

```json
{
  "name": "default",
  "api_base": "https://api.openai.com/v1",
  "api_key": "sk-...",
  "model": "gpt-3.5-turbo"
}
```

> 安全提示：JSON 中的 `api_key` 建议留空，改为通过 API 提交后由后端用 `CRYPTO_KEY` 加密存储。

### 4.4 语音 Provider 管理

语音合成（TTS）使用 AI 语音大模型，配置持久化在 `backend/data/voice_providers.json`，可通过 `POST /api/v1/voice-providers` 管理。

### 4.5 安全配置（重要）

- **API Token 鉴权**：后端已配置随机 `API_TOKEN`，所有 `POST / PUT / PATCH / DELETE` 写接口都需要携带 `X-API-Token` 头（或 `Authorization: Bearer <token>`）。前端在 `.env` 配置 `VITE_API_TOKEN` 后会自动携带。
- **密钥加密**：`data/*.json` 中的 API Key 使用 `CRYPTO_KEY`（Fernet 派生）加密存储，避免明文泄露。

---

## 5. 使用指南

### 5.1 语音对话

1. 浏览器打开 http://localhost:3000，允许麦克风权限。
2. **按住**界面中的麦克风按钮（或按住空格键）开始说话。
3. 松开后自动停止录音，系统依次完成「识别 → 思考 → 语音回复」。
4. 回复以**语音播报 + 文字流式显示**两种方式呈现。

### 5.2 文字对话

1. 在底部输入框输入文字。
2. 按 **Enter** 发送（Shift + Enter 换行）。
3. AI 回复会在右侧对话流流式显示，并同步语音播报。

### 5.3 状态说明

界面中心的「玥珠」光球会随状态变化：

| 状态 | 视觉表现 | 含义 |
|------|---------|------|
| 待机 `idle` | 缓慢呼吸 | 等待输入 |
| 聆听 `listening` | 外环泛青瓷色 | 正在录音 |
| 思索 `thinking` | 粒子加速旋转 | 正在处理 |
| 应答 `speaking` | 声纹柱脉冲 | 正在播报 |

### 5.4 快捷键

| 按键 | 动作 |
|------|------|
| 按住空格 | 按住说话（录音） |
| Enter | 发送文字 |
| Shift + Enter | 换行 |

---

## 6. 功能说明

### 6.1 多智能体

系统内置一个「协调者」+ 五个「专精智能体」，协调者根据任务类型自动路由：

| 智能体 | 角色 | 适用场景 |
|--------|------|---------|
| `general_chat` | 通用聊天 | 闲聊、问候、情感支持 |
| `code_expert` | 代码专家 | 编程、调试、代码审查 |
| `creative` | 创意写作 | 文案、故事、诗歌、头脑风暴 |
| `analyst` | 数据分析师 | 逻辑推理、数据分析、数学计算 |
| `translator` | 翻译官 | 多语言翻译、本地化 |

在「设置」中可为每个智能体配置独立模型、系统提示词、性格与装配技能。

### 6.2 内置技能

| 技能 | 名称 | 示例指令 |
|------|------|---------|
| 天气查询 | `weather` | 「今天北京天气怎么样？」 |
| 智能家居控制 | `device_control` | 「打开客厅的灯」 |
| 日程管理 | `schedule` | 「提醒我明天上午 10 点开会」 |
| 音乐播放 | `music_play` | 「播放周杰伦的歌」 |
| 联网搜索 | `web_search` | 「搜索一下最新的 AI 新闻」 |
| 计算器 | `calculator` | 「计算 25 乘以 8 加 3」 |
| 日期时间 | `time_date` | 「今天是星期几？」 |
| 讲笑话 | `joke` | 「讲个笑话」 |

> 智能家居控制当前为**模拟设备**，真实 IoT 对接见 [feature-roadmap.md](feature-roadmap.md)。

### 6.3 MCP 技能扩展

系统通过 MCP 协议接入外部工具服务器，每个 MCP 服务器的工具会注册为技能（名称 `mcp_<server>`）。MCP 服务器配置位于 `backend/data/mcp_servers.json`。

---

## 7. 管理 API

后端提供 REST API 与交互式文档（http://localhost:8000/docs）。

| 前缀 | 用途 |
|------|------|
| `/api/v1/health` | 健康检查 |
| `/api/v1/voice` | 语音处理 |
| `/api/v1/conversation` | 对话管理 |
| `/api/v1/functions` | 功能调用 |
| `/api/v1/settings` | 配置管理 |
| `/api/v1/agents` | 多智能体管理 |
| `/api/v1/providers` | LLM Provider 管理 |
| `/api/v1/voice-providers` | 语音 Provider 管理 |
| `/api/v1/skills` | 技能管理 |

**鉴权**：所有写操作（`POST/PUT/PATCH/DELETE`）需携带请求头：

```bash
curl -X POST http://localhost:8000/api/v1/providers \
  -H "X-API-Token: <你的 API_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"name":"default","api_base":"https://api.openai.com/v1","model":"gpt-3.5-turbo"}'
```

---

## 8. 常见问题

**Q1：启动后端报错 `ModuleNotFoundError`？**
未安装依赖，请先执行 `pip install -r requirements.txt`。

**Q2：首次启动很慢？**
首次启动会下载 Whisper 语音识别模型（约 150MB），之后会缓存到本地，启动会明显加快。

**Q3：语音识别 / 播报没声音？**
- 检查浏览器是否授予麦克风权限；
- 确认后端日志无 ASR / TTS 报错；
- 确认语音 Provider 已正确配置 API Key。

**Q4：调用 LLM 报 401 / 403？**
检查 `data/llm_providers.json` 中 `default` Provider 的 `api_key` 与 `api_base` 是否正确。

**Q5：写接口返回 401 未授权？**
写接口需要 `X-API-Token` 头，前端请在 `frontend/.env` 配置 `VITE_API_TOKEN`（与后端 `API_TOKEN` 一致）。

**Q6：如何查看日志？**
后端日志输出到终端；同时写入 `backend/logs/voice_assistant.log`。

---

## 9. 停止服务

- 后端：在运行 `python main.py` 的终端按 `Ctrl + C`。
- 前端：在运行 `npm run dev` 的终端按 `Ctrl + C`。

---

> 更多技术细节、架构设计与 API 参考请见 [README](../README.md)。
