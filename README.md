# 小玥 AI 语音助手 — 项目介绍

> 智能语音交互系统：语音输入 → ASR 识别 → NLU 理解 → 多智能体协同 → LLM 回复 → TTS 语音合成，全链路闭环。

---

## 仓库结构

```
XIaoRAI/
├── voice-assistant/        # 主项目（推荐）— 小玥 AI 语音助手 v1.1.0
│   ├── backend/            # FastAPI + Python 后端
│   ├── frontend/           # Vue 3 + Vite 前端
│   ├── docs/               # 用户手册、前端指南、设计系统、功能路线图
│   ├── docker-compose.yml  # 容器化部署
│   └── README.md           # 详细操作文档
│
└── xiaoRAI/                # 早期版本 / 备份
    ├── docs_upload/        # 旧版文档备份（v1.0.0）
    └── frontend/           # 旧版前端实现
```

---

## 项目简介

**小玥 AI 语音助手** 是一个面向中文用户的全栈语音交互助手，强调「语音即主角」的交互体验。前端以「月夜 · 明珠」为设计主题，将助手具象化为舞台中央一颗会呼吸的光球；后端通过 FastAPI 提供 REST API 与 WebSocket 实时语音通道。

### 核心能力

| 能力 | 说明 |
|------|------|
| **语音对话** | 浏览器端录音 → Whisper ASR → 多智能体路由 → LLM 生成 → AI 语音合成播报 |
| **多智能体协同** | Coordinator 自动将任务路由到代码专家、创意写作、数据分析、翻译官等专精智能体 |
| **多 Provider 管理** | LLM / TTS 均采用可插拔 Provider 注册表，支持智谱、DeepSeek、Ollama 等热切换 |
| **技能与 MCP 扩展** | 内置天气、设备、日程、音乐、搜索、计算器等技能，并可通过 MCP 接入外部工具 |
| **运行时热更新** | 配置、Provider、智能体均可通过 API 在线修改，无需重启服务 |
| **安全配置** | 写接口支持 API Token 鉴权，持久化 API Key 使用 Fernet 加密 |

---

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 后端框架 | Python 3.11+ / FastAPI | 异步 Web 框架 |
| ASR | OpenAI Whisper + WebRTC VAD | 本地语音识别 |
| TTS | 智谱 GLM-TTS / OpenAI 兼容 TTS | AI 语音大模型合成 |
| NLU | 规则引擎 + LLM 兜底 | 意图识别与实体抽取 |
| LLM | OpenAI 兼容 API | 多 Provider 注册表 |
| 多智能体 | 自研 AgentRegistry / Orchestrator | 协调者 + 专精智能体 |
| 技能扩展 | Skill Registry + MCP Bridge | 内置技能 + 外部 MCP |
| 前端 | Vue 3 Composition API + Vite | 单页应用 |
| 部署 | Docker Compose | 前后端双容器 |

---

## 界面设计「月夜 · 明珠」

v1.1.0 起前端重设计为语音优先的暗色主题界面：

- **玥珠**：舞台中央的 Canvas 呼吸光球，待机 / 聆听 / 思索 / 应答四态各有专属动效。
- **双声部对话流**：去气泡化，以月光暖金标识助手、青瓷冷绿标识用户。
- **环境层**：星野背景、月轮、极光渐变，营造「月夜」氛围。

详见：
- `voice-assistant/docs/design-moonlight.md` — 设计系统说明
- `voice-assistant/docs/frontend.md` — 前端开发指南
- `voice-assistant/docs/feature-roadmap.md` — 功能补全技术文档
- `voice-assistant/docs/user-guide.md` — 终端用户使用手册

---

## 快速开始

### 1. 启动后端

```bash
cd voice-assistant/backend
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux / macOS

pip install -r requirements.txt
copy .env.example .env          # Windows
# cp .env.example .env         # Linux / macOS

python main.py
```

后端默认运行在 `http://localhost:8000`，API 文档见 `http://localhost:8000/docs`。

### 2. 启动前端

```bash
cd voice-assistant/frontend
npm install
npm run dev
```

前端默认运行在 `http://localhost:3000`。

### 3. Docker Compose 部署（推荐生产环境）

```bash
cd voice-assistant
copy backend\.env.example backend\.env   # Windows
# cp backend/.env.example backend/.env   # Linux / macOS

docker-compose up -d
```

---

## 关键文档索引

| 文档 | 路径 | 内容 |
|------|------|------|
| 操作文档 | `voice-assistant/README.md` | 架构、API、WebSocket、部署、FAQ |
| 使用手册 | `voice-assistant/docs/user-guide.md` | 终端用户安装与使用 |
| 设计系统 | `voice-assistant/docs/design-moonlight.md` | 「月夜 · 明珠」设计概念与 Token |
| 前端指南 | `voice-assistant/docs/frontend.md` | Vue 3 开发、目录结构、接口说明 |
| 功能路线图 | `voice-assistant/docs/feature-roadmap.md` | 唤醒词、VAD、流式响应、记忆、RAG 等补全计划 |
| 更新记录 | `voice-assistant/CHANGELOG.md` | v1.1.0 界面重设计等变更 |

---

## 版本说明

- **voice-assistant/**：`v1.1.0`（当前主推版本），已引入多智能体、Provider 注册表、MCP 扩展、AI 语音大模型 TTS、「月夜 · 明珠」新界面。
- **xiaoRAI/docs_upload/**：`v1.0.0`（旧版备份），使用 Edge TTS、本地/远程 LLM 自动切换、AudioVisualizer 音频可视化。

---

## 贡献与反馈

欢迎通过 Issue 或 Pull Request 提交问题与改进建议。开发前请先阅读 `voice-assistant/docs/frontend.md` 与 `voice-assistant/docs/design-moonlight.md`，确保新代码与现有设计系统保持一致。
