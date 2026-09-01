"""
pytest 共享 fixture 和配置

提供：
  - Mock ASRService / NLUService / TTSService / DialogManager
  - 模拟 WAV 音频数据（16000Hz, 单声道, 16-bit PCM）
  - 测试文本样本
  - 测试配置覆盖
"""

import os
import sys
import struct
import io
import wave
from typing import AsyncGenerator, Dict, Optional, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import numpy as np

# 确保 backend 目录在 sys.path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ============================================================
# 模拟音频数据生成
# ============================================================

@pytest.fixture(scope="session")
def sample_audio_wav() -> bytes:
    """
    生成模拟 WAV 音频数据（16000Hz, 单声道, 16-bit PCM, 约 1 秒）
    包含一个 440Hz 正弦波，模拟人声
    """
    sample_rate = 16000
    duration_sec = 1.0
    num_samples = int(sample_rate * duration_sec)
    frequency = 440.0  # A4 音高

    # 生成正弦波
    t = np.linspace(0, duration_sec, num_samples, endpoint=False)
    waveform = np.sin(2 * np.pi * frequency * t) * 0.5

    # 转为 int16 PCM
    pcm_int16 = (waveform * 32767).astype(np.int16)

    # 写入 WAV 内存缓冲区
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_int16.tobytes())

    return buf.getvalue()


@pytest.fixture(scope="session")
def sample_audio_raw() -> bytes:
    """
    生成模拟原始 PCM 音频数据（16000Hz, 单声道, 16-bit, 约 0.5 秒）
    包含一个 880Hz 正弦波
    """
    sample_rate = 16000
    duration_sec = 0.5
    num_samples = int(sample_rate * duration_sec)
    frequency = 880.0

    t = np.linspace(0, duration_sec, num_samples, endpoint=False)
    waveform = np.sin(2 * np.pi * frequency * t) * 0.3
    pcm_int16 = (waveform * 32767).astype(np.int16)

    return pcm_int16.tobytes()


@pytest.fixture(scope="session")
def sample_silence_wav() -> bytes:
    """
    生成静音 WAV 音频数据（16000Hz, 单声道, 16-bit PCM, 约 0.5 秒）
    用于测试静音检测
    """
    sample_rate = 16000
    duration_sec = 0.5
    num_samples = int(sample_rate * duration_sec)
    pcm_int16 = np.zeros(num_samples, dtype=np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_int16.tobytes())

    return buf.getvalue()


# ============================================================
# 测试文本样本
# ============================================================

@pytest.fixture(scope="session")
def test_text_samples() -> Dict[str, str]:
    """各类意图的测试文本"""
    return {
        "weather_query": "北京明天天气怎么样",
        "weather_query_2": "今天多少度",
        "weather_query_3": "上海会下雨吗",
        "device_control": "打开客厅的灯",
        "device_control_2": "把空调调到26度",
        "device_control_3": "关闭电视",
        "schedule": "提醒我明天早上8点开会",
        "schedule_2": "今天有什么安排",
        "schedule_3": "设置一个提醒",
        "music_play": "播放周杰伦的歌",
        "music_play_2": "来一首流行音乐",
        "music_play_3": "下一首",
        "general_chat": "你好",
        "general_chat_2": "你是谁",
        "general_chat_3": "谢谢",
        "empty": "",
        "ambiguous": "这个东西怎么用",
    }


# ============================================================
# Mock 服务
# ============================================================

@pytest.fixture
def mock_asr_service():
    """
    创建 Mock ASRService

    模拟的接口:
      - initialize() -> self
      - recognize_file(path, language, use_vad, use_cache) -> ASRResult
      - recognize_stream(session_id, audio_chunk, language) -> ASRResult | None
      - transcribe(audio_bytes, language) -> ASRResult
      - reset_stream(session_id) -> None
    """
    from app.core.asr import ASRResult

    mock = AsyncMock()

    # 默认返回值：模拟识别出"北京明天天气怎么样"
    mock.recognize_file.return_value = ASRResult(
        text="北京明天天气怎么样",
        confidence=0.92,
        language="zh",
        segments=[{"start": 0.0, "end": 1.5, "text": "北京明天天气怎么样", "confidence": 0.92}],
        duration=1.5,
    )

    # 流式识别：首次调用返回 None（还在累积），第二次调用返回结果
    mock.recognize_stream = AsyncMock()
    mock_stream_results = {
        "session_1": [
            None,  # 第一次调用，仍在累积
            ASRResult(text="北京明天天气怎么样", confidence=0.92, language="zh", duration=1.5),
        ]
    }
    mock_call_counts = {"session_1": 0}

    async def _recognize_stream(session_id: str, audio_chunk: bytes, language: str = "zh"):
        if session_id not in mock_call_counts:
            mock_call_counts[session_id] = 0
        idx = mock_call_counts[session_id]
        mock_call_counts[session_id] += 1
        results = mock_stream_results.get(session_id, [None])
        if idx < len(results):
            return results[idx]
        return None

    mock.recognize_stream.side_effect = _recognize_stream

    # transcribe
    mock.transcribe = AsyncMock(return_value=ASRResult(
        text="北京明天天气怎么样", confidence=0.92, language="zh", duration=1.5,
    ))

    # reset_stream
    mock.reset_stream = AsyncMock()

    # initialize
    mock.initialize = AsyncMock(return_value=mock)

    return mock


