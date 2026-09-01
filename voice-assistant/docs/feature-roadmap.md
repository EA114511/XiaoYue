# 小玥 AI 语音助手 — 功能补全技术文档

> **版本**: v1.0.0  
> **用途**: 供 AI 助手按本文档直接实施代码补全  
> **关联项目**: `voice-assistant/`（FastAPI 后端 + Vue3 前端）

---

## 文档导读

本文档按 **优先级（高 → 中 → 低）** 列出当前项目缺失的全部功能，每个功能包含：
- `目标`：一句话定义
- `当前问题`：现有代码的短板
- `技术方案`：实现思路与选型
- `实现步骤`：按顺序执行的文件操作
- `涉及文件`：需要新建/修改的代码文件
- `关键代码结构`：核心类/函数/接口的伪代码或设计
- `依赖项`：需要新增的 pip/npm 包
- `验收标准`：完成后应验证的行为

> **实施原则**：
> - 后端新增文件统一放在 `backend/app/` 下，按模块分子目录
> - 前端新增组件统一放在 `frontend/src/components/` 下
> - 新增依赖写入 `requirements.txt` / `package.json`
> - 保持与现有代码风格一致（PEP8 / Vue Composition API）

---

## 第一部分：高优先级（决定"语音助手"核心体验）

### 1. 唤醒词检测（Wake Word Detection）

#### 目标
无需手动点击麦克风，用户说出唤醒词（如"小玥小玥"）即可激活录音。

#### 当前问题
`useVoiceChat.js` 中录音必须通过 `onMicDown` / `startRecording()` 手动触发，无持续监听能力。

#### 技术方案
采用 **Porcupine**（picovoice 开源唤醒词引擎，支持中文自定义唤醒词），在浏览器端通过 WebAssembly 运行，持续监听麦克风音频流。

#### 依赖项
```bash
# 前端
npm install @picovoice/porcupine-web @picovoice/web-voice-processor

# 后端（如需服务端唤醒词验证，可选）
# 无需后端依赖，纯前端实现
```

#### 涉及文件
- `frontend/src/composables/useWakeWord.js`（新建）
- `frontend/src/components/VoiceAssistant.vue`（修改：集成唤醒词）

#### 实现步骤

**Step 1：创建唤醒词组合式 API**

```javascript
// frontend/src/composables/useWakeWord.js
import { Porcupine } from '@picovoice/porcupine-web'
import { WebVoiceProcessor } from '@picovoice/web-voice-processor'

export function useWakeWord({ onWake, keywordPath = '/wake-word/小玥小玥.ppn' }) {
  let porcupine = null
  let webVp = null
  let isListening = false

  async function init(accessKey) {
    porcupine = await Porcupine.create(accessKey, [keywordPath], [0.5])
    webVp = await WebVoiceProcessor.instance()
  }

  async function start() {
    if (!porcupine) return
    await webVp.subscribe(porcupine)
    isListening = true
    porcupine.keywordDetectionCallback = (keywordLabel) => {
      if (keywordLabel !== -1) onWake()
    }
  }

  async function stop() {
    if (webVp && porcupine) {
      await webVp.unsubscribe(porcupine)
    }
    isListening = false
  }

  async function release() {
    await stop()
    if (porcupine) porcupine.terminate()
  }

  return { init, start, stop, release, isListening }
}
```

**Step 2：在 VoiceAssistant.vue 中集成**

在 `<script setup>` 中：
```javascript
import { useWakeWord } from '@/composables/useWakeWord'

const { start: startWakeWord, stop: stopWakeWord } = useWakeWord({
  onWake: () => {
    // 触发一次录音
    if (!isRecording.value && !isProcessing.value) {
      startRecording()
      // 可选：播放"叮"提示音
      playWakeSound()
    }
  }
})

// 组件挂载后启动唤醒词监听
onMounted(() => startWakeWord())
onUnmounted(() => stopWakeWord())
```

