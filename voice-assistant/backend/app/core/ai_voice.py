"""
AI 语音大模型合成模块

基于 OpenAI 兼容的 TTS API（/v1/audio/speech），提供高质量 AI 语音合成。
替代传统的 edge-tts，支持更自然的语音输出。

===== 支持的 API 格式 =====

OpenAI TTS API:
  POST {api_base}/audio/speech
  {
    "model": "tts-1",
    "input": "要合成的文本",
    "voice": "alloy",
    "response_format": "mp3",
    "speed": 1.0
  }
  返回: 音频二进制数据 (MP3)

支持的音色 (OpenAI):
  - alloy    (中性, 多用途)
  - echo     (男声, 深沉)
  - fable    (英式, 叙事风格)
  - nova     (女声, 温暖)
  - onyx     (男声, 自信)
  - shimmer  (女声, 清澈)

===== 使用方式 =====

  from app.core.ai_voice import AIVoiceService

  voice_svc = AIVoiceService()
  audio_bytes = await voice_svc.synthesize("你好，今天天气怎么样")
"""

import asyncio
import base64
import hashlib
import json
import logging
from collections import OrderedDict
from typing import AsyncGenerator, Optional, Dict, Any

import httpx

from app.core.config import settings
from app.core.voice_providers import voice_provider_registry

logger = logging.getLogger("voice-assistant.ai_voice")

# ---- 并发控制 ----
_voice_semaphore = asyncio.Semaphore(3)

# ---- 缓存 ----
class VoiceCache:
    """AI 语音合成缓存（基于文本哈希）"""

    def __init__(self, max_size: int = 128):
        self._max_size = max_size
        self._cache: OrderedDict = OrderedDict()

    def _make_key(self, text: str, model: str, voice: str) -> str:
        raw = f"{text}|{model}|{voice}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def get(self, text: str, model: str, voice: str) -> Optional[bytes]:
        key = self._make_key(text, model, voice)
        entry = self._cache.get(key)
        if entry is None:
            return None
        self._cache.move_to_end(key)
        logger.debug(f"[VoiceCache] 缓存命中: \"{text[:30]}...\"")
        return entry

    def put(self, text: str, model: str, voice: str, audio: bytes):
        key = self._make_key(text, model, voice)
        self._cache[key] = audio
        self._cache.move_to_end(key)
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def clear(self):
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)


# 全局缓存实例
_voice_cache = VoiceCache(max_size=getattr(settings, "TTS_CACHE_SIZE", 128))