@pytest.fixture
def mock_nlu_service():
    """
    创建 Mock NLUService

    模拟的接口:
      - parse(text) -> Intent
    """
    from app.core.nlu import Intent

    mock = AsyncMock()

    def _parse_side_effect(text: str) -> Intent:
        text = text.strip()
        if not text:
            return Intent(name="general_chat", confidence=0.0, entities={})
        if "天气" in text or "温度" in text or "下雨" in text:
            return Intent(name="weather_query", confidence=0.85, entities={
                "city": "北京" if "北京" in text else "",
                "date": "明天" if "明天" in text else "今天",
                "raw_text": text,
            })
        if "打开" in text or "关闭" in text or "灯" in text or "空调" in text:
            return Intent(name="device_control", confidence=0.85, entities={
                "device": "灯" if "灯" in text else "空调",
                "action": "打开" if "打开" in text else "关闭",
                "raw_text": text,
            })
        if "提醒" in text or "日程" in text or "安排" in text:
            return Intent(name="schedule", confidence=0.75, entities={
                "event_name": "开会",
                "date": "明天",
                "time": "08:00",
                "raw_text": text,
            })
        if "播放" in text or "歌" in text or "音乐" in text:
            return Intent(name="music_play", confidence=0.80, entities={
                "artist": "周杰伦" if "周杰伦" in text else "",
                "genre": "流行" if "流行" in text else "",
                "raw_text": text,
            })
        return Intent(name="general_chat", confidence=0.50, entities={"raw_text": text})

    mock.parse.side_effect = _parse_side_effect
    return mock


@pytest.fixture
def mock_ai_voice_service():
    """
    创建 Mock AIVoiceService（AI 语音大模型 TTS）

    模拟的接口:
      - synthesize(text, model, voice, provider_name) -> Optional[bytes]
      - synthesize_stream(text, ...) -> AsyncGenerator[bytes, None]
      - is_configured (property) -> bool
    """
    mock = AsyncMock()

    # synthesize — 返回模拟音频数据
    mock.synthesize = AsyncMock(return_value=b"\xff\xf3\x44\x00" * 1000)

    # synthesize_stream — 模拟流式合成（需用 async def 以支持 async for）
    mock_async_iter = AsyncMock()
    mock_async_iter.__aiter__.return_value = mock_async_iter
    mock_async_iter.__anext__.side_effect = [
        b"\xff\xf3\x44\x00" * 256,
        b"\xff\xf3\x44\x00" * 256,
        b"\xff\xf3\x44\x00" * 256,
        StopAsyncIteration(),
    ]

    mock._synthesize_stream_call = MagicMock()

    def _synthesize_stream(text, **kwargs):  # 必须是非 async 函数，async for 需要直接返回 async iterable
        mock._synthesize_stream_call(text=text, **kwargs)
        return mock_async_iter

    mock.synthesize_stream = _synthesize_stream
    mock.is_configured = True

    return mock


@pytest.fixture
def mock_dialog_manager():
    """
    创建 Mock DialogManager

    模拟的接口:
      - process_message(text, conversation_id) -> dict
      - create_conversation(session_id) -> str
      - get_conversation(conversation_id) -> ConversationContext | None
      - cleanup_expired() -> int
    """
    mock = AsyncMock()

    def _process_message_side_effect(text: str, conversation_id: str = None) -> Dict[str, Any]:
        text = text.strip()
        if not text:
            return {
                "conversation_id": conversation_id or "mock_conv",
                "response": "请说点什么吧。",
                "intent": "general_chat",
                "confidence": 0.0,
                "entities": {},
                "turn_count": 0,
                "state": "idle",
            }
        if "天气" in text:
            return {
                "conversation_id": conversation_id or "mock_conv",
                "response": f"当前天气晴朗，温度25°C。",
                "intent": "weather_query",
                "confidence": 0.85,
                "entities": {"city": "北京", "date": "明天"},
                "turn_count": 1,
                "state": "idle",
            }
        if "打开" in text or "灯" in text:
            return {
                "conversation_id": conversation_id or "mock_conv",
                "response": "已为您打开灯光。",
                "intent": "device_control",
                "confidence": 0.90,
                "entities": {"device": "灯", "action": "打开"},
                "turn_count": 1,
                "state": "idle",
            }
        if "你好" in text:
            return {
                "conversation_id": conversation_id or "mock_conv",
                "response": "你好！我是AI语音助手，请问有什么可以帮助您的？",
                "intent": "general_chat",
                "confidence": 0.80,
                "entities": {},
                "turn_count": 1,
                "state": "idle",
            }
        return {
            "conversation_id": conversation_id or "mock_conv",
            "response": f"已收到消息: {text}",
            "intent": "general_chat",
            "confidence": 0.50,
            "entities": {},
            "turn_count": 1,
            "state": "idle",
        }

    mock.process_message.side_effect = _process_message_side_effect
    mock.create_conversation = MagicMock(return_value="mock_conv")
    mock.get_conversation = MagicMock(return_value=None)
    mock.cleanup_expired = MagicMock(return_value=0)

    return mock


# ============================================================
# 测试配置
# ============================================================

@pytest.fixture(autouse=True)
def override_settings():
    """
    自动覆盖 Settings，确保测试使用安全的默认值
    避免测试时误用生产环境的 API Key
    """
    with patch("app.core.config.settings") as mock_settings:
        mock_settings.OPENAI_API_KEY = ""
        mock_settings.OPENAI_MODEL = "gpt-3.5-turbo"
        mock_settings.OPENAI_MAX_TOKENS = 128
        mock_settings.OPENAI_TEMPERATURE = 0.7
        mock_settings.WHISPER_MODEL_SIZE = "base"
        mock_settings.ASR_DEFAULT_LANGUAGE = "zh"
        mock_settings.VAD_SENSITIVITY = 2
        mock_settings.ASR_MAX_CONCURRENCY = 2
        yield


# ============================================================
# pytest-asyncio 配置
# ============================================================

def pytest_configure(config):
    """pytest 配置钩子：注册 asyncio 模式"""
    config.option.asyncio_mode = "auto"