#### 验收标准
- [ ] 页面打开后，麦克风处于低功耗监听状态
- [ ] 说出"小玥小玥"后，自动触发录音，无需手动点击
- [ ] 唤醒后播放简短提示音反馈

---

### 2. 前端 VAD + 自动断句（Voice Activity Detection）

#### 目标
录音时自动检测用户说话结束，自动停止录音并发送，无需手动松开按钮。

#### 当前问题
录音通过 `mousedown/mouseup` 或 `touchstart/touchend` 控制，用户必须主动松手。

#### 技术方案
使用 **Silero VAD**（通过 ONNX Runtime Web 在浏览器运行）或 **WebRTC VAD** 的 JS 版本。检测到连续静音 800ms 即判定为说话结束。

#### 依赖项
```bash
npm install onnxruntime-web  # Silero VAD 依赖
```

#### 涉及文件
- `frontend/src/composables/useVAD.js`（新建）
- `frontend/src/composables/useVoiceChat.js`（修改：集成 VAD 自动停止）

#### 实现步骤

**Step 1：创建 VAD 模块**

```javascript
// frontend/src/composables/useVAD.js
import { InferenceSession, Tensor } from 'onnxruntime-web'

export class VADProcessor {
  constructor({ onSpeechStart, onSpeechEnd, silenceTimeoutMs = 800 }) {
    this.onSpeechStart = onSpeechStart
    this.onSpeechEnd = onSpeechEnd
    this.silenceTimeoutMs = silenceTimeoutMs
    this.isSpeech = false
    this.silenceTimer = null
    this.sampleRate = 16000
  }

  async loadModel(modelUrl = '/models/silero_vad.onnx') {
    this.session = await InferenceSession.create(modelUrl)
  }

  async process(audioData) {
    // audioData: Float32Array, 16000Hz, 30ms 帧
    const input = new Tensor('float32', audioData, [1, audioData.length])
    const feeds = { input: input }
    const results = await this.session.run(feeds)
    const prob = results.output.data[0]

    const THRESHOLD = 0.5
    if (prob > THRESHOLD) {
      if (!this.isSpeech) {
        this.isSpeech = true
        this.onSpeechStart?.()
      }
      clearTimeout(this.silenceTimer)
    } else if (this.isSpeech) {
      clearTimeout(this.silenceTimer)
      this.silenceTimer = setTimeout(() => {
        this.isSpeech = false
        this.onSpeechEnd?.()
      }, this.silenceTimeoutMs)
    }
  }
}
```

**Step 2：修改 useVoiceChat.js**

在 `startRecording()` 中：
```javascript
// 创建 VAD 处理器
const vad = new VADProcessor({
  onSpeechEnd: () => {
    stopRecording()  // 自动停止
  }
})
await vad.loadModel()

// 在 ondataavailable 中把音频送入 VAD
mediaRecorder.ondataavailable = async (event) => {
  if (event.data.size > 0) {
    // 发送音频到后端
    sendAudioChunk(event.data)
    // 同时送入 VAD 分析
    const buffer = await event.data.arrayBuffer()
    const floatData = convertToFloat32(buffer)
    await vad.process(floatData)
  }
}
```

#### 验收标准
- [ ] 按住麦克风开始说话，说完后 800ms 内自动停止录音
- [ ] 安静环境下不误触发
- [ ] 说话被打断（短暂停顿后继续）不会过早停止

---

### 3. 语音打断（Barge-in）

#### 目标
AI 正在播报 TTS 时，用户可以直接说话打断它，立即停止播放并进入聆听状态。

#### 当前问题
`AudioQueue` 播放期间没有监听麦克风，用户无法语音打断。

#### 技术方案
播放 TTS 期间保持唤醒词/VAD 监听。检测到用户语音时：
1. 立即停止 `AudioQueue` 播放
2. 清空音频队列
3. 立即开始新一轮录音

#### 涉及文件
- `frontend/src/composables/useVoiceChat.js`（修改）
- `frontend/src/components/VoiceAssistant.vue`（修改）