class AIVoiceService:
    """
    AI 语音大模型合成服务

    调用 OpenAI 兼容的 TTS API 进行语音合成，支持完整合成和流式合成。
    使用 VoiceProviderRegistry 获取配置的 Provider。

    当 Provider 未启用或配置不完整时，返回 None（调用方应回退到仅文本回复）。
    """

    def __init__(self):
        self._http_client: Optional[httpx.AsyncClient] = None
        self._cache = _voice_cache
        logger.info("[AIVoice] AI 语音大模型服务已初始化")

    # ---------------------------------------------------------------
    # 生命周期
    # ---------------------------------------------------------------

    async def initialize(self):
        """初始化 HTTP 客户端"""
        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_connections=5, max_keepalive_connections=5),
        )
        logger.info("[AIVoice] HTTP 客户端已创建")

    async def cleanup(self):
        """清理 HTTP 客户端"""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            logger.info("[AIVoice] HTTP 客户端已关闭")
        self._cache.clear()
        logger.info("[AIVoice] 缓存已清空")

    # ---------------------------------------------------------------
    # 核心合成
    # ---------------------------------------------------------------

    async def synthesize(
        self,
        text: str,
        model: Optional[str] = None,
        voice: Optional[str] = None,
        provider_name: Optional[str] = None,
    ) -> Optional[bytes]:
        """
        完整合成：将文本合成为音频数据

        支持两种 API 格式：
          - OpenAI 兼容（encode_format != "base64"）：直接返回原始音频二进制
          - 智谱 GLM-TTS（encode_format == "base64"）：解析 SSE base64 PCM 并解码

        参数:
            text:          待合成的文本
            model:         语音模型名称，None 则使用 Provider 配置
            voice:         音色 ID，None 则使用 Provider 配置
            provider_name: Provider 名称，None 则使用已启用的 Provider

        返回:
            PCM 或 MP3 格式的音频字节数据，失败或未配置时返回 None
        """
        if not text or not text.strip():
            return None

        text = text.strip()

        # 获取语音 Provider
        provider = self._get_provider(provider_name)
        if not provider or not provider.enabled:
            logger.debug("[AIVoice] 未启用语音 Provider，跳过 AI 语音合成")
            return None

        # 参数覆盖
        model = model or provider.model or "glm-tts"
        voice_id = voice or provider.voice or "female"
        response_format = provider.response_format or "pcm"
        encode_format = provider.encode_format or "base64"
        speed = provider.speed or 1.0
        volume = getattr(provider, 'volume', 1.0)
        voice_type = getattr(provider, 'voice_type', 'preset')
        clone_settings = getattr(provider, 'clone_settings', None) or {}

        # 声音复刻模式：使用 clone_voice_id 替代预设音色
        if voice_type == "clone" and clone_settings.get("clone_voice_id"):
            voice_id = clone_settings["clone_voice_id"]
            logger.debug(f"[AIVoice] 使用复刻音色: {voice_id} (voice_name={clone_settings.get('voice_name', '')})")

        # 检查缓存
        cached = self._cache.get(text, model, voice_id)
        if cached is not None:
            return cached

        # 构建 API 请求
        api_base = provider.api_base.rstrip("/")
        url = f"{api_base}/audio/speech"
        headers = {
            "Content-Type": "application/json",
        }
        if provider.api_key:
            headers["Authorization"] = f"Bearer {provider.api_key}"

        payload = {
            "model": model,
            "input": text,
            "voice": voice_id,
            "response_format": response_format,
            "speed": speed,
        }

        # 智谱 GLM-TTS 特有参数
        if encode_format == "base64":
            payload["stream"] = True
            payload["encode_format"] = "base64"
            if volume != 1.0:
                payload["volume"] = volume
        else:
            payload["stream"] = False

        client = self._http_client
        if not client:
            logger.warning("[AIVoice] HTTP 客户端未初始化")
            return None

        try:
            async with _voice_semaphore:
                logger.debug(f"[AIVoice] 请求: {url}, model={model}, voice={voice_id}, "
                             f"encode_format={encode_format}")
                resp = await client.post(url, headers=headers, json=payload)

                if resp.status_code != 200:
                    logger.warning(
                        f"[AIVoice] API 请求失败: HTTP {resp.status_code}, "
                        f"body={resp.text[:200]}"
                    )
                    return None

                # ----- 分支 1: 智谱 SSE + base64 PCM -----
                if encode_format == "base64":
                    audio_chunks: list[bytes] = []
                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        json_str = line[5:].strip()
                        if json_str == "[DONE]":
                            break
                        try:
                            chunk_data = json.loads(json_str)
                            choices = chunk_data.get("choices", [])
                            for choice in choices:
                                if choice.get("finish_reason") == "stop":
                                    break
                                content = choice.get("delta", {}).get("content", "")
                                if content:
                                    audio_chunks.append(base64.b64decode(content))
                        except json.JSONDecodeError:
                            continue
                    if audio_chunks:
                        audio_data = b"".join(audio_chunks)
                        # PCM → WAV 包装，浏览器才能解码播放
                        audio_data = self.pcm_to_wav(audio_data)
                        self._cache.put(text, model, voice_id, audio_data)
                        logger.debug(f"[AIVoice] 合成成功: {len(audio_data)} bytes (WAV/PCM/base64)")
                        return audio_data
                    else:
                        logger.warning("[AIVoice] 未从 SSE 流中解析到音频数据")
                        return None

                # ----- 分支 2: OpenAI 兼容 原始音频二进制 -----
                audio_data = resp.content
                if audio_data:
                    self._cache.put(text, model, voice_id, audio_data)
                    logger.debug(f"[AIVoice] 合成成功: {len(audio_data)} bytes")
                    return audio_data
                else:
                    logger.warning("[AIVoice] 返回的音频数据为空")
                    return None

        except httpx.TimeoutException:
            logger.warning(f"[AIVoice] 请求超时: {url}")
            return None
        except httpx.RequestError as e:
            logger.warning(f"[AIVoice] 请求异常: {e}")
            return None
        except Exception as e:
            logger.error(f"[AIVoice] 合成异常: {e}", exc_info=True)
            return None

    async def synthesize_stream(
        self,
        text: str,
        model: Optional[str] = None,
        voice: Optional[str] = None,
        provider_name: Optional[str] = None,
        chunk_size: int = 4096,
    ) -> AsyncGenerator[bytes, None]:
        """
        流式合成：逐块获取音频数据

        支持两种 API 格式：
          - OpenAI 兼容（encode_format != "base64"）：SSE 返回原始音频二进制块
          - 智谱 GLM-TTS（encode_format == "base64"）：SSE JSON 中解析 base64 PCM 并解码

        参数:
            text:          待合成的文本
            model:         语音模型名称
            voice:         音色 ID
            provider_name: Provider 名称
            chunk_size:    分块大小（字节）

        生成:
            音频数据块（PCM 或 MP3 格式）
        """
        if not text or not text.strip():
            return

        text = text.strip()

        provider = self._get_provider(provider_name)
        if not provider or not provider.enabled:
            logger.debug("[AIVoice] 未启用语音 Provider，跳过流式合成")
            return

        model = model or provider.model or "glm-tts"
        voice_id = voice or provider.voice or "female"
        response_format = provider.response_format or "pcm"
        encode_format = provider.encode_format or "base64"
        speed = provider.speed or 1.0
        volume = getattr(provider, 'volume', 1.0)
        voice_type = getattr(provider, 'voice_type', 'preset')
        clone_settings = getattr(provider, 'clone_settings', None) or {}

        # 声音复刻模式：使用 clone_voice_id 替代预设音色
        if voice_type == "clone" and clone_settings.get("clone_voice_id"):
            voice_id = clone_settings["clone_voice_id"]
            logger.debug(f"[AIVoice][流式] 使用复刻音色: {voice_id}")

        api_base = provider.api_base.rstrip("/")
        url = f"{api_base}/audio/speech"
        headers = {
            "Content-Type": "application/json",
        }
        if provider.api_key:
            headers["Authorization"] = f"Bearer {provider.api_key}"

        payload = {
            "model": model,
            "input": text,
            "voice": voice_id,
            "response_format": response_format,
            "speed": speed,
        }

        # 智谱 GLM-TTS 特有参数
        if encode_format == "base64":
            payload["stream"] = True
            payload["encode_format"] = "base64"
            if volume != 1.0:
                payload["volume"] = volume
        else:
            payload["stream"] = False

        client = self._http_client
        if not client:
            return

        try:
            async with _voice_semaphore:
                async with client.stream("POST", url, headers=headers, json=payload) as resp:
                    if resp.status_code != 200:
                        logger.warning(
                            f"[AIVoice] 流式合成失败: HTTP {resp.status_code}, "
                            f"body={(await resp.aread())[:200]}"
                        )
                        return

                    # ----- 分支 1: 智谱 SSE + base64 PCM -----
                    if encode_format == "base64":
                        pcm_buffer = b""
                        async for line in resp.aiter_lines():
                            line = line.strip()
                            if not line or not line.startswith("data:"):
                                continue
                            json_str = line[5:].strip()
                            if json_str == "[DONE]":
                                break
                            try:
                                chunk_data = json.loads(json_str)
                                choices = chunk_data.get("choices", [])
                                for choice in choices:
                                    if choice.get("finish_reason") == "stop":
                                        break
                                    content = choice.get("delta", {}).get("content", "")
                                    if content:
                                        pcm_buffer += base64.b64decode(content)
                            except json.JSONDecodeError:
                                continue
                        # PCM → WAV 包装后一次性 yield
                        if pcm_buffer:
                            yield self.pcm_to_wav(pcm_buffer)

                    # ----- 分支 2: OpenAI 兼容 原始音频二进制块 -----
                    else:
                        full_data = b""
                        async for chunk in resp.aiter_bytes():
                            full_data += chunk
                            if len(full_data) >= chunk_size:
                                yield full_data[:chunk_size]
                                full_data = full_data[chunk_size:]
                        if full_data:
                            yield full_data

        except Exception as e:
            logger.warning(f"[AIVoice] 流式合成异常: {e}")

    # ---------------------------------------------------------------
    # 内部方法
    # ---------------------------------------------------------------

    def _get_provider(self, name: Optional[str] = None) -> Optional[Any]:
        """获取语音 Provider"""
        from app.core.voice_providers import voice_provider_registry
        if name:
            return voice_provider_registry.get(name)
        return voice_provider_registry.get_active() or voice_provider_registry.get_default()

    def get_available_voices(self, provider_name: Optional[str] = None) -> Dict[str, str]:
        """
        获取可用的音色列表

        根据 Provider 类型返回不同的音色选项：
          - 智谱 GLM-TTS: female, male, child, etc.
          - OpenAI 兼容: alloy, echo, fable, nova, onyx, shimmer
        """
        # 如果是智谱 Provider，返回智谱音色
        if provider_name and ("zhipu" in provider_name or "glm" in provider_name):
            return {
                "female": "女声（柔和自然，中文优化）",
                "male": "男声（沉稳清晰，中文优化）",
                "child": "童声（活泼可爱）",
                "female-wellbeing": "女声（温暖关怀）",
                "male-journey": "男声（沉稳叙事）",
                "female-candidate": "女声（正式播报）",
            }
        # 尝试从 provider 配置判断
        provider = self._get_provider(provider_name)
        if provider:
            pname = provider.name.lower()
            if "zhipu" in pname or "glm" in pname:
                return self.get_available_voices(provider_name="zhipu-glm")
        # 默认 OpenAI 标准音色
        return {
            "alloy": "Alloy（中性，多用途）",
            "echo": "Echo（男声，深沉）",
            "fable": "Fable（英式，叙事风格）",
            "nova": "Nova（女声，温暖）",
            "onyx": "Onyx（男声，自信）",
            "shimmer": "Shimmer（女声，清澈）",
        }

    # ---------------------------------------------------------------
    # 工具
    # ---------------------------------------------------------------

    @staticmethod
    def pcm_to_wav(pcm_data: bytes, sample_rate: int = 24000) -> bytes:
        """
        将原始 PCM 数据包装为 WAV 格式（浏览器可直接解码播放）

        PCM 参数: 16-bit, 单声道 (mono), 小端序 (little-endian)

        参数:
            pcm_data:    原始 PCM 字节数据
            sample_rate: 采样率, 智谱 GLM-TTS 默认为 24000 Hz

        返回:
            带 WAV 头部的完整音频数据
        """
        # 计算参数
        channels = 1       # 单声道
        bits_per_sample = 16
        byte_rate = sample_rate * channels * bits_per_sample // 8
        block_align = channels * bits_per_sample // 8
        data_size = len(pcm_data)
        file_size = 36 + data_size  # 4+8+16+8+data_size - 8 (RIFF 头不包含自身)

        # 构建 44 字节 WAV 头
        import struct
        header = struct.pack(
            '<4sI4s4sIHHIIHH4sI',
            b'RIFF',                 # RIFF 标识
            file_size,               # 文件总大小 - 8
            b'WAVE',                 # WAVE 标识
            b'fmt ',                 # fmt chunk 标识
            16,                      # fmt chunk 大小 (PCM = 16)
            1,                       # 音频格式 (1 = PCM)
            channels,                # 声道数
            sample_rate,             # 采样率
            byte_rate,               # 字节率
            block_align,             # 块对齐
            bits_per_sample,         # 位深
            b'data',                 # data chunk 标识
            data_size,               # 数据大小
        )
        return header + pcm_data

    async def prewarm(self):
        """预热：测试连接"""
        logger.info("[AIVoice] 预热中...")
        if not self._http_client:
            await self.initialize()

        provider = self._get_provider()
        if not provider or not provider.enabled:
            logger.info("[AIVoice] 跳过预热（未启用 AI 语音）")
            return False

        result = await self.synthesize("您好", model=provider.model, voice=provider.voice)
        if result:
            logger.info(f"[AIVoice] 预热完成 ({len(result)} bytes)")
            return True
        else:
            logger.warning("[AIVoice] 预热失败")
            return False

    @property
    def is_configured(self) -> bool:
        """检查 AI 语音服务是否已配置并启用"""
        provider = self._get_provider()
        return provider is not None and provider.enabled and bool(provider.api_base)