#### 实现步骤

在 `useVoiceChat.js` 中，当 `isPlaying` 为 `true` 时，启动一个低功耗的音频分析循环：

```javascript
// 在 audioQueue 播放期间持续监听
async function monitorBargeIn() {
  if (!mediaStream.value) {
    // 获取麦克风但不录制，仅用于 VAD 分析
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { sampleRate: 16000 } })
    const audioContext = new AudioContext({ sampleRate: 16000 })
    const source = audioContext.createMediaStreamSource(stream)
    const processor = audioContext.createScriptProcessor(4096, 1, 1)

    processor.onaudioprocess = (e) => {
      const data = e.inputBuffer.getChannelData(0)
      const volume = data.reduce((a, b) => a + Math.abs(b), 0) / data.length
      if (volume > 0.02) {  // 音量阈值
        // 用户说话了，打断！
        audioQueue.stop()
        isPlaying.value = false
        stopAllVoicePlay()
        // 立即开始新录音
        startRecording()
        // 关闭打断监听器
        processor.disconnect()
        source.disconnect()
        stream.getTracks().forEach(t => t.stop())
      }
    }

    source.connect(processor)
    processor.connect(audioContext.destination)

    // 播放结束时自动关闭
    watch(isPlaying, (playing) => {
      if (!playing) {
        processor.disconnect()
        source.disconnect()
        stream.getTracks().forEach(t => t.stop())
      }
    })
  }
}
```

在 `VoiceAssistant.vue` 中，当 `isPlaying` 变为 `true` 时调用 `monitorBargeIn()`。

#### 验收标准
- [ ] AI 正在播报时，用户直接说话，TTS 立即停止
- [ ] 打断后立即进入聆听状态（无需唤醒词）
- [ ] 安静环境下，TTS 播放不会被误打断

---

### 4. 流式 LLM 响应（Streaming Response）

#### 目标
LLM 生成回复时，文字逐字/逐句流式显示到前端，而不是等全部生成完才一次性显示。

#### 当前问题
`DialogManager._call_llm()` 和 `AgentOrchestrator._call_agent()` 都是完整等待 LLM 响应后才返回。

#### 技术方案
后端改用 `httpx.stream()` 接收 SSE 流式响应，通过 WebSocket 分块推送到前端。前端逐字显示。

#### 涉及文件
- `backend/app/core/dialog.py`（修改：`_call_llm_stream` 方法）
- `backend/app/core/multi_agent.py`（修改：`_call_agent_stream` 方法）
- `backend/app/api/websocket.py`（修改：新增流式消息类型）
- `frontend/src/composables/useVoiceChat.js`（修改：处理流式文本）
- `frontend/src/components/VoiceAssistant.vue`（修改：流式显示）

#### 实现步骤

**Step 1：后端新增流式 LLM 调用**

在 `backend/app/core/dialog.py` 中新增：

```python
async def _call_llm_stream(self, text: str, context: ConversationContext):
    """流式调用 LLM，yield 文本片段"""
    messages = [
        {"role": "system", "content": system_prompt},
        *context.get_history_messages(max_turns=10),
    ]
    provider = provider_registry.get_default()
    headers = {"Content-Type": "application/json"}
    if provider.api_key:
        headers["Authorization"] = f"Bearer {provider.api_key}"

    async with _llm_http_client.stream(
        "POST",
        f"{provider.api_base}/chat/completions",
        headers=headers,
        json={
            "model": provider.model,
            "messages": messages,
            "stream": True,
            "max_tokens": settings.OPENAI_MAX_TOKENS,
        },
    ) as resp:
        async for line in resp.aiter_lines():
            line = line.strip()
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
                delta = chunk["choices"][0]["delta"].get("content", "")
                if delta:
                    yield delta
            except:
                continue
```

**Step 2：WebSocket 新增流式消息类型**

在 `websocket.py` 的 `_handle_audio` 和 `_handle_text` 中：

```python
# 对话管理改为流式
reply_text = ""
async for delta in self.dialog_manager._call_llm_stream(transcript, context):
    reply_text += delta
    await self._send(session.websocket, {
        "type": "stream_delta",
        "delta": delta,
        "session_id": session.session_id,
    })

# 最后发送结束标记
await self._send(session.websocket, {
    "type": "stream_end",
    "full_text": reply_text,
    "session_id": session.session_id,
})
```

**Step 3：前端处理流式消息**

在 `useVoiceChat.js` 的 `handleTextMessage` 中新增：

```javascript
case 'stream_delta':
  // 累加到当前回复
  response.value += msg.delta
  onResponse(response.value)  // 触发更新
  break

case 'stream_end':
  isProcessing.value = false
  onStatusChange('idle')
  break
```

在 `VoiceAssistant.vue` 中，流式回复显示为逐字打字效果（已存在的流式光标逻辑复用）。

#### 验收标准
- [ ] 用户发送消息后，AI 回复文字逐字出现，而非一次性弹出
- [ ] 流式期间前端状态保持 "thinking"，直到收到 `stream_end`
- [ ] 支持流式文本和流式 TTS 并行（文本先出，TTS 随后播放）

---

### 5. 流式 TTS 播放（Streaming TTS Playback）

#### 目标
LLM 流式输出时，每输出一段文字就立即送入 TTS 合成，边合成边播放，实现"边说边播"。

#### 当前问题
`AIVoiceService.synthesize_stream()` 虽有流式接口，但 WebSocket 端 `_tts_stream_and_send` 是等 LLM 完整回复后才调用 TTS。

#### 技术方案
与流式 LLM 联动：LLM 每输出一句话（以句号/问号/感叹号分割），立即送入 TTS 合成并推送到前端播放。

#### 涉及文件
- `backend/app/api/websocket.py`（修改：流式 LLM + 流式 TTS 联动）
- `backend/app/core/ai_voice.py`（修改：句子级流式合成）

#### 实现步骤

在 `websocket.py` 中创建 `SentenceBuffer` 类：

```python
class SentenceBuffer:
    """累积 LLM 输出，按句子分割后触发 TTS"""
    def __init__(self, on_sentence):
        self.buffer = ""
        self.on_sentence = on_sentence
        self.sentence_end = re.compile(r'[。！？\.\!\?]+')

    def feed(self, text: str):
        self.buffer += text
        # 查找完整句子
        while True:
            match = self.sentence_end.search(self.buffer)
            if not match:
                break
            end_pos = match.end()
            sentence = self.buffer[:end_pos].strip()
            self.buffer = self.buffer[end_pos:]
            if sentence:
                self.on_sentence(sentence)

    def flush(self):
        if self.buffer.strip():
            self.on_sentence(self.buffer.strip())
            self.buffer = ""
```

在 `_handle_text` 流式处理中：

```python
# 创建句子缓冲器，每收到一个完整句子就触发 TTS
sentence_buffer = SentenceBuffer(
    on_sentence=lambda sent: asyncio.create_task(
        self._tts_stream_and_send(session, sent)
    )
)

async for delta in self.dialog_manager._call_llm_stream(text, context):
    sentence_buffer.feed(delta)
    await self._send(session.websocket, {
        "type": "stream_delta",
        "delta": delta,
    })

sentence_buffer.flush()  # 处理最后不完整的句子
```

#### 验收标准
- [ ] LLM 输出"今天北京天气晴朗。"后，TTS 立即开始播报这句
- [ ] 不需要等 LLM 生成完整回复才开始语音播报
- [ ] 多句话时，TTS 按句子顺序连续播放

---

## 第二部分：中优先级（决定助手"智能"程度）

### 6. 长期记忆系统（Long-term Memory）

#### 目标
助手能记住用户的偏好、习惯、身份信息，跨会话保持记忆。

#### 当前问题
对话历史仅保留 10 轮、30 分钟超时清空，每次对话都是"陌生人"。

#### 技术方案
- 后端：SQLite 增加 `memories` 表，存储键值对记忆
- 每次对话前，检索与当前话题相关的记忆注入 system prompt
- 对话结束后，让 LLM 提取本次对话中值得记忆的信息并保存

#### 依赖项
```bash
pip install sentence-transformers  # 用于记忆向量化检索（可选）
```

#### 涉及文件
- `backend/app/core/memory.py`（新建）
- `backend/app/core/dialog.py`（修改：注入记忆）
- `backend/app/core/database.py`（修改：新增 memories 表 + Memory 模型）

#### 实现步骤

**Step 1：数据库模型**

```python
# backend/app/core/database.py
from sqlalchemy import Column, String, DateTime, Text, Float
from datetime import datetime

class Memory(Base):
    __tablename__ = "memories"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(64), index=True)  # 支持多用户
    category = Column(String(32), index=True)  # preference, fact, relationship, habit
    key = Column(String(128), index=True)     # 记忆主题，如"喜欢的音乐"
    value = Column(Text)                       # 记忆内容
    importance = Column(Float, default=1.0)    # 重要度 0-1
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    source_conversation = Column(String(36))   # 来源对话ID
```

**Step 2：记忆管理服务**

```python
# backend/app/core/memory.py
class MemoryService:
    def __init__(self, db_service):
        self.db = db_service

    async def save_memory(self, user_id: str, category: str, key: str, value: str, importance: float = 1.0):
        """保存一条记忆"""
        # 如果已有同类别同 key 的记忆，更新它
        pass

    async def retrieve_memories(self, user_id: str, query: str, limit: int = 5) -> List[Dict]:
        """根据当前对话内容检索相关记忆"""
        # 简单实现：关键词匹配
        # 高级实现：向量化 + 余弦相似度
        pass

    async def extract_memories(self, user_id: str, conversation_history: str) -> List[Dict]:
        """让 LLM 从对话历史中抽取值得记忆的信息"""
        prompt = """从以下对话中，提取用户的偏好、习惯、身份信息等值得长期记忆的内容。
每条记忆用 JSON 格式：{"category": "preference|fact|relationship|habit", "key": "...", "value": "...", "importance": 0.0-1.0}
只返回 JSON 数组，不要其他内容。"""
        # 调用 LLM 提取
        pass
```

**Step 3：在 DialogManager 中注入记忆**

在 `_call_llm()` 中，构建 messages 时：
```python
# 获取相关记忆
memories = await memory_service.retrieve_memories(user_id, text)
memory_text = "\n".join(f"- {m['key']}: {m['value']}" for m in memories)

system_prompt = (
    '你是一个智能语音助手...\n'
    f'\n===== 用户记忆 =====\n{memory_text}\n'
    '请在回答中适当利用上述记忆，让回复更个性化。'
)
```

#### 验收标准
- [ ] 用户说"我喜欢周杰伦"，下次问"放首歌"时，助手能推荐周杰伦的歌
- [ ] 用户说"我是程序员"，后续编程问题的回答更贴合程序员语境
- [ ] 记忆持久化到数据库，重启服务后不丢失

---

### 7. 知识库 / RAG（Retrieval-Augmented Generation）

#### 目标
用户可上传本地文档（PDF/Word/TXT），助手基于文档内容回答问题。

#### 技术方案
- 文档上传 → 文本提取 → 切片（chunk）→ 向量化 → 存入向量数据库（ChromaDB 或 SQLite + 本地向量）
- 问答时检索相关片段，注入 LLM 上下文

#### 依赖项
```bash
pip install chromadb PyPDF2 python-docx sentence-transformers
```

#### 涉及文件
- `backend/app/core/rag.py`（新建）
- `backend/app/api/endpoints.py`（修改：新增上传/管理 API）
- `backend/app/core/database.py`（修改：新增 Document/Chunk 模型）

#### 实现步骤

**Step 1：RAG 服务**

```python
# backend/app/core/rag.py
import chromadb
from sentence_transformers import SentenceTransformer

class RAGService:
    def __init__(self):
        self.client = chromadb.Client()
        self.collection = self.client.get_or_create_collection("knowledge")
        self.encoder = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

    async def add_document(self, doc_id: str, title: str, content: str):
        """文档切片并入库"""
        chunks = self._chunk_text(content, chunk_size=500, overlap=50)
        embeddings = self.encoder.encode(chunks).tolist()
        ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
        metadatas = [{"doc_id": doc_id, "title": title, "chunk_index": i} for i in range(len(chunks))]
        self.collection.add(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)

    async def query(self, question: str, top_k: int = 3) -> List[str]:
        """检索相关片段"""
        embedding = self.encoder.encode([question]).tolist()
        results = self.collection.query(query_embeddings=embedding, n_results=top_k)
        return results['documents'][0] if results['documents'] else []

    def _chunk_text(self, text, chunk_size=500, overlap=50):
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end])
            start = end - overlap
        return chunks
```

**Step 2：DialogManager 集成 RAG**

在 `_handle_general_chat` 中：
```python
# 先检索知识库
rag_chunks = await rag_service.query(text, top_k=3)
if rag_chunks:
    context = "\n\n".join(rag_chunks)
    system_prompt += f"\n\n===== 参考资料 =====\n{context}\n请基于以上资料回答。"
```

**Step 3：新增 API 端点**

```python
# backend/app/api/endpoints.py
@functions.post("/knowledge/upload")
async def upload_knowledge(file: UploadFile):
    # 提取文本（PDF/Word/TXT）
    # 调用 rag_service.add_document()
    pass

@functions.get("/knowledge/query")
async def query_knowledge(q: str):
    chunks = await rag_service.query(q)
    return {"chunks": chunks}
```

#### 验收标准
- [ ] 上传 PDF 后，助手能回答文档中的内容
- [ ] 回答时标注信息来源
- [ ] 支持多文档同时检索

---

### 8. 真实 IoT 设备集成

#### 目标
对接真实智能家居系统，而非模拟设备。

#### 技术方案
- **Home Assistant**: 通过 WebSocket API 连接，控制灯光、空调等
- **米家**: 通过 miio 协议
- **Matter**: 未来兼容

#### 依赖项
```bash
pip install homeassistant-api python-miio
```

#### 涉及文件
- `backend/app/integrations/home_assistant.py`（新建）
- `backend/app/functions/device.py`（修改：对接真实协议）

#### 实现步骤

```python
# backend/app/integrations/home_assistant.py
from homeassistant_api import Client

class HomeAssistantIntegration:
    def __init__(self, url: str, token: str):
        self.client = Client(url, token)

    async def turn_on(self, entity_id: str):
        await self.client.trigger_service("homeassistant", "turn_on", entity_id=entity_id)

    async def turn_off(self, entity_id: str):
        await self.client.trigger_service("homeassistant", "turn_off", entity_id=entity_id)

    async def set_temperature(self, entity_id: str, temp: float):
        await self.client.trigger_service("climate", "set_temperature", entity_id=entity_id, temperature=temp)

    async def list_devices(self):
        states = await self.client.get_states()
        return [{"entity_id": s.entity_id, "name": s.attributes.get("friendly_name"), "state": s.state} for s in states]
```

修改 `device.py`，当配置了 Home Assistant 时走真实接口，否则保持模拟。

#### 验收标准
- [ ] 能控制真实的 Home Assistant 设备
- [ ] 能查询真实设备状态
- [ ] 设备列表动态同步

---

### 9. 闹钟与定时提醒

#### 目标
用户说"5分钟后叫我"或"明天早上8点叫我起床"，助手能准时提醒。

#### 技术方案
- 后端：APScheduler 定时任务调度器
- 提醒触发时：WebSocket 推送提醒消息 / 本地通知

#### 依赖项
```bash
pip install apscheduler
```

#### 涉及文件
- `backend/app/core/scheduler.py`（新建）
- `backend/app/functions/reminder.py`（新建）
- `backend/app/api/endpoints.py`（修改：新增提醒 API）

#### 实现步骤

```python
# backend/app/core/scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

class ReminderScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.scheduler.start()

    def add_reminder(self, reminder_id: str, trigger_time: datetime, callback, *args):
        self.scheduler.add_job(
            callback,
            trigger=DateTrigger(run_date=trigger_time),
            id=reminder_id,
            args=args,
            replace_existing=True,
        )

    def remove_reminder(self, reminder_id: str):
        self.scheduler.remove_job(reminder_id)
```

在 WebSocket handler 中，提醒触发时推送：
```python
async def on_reminder_trigger(session_id: str, message: str):
    websocket = session_manager.get_by_session_id(session_id)
    if websocket:
        await websocket.send_json({
            "type": "reminder",
            "message": message,
            "timestamp": datetime.now().isoformat(),
        })
```

#### 验收标准
- [ ] "5分钟后提醒我喝水" → 5分钟后收到语音提醒
- [ ] "明天早上8点叫我起床" → 准时提醒
- [ ] 支持取消已设置的提醒

---

### 10. 多用户认证系统

#### 目标
支持多个用户独立使用，每个用户有自己的配置、对话历史、记忆。

#### 技术方案
- JWT Token 认证
- SQLite 增加 `users` 表
- WebSocket 连接时通过 query param 或首次消息传递 token

#### 依赖项
```bash
pip install python-jose[cryptography] passlib[bcrypt]
```

#### 涉及文件
- `backend/app/core/auth.py`（新建）
- `backend/app/core/database.py`（修改：新增 User 模型）
- `backend/app/api/endpoints.py`（修改：新增登录/注册 API）
- `backend/app/api/websocket.py`（修改：鉴权）

#### 实现步骤

```python
# backend/app/core/auth.py
from jose import jwt, JWTError
from passlib.context import CryptContext

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=24))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None
```

WebSocket 连接时鉴权：
```python
async def voice_websocket_endpoint(websocket: WebSocket):
    token = websocket.query_params.get("token")
    user_id = verify_token(token)
    if not user_id:
        await websocket.close(code=4001, reason="Unauthorized")
        return
    # 后续所有操作关联 user_id
```

#### 验收标准
- [ ] 用户可注册/登录
- [ ] 每个用户有独立的对话历史和记忆
- [ ] 未登录用户无法访问 WebSocket

---

## 第三部分：低优先级（提升产品完整度）

### 11. 情绪识别（Emotion Detection）

#### 目标
根据用户语音语调判断情绪（开心/生气/疲惫/焦虑），调整回复风格。

#### 技术方案
- 前端：使用音频特征分析（音高/语速/音量）或集成 emotion detection 模型
- 后端：将情绪标签注入 system prompt

#### 涉及文件
- `frontend/src/composables/useEmotionDetection.js`（新建）

#### 实现步骤

```javascript
// 简单实现：基于音量+语速的情绪推断
export function analyzeEmotion(audioData, sampleRate) {
  const volume = audioData.reduce((a, b) => a + Math.abs(b), 0) / audioData.length
  const zeroCrossings = audioData.reduce((count, val, i) => {
    return (i > 0 && val * audioData[i-1] < 0) ? count + 1 : count
  }, 0)
  const pitch = zeroCrossings * sampleRate / (2 * audioData.length)

  if (volume > 0.3 && pitch > 300) return 'excited'
  if (volume > 0.25 && pitch > 250) return 'angry'
  if (volume < 0.05) return 'tired'
  if (pitch > 200 && pitch < 280 && volume > 0.1) return 'happy'
  return 'neutral'
}
```

将情绪标签随音频一起发送到后端，后端在 system prompt 中加入：
```
用户当前情绪：{emotion}。请据此调整语气和内容。
```

---

### 12. 语音合成情感控制

#### 目标
TTS 能根据内容情感调整语气（开心/难过/严肃/温柔）。

#### 技术方案
- 使用支持情感控制的 TTS API（如阿里云的语音合成、微软 Azure TTS 的 SpeakingStyles）
- 在调用 TTS 前，先用 LLM 分析回复文本的情感标签

#### 涉及文件
- `backend/app/core/ai_voice.py`（修改：增加情感参数）

#### 实现步骤

```python
async def synthesize_with_emotion(self, text: str, emotion: str = "neutral"):
    # emotion: neutral, happy, sad, serious, gentle, excited
    style_map = {
        "happy": "cheerful",
        "sad": "sad",
        "serious": "serious",
        "gentle": "gentle",
        "excited": "excited",
    }
    style = style_map.get(emotion, "neutral")

    # 如果 Provider 支持 style 参数
    payload = {
        "model": model,
        "input": text,
        "voice": voice_id,
        "style": style,  # Azure / 阿里云等支持的参数
    }
    # ...
```

---

### 13. 录音保存与回放

#### 目标
用户可下载或回放自己的录音和 AI 的 TTS 回复。

#### 技术方案
- 后端将录音文件（用户音频 + AI TTS 音频）保存到 `data/recordings/{conversation_id}/`
- API 提供列表和下载

#### 涉及文件
- `backend/app/api/endpoints.py`（新增 API）

---

### 14. PWA / 移动端适配

#### 目标
可安装为桌面/手机 PWA 应用，支持离线基本功能。

#### 技术方案
- 添加 `manifest.json` 和 Service Worker
- 响应式布局已在 `VoiceAssistant.vue` 中有基础，需进一步完善移动端交互

#### 涉及文件
- `frontend/public/manifest.json`（新建）
- `frontend/src/sw.js`（新建）

---

### 15. 性能监控面板

#### 目标
可视化展示 ASR/TTS/LLM 延迟、错误率、缓存命中率。

#### 技术方案
- 后端收集指标到内存或 SQLite
- 前端新增 `/monitor` 路由，展示实时图表

#### 依赖项
```bash
npm install chart.js
```

---

## 附录：实施顺序建议

### 第一阶段（核心交互，1-2 周）
1. 前端 VAD + 自动断句
2. 流式 LLM 响应
3. 流式 TTS 播放

### 第二阶段（自然交互，1-2 周）
4. 唤醒词检测
5. 语音打断

### 第三阶段（智能增强，2-3 周）
6. 长期记忆系统
7. 知识库 RAG
8. 闹钟/提醒

### 第四阶段（生态对接，2-3 周）
9. 多用户认证
10. 真实 IoT 集成

### 第五阶段（ polish，1-2 周）
11. 情绪识别
12. 录音保存
13. PWA
14. 监控面板

---

## 附录：关键接口速查

### WebSocket 消息类型（现有 + 新增）

| 方向 | type | 说明 |
|------|------|------|
| C→S | `audio` | 音频数据（base64） |
| C→S | `text` | 文本消息 |
| C→S | `ping` | 心跳 |
| S→C | `connected` | 连接确认 |
| S→C | `audio_result` | ASR 结果 + AI 回复 |
| S→C | `text_response` | 纯文本回复 |
| **S→C** | **`stream_delta`** | **流式文本片段（新增）** |
| **S→C** | **`stream_end`** | **流式结束标记（新增）** |
| **S→C** | **`reminder`** | **定时提醒触发（新增）** |
| S→C | `error` | 错误 |
| S→C | `pong` | 心跳响应 |

### 二进制帧类型

| 类型 | 值 | 说明 |
|------|-----|------|
| BINARY_TYPE_AUDIO | 0x01 | TTS 音频数据块 |
| BINARY_TYPE_END | 0x02 | TTS 流结束 |

---

> **本文档为 AI 可直接实施的详细技术方案。每项功能独立成章，可按需选取实施。**
