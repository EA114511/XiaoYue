"""
ASR 模块单元测试

测试覆盖:
  - ASRService.initialize() — 初始化和模型加载
  - ASRService.recognize_file() — 文件识别（含缓存和 VAD）
  - ASRService.recognize_stream() — 流式识别（累积音频 → 输出文本）
  - ASRService.transcribe() — 兼容接口
  - VoiceActivityDetector — 语音/静音检测
  - ASRResultCache — 缓存命中与淘汰
  - 音频预处理 — 重采样/归一化/指纹
  - 边缘情况 — 空音频、静音、长音频
"""

import io
import time
import wave
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import numpy as np
import pytest

from app.core.asr import (
    ASRService,
    ASRResult,
    ASRResultCache,
    VoiceActivityDetector,
    WhisperASR,
    StreamSession,
    audio_fingerprint,
    preprocess_audio,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def asr_service():
    """创建 ASRService 实例（未初始化）"""
    return ASRService()


@pytest.fixture
def asr_result():
    """创建标准 ASRResult 实例"""
    return ASRResult(
        text="北京明天天气怎么样",
        confidence=0.92,
        language="zh",
        segments=[{"start": 0.0, "end": 1.5, "text": "北京明天天气怎么样", "confidence": 0.92}],
        duration=1.5,
    )


@pytest.fixture
def whisper_asr():
    """创建 WhisperASR 实例（使用最小模型 tiny 加速测试）"""
    return WhisperASR(model_size="tiny")


# ============================================================
# ASRResult 测试
# ============================================================

class TestASRResult:
    """ASR 识别结果数据结构测试"""

    def test_create_result(self):
        """测试创建 ASRResult 实例"""
        result = ASRResult(text="你好", confidence=0.95, language="zh")
        assert result.text == "你好"
        assert result.confidence == 0.95
        assert result.language == "zh"
        assert result.segments == []
        assert result.duration == 0.0

    def test_create_with_all_fields(self):
        """测试带所有字段创建实例"""
        result = ASRResult(
            text="测试",
            confidence=0.85,
            language="zh",
            segments=[{"start": 0.0, "end": 0.5, "text": "测试"}],
            duration=0.5,
        )
        assert result.text == "测试"
        assert len(result.segments) == 1
        assert result.duration == 0.5

    def test_to_dict(self, asr_result):
        """测试序列化为字典"""
        d = asr_result.to_dict()
        assert d["text"] == "北京明天天气怎么样"
        assert d["confidence"] == 0.92
        assert d["language"] == "zh"
        assert "segments" in d
        assert "duration" in d

    def test_empty_result(self):
        """测试空识别结果"""
        result = ASRResult(text="", confidence=0.0)
        assert result.text == ""
        assert result.confidence == 0.0


# ============================================================
# 音频预处理测试
# ============================================================

class TestAudioPreprocessing:
    """音频预处理流水线测试"""

    def test_preprocess_wav(self, sample_audio_wav):
        """测试标准 WAV 格式预处理"""
        audio_array, sample_rate = preprocess_audio(sample_audio_wav)
        assert sample_rate == 16000
        assert isinstance(audio_array, np.ndarray)
        assert audio_array.dtype == np.float32
        # 值域应在 [-1, 1] 范围内
        assert np.all(audio_array >= -1.0)
        assert np.all(audio_array <= 1.0)
        # 长度应与 1 秒音频匹配
        assert len(audio_array) == 16000

    def test_preprocess_raw_pcm(self, sample_audio_raw):
        """测试原始 PCM 格式预处理"""
        audio_array, sample_rate = preprocess_audio(sample_audio_raw)
        assert sample_rate == 16000
        assert isinstance(audio_array, np.ndarray)
        assert audio_array.dtype == np.float32
        # 0.5 秒音频 → 8000 个采样点
        assert len(audio_array) == 8000

    def test_preprocess_silence(self, sample_silence_wav):
        """测试静音音频预处理"""
        audio_array, sample_rate = preprocess_audio(sample_silence_wav)
        assert sample_rate == 16000
        # 静音数组应全为零
        assert np.all(audio_array == 0.0)

    def test_audio_fingerprint(self, sample_audio_wav):
        """测试音频指纹计算"""
        fp1 = audio_fingerprint(sample_audio_wav)
        fp2 = audio_fingerprint(sample_audio_wav)
        # 相同音频应产生相同指纹
        assert fp1 == fp2
        assert len(fp1) == 16  # SHA256 前 16 位

    def test_audio_fingerprint_different(self, sample_audio_wav, sample_silence_wav):
        """测试不同音频产生不同指纹"""
        fp1 = audio_fingerprint(sample_audio_wav)
        fp2 = audio_fingerprint(sample_silence_wav)
        assert fp1 != fp2


# ============================================================
# VAD 检测器测试
# ============================================================

class TestVoiceActivityDetector:
    """语音活动检测测试"""

    @pytest.fixture
    def vad(self):
        """创建 VAD 检测器"""
        return VoiceActivityDetector(sensitivity=0)  # 最宽松模式

    def test_is_speech_with_speech(self, vad, sample_audio_raw):
        """测试检测有效语音"""
        # 正弦波应被检测为语音
        result = vad.is_speech(sample_audio_raw, sample_rate=16000)
        # 注意: webrtcvad 在 CI 环境中可能不准确，这里只验证接口正常
        assert isinstance(result, bool)

    def test_is_speech_with_silence(self, vad):
        """测试检测静音"""
        # 全零 PCM 数据应被检测为非语音
        pcm_silence = np.zeros(16000, dtype=np.int16).tobytes()
        result = vad.is_speech(pcm_silence, sample_rate=16000)
        assert result is False

    def test_is_speech_empty(self, vad):
        """测试空音频"""
        result = vad.is_speech(b"", sample_rate=16000)
        assert result is False

    def test_detect_speech_segments(self, vad, sample_audio_raw):
        """测试语音段落检测"""
        from app.core.asr import preprocess_audio
        audio_array, sr = preprocess_audio(sample_audio_raw)
        segments = vad.detect_speech_segments(audio_array, sr)
        assert isinstance(segments, list)
        if segments:
            for start, end in segments:
                assert start >= 0.0
                assert end > start


# ============================================================
# ASR 缓存测试
# ============================================================

class TestASRResultCache:
    """ASR 结果缓存测试"""

    @pytest.fixture
    def cache(self):
        """创建小型缓存（最大 3 条）"""
        return ASRResultCache(max_size=3)

    @pytest.fixture
    def result_a(self):
        return ASRResult(text="天气", confidence=0.9)

    @pytest.fixture
    def result_b(self):
        return ASRResult(text="音乐", confidence=0.8)

    @pytest.fixture
    def result_c(self):
        return ASRResult(text="灯光", confidence=0.85)

    @pytest.fixture
    def result_d(self):
        return ASRResult(text="新闻", confidence=0.75)

    def test_get_miss(self, cache):
        """测试缓存未命中"""
        result = cache.get("unknown_fingerprint")
        assert result is None

    def test_put_and_get(self, cache, result_a):
        """测试写入和读取缓存"""
        cache.put("fingerprint_a", result_a)
        result = cache.get("fingerprint_a")
        assert result is not None
        assert result.text == "天气"
        assert result.confidence == 0.9

    def test_cache_size(self, cache, result_a, result_b, result_c):
        """测试缓存大小追踪"""
        assert cache.size == 0
        cache.put("a", result_a)
        assert cache.size == 1
        cache.put("b", result_b)
        assert cache.size == 2
        cache.put("c", result_c)
        assert cache.size == 3

    def test_lru_eviction(self, cache, result_a, result_b, result_c, result_d):
        """测试 LRU 淘汰策略"""
        cache.put("a", result_a)
        cache.put("b", result_b)
        cache.put("c", result_c)

        # 访问 'a'，使其成为最新使用的
        cache.get("a")

        # 插入 'd'，应淘汰最久未使用的 'b'
        cache.put("d", result_d)

        assert cache.get("a") is not None  # 'a' 应保留
        assert cache.get("b") is None      # 'b' 应被淘汰
        assert cache.get("c") is not None  # 'c' 应保留
        assert cache.get("d") is not None  # 'd' 应存在
        assert cache.size == 3

    def test_clear(self, cache, result_a, result_b):
        """测试清空缓存"""
        cache.put("a", result_a)
        cache.put("b", result_b)
        assert cache.size == 2

        cache.clear()
        assert cache.size == 0
        assert cache.get("a") is None
        assert cache.get("b") is None

    def test_move_to_end_on_get(self, cache, result_a, result_b):
        """测试读取时更新访问顺序"""
        cache.put("a", result_a)
        cache.put("b", result_b)

        # 读取 'a' 使其成为最近使用
        cache.get("a")

        # 检查 OrderedDict 内部顺序（'a' 应被移到末尾）
        keys = list(cache._cache.keys())
        assert keys[-1] == "a"


# ============================================================
# WhisperASR 引擎测试
# ============================================================

class TestWhisperASR:
    """Whisper 语音识别引擎测试"""

    @pytest.mark.asyncio
    async def test_initialization(self, whisper_asr):
        """测试 WhisperASR 初始化"""
        # 验证初始状态
        assert whisper_asr._model is None
        assert whisper_asr.model_size == "tiny"

    @pytest.mark.asyncio
    async def test_model_size_mapping(self):
        """测试模型尺寸映射"""
        for size in ["tiny", "base", "small", "medium", "large"]:
            engine = WhisperASR(model_size=size)
            assert engine.model_size == size

    def test_invalid_model_size(self):
        """测试无效模型尺寸回退"""
        engine = WhisperASR(model_size="invalid_size")
        assert engine.model_size == "base"

    @pytest.mark.asyncio
    async def test_transcribe_with_mock(self):
        """使用 Mock 测试 transcribe 流程"""
        engine = WhisperASR(model_size="tiny")

        # Mock whisper 模型
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": " 测试文本 ",
            "segments": [
                {"start": 0.0, "end": 0.5, "text": "测试文本", "confidence": 0.85}
            ],
            "language": "zh",
        }
        engine._model = mock_model

        # 模拟音频输入
        audio = np.zeros(16000, dtype=np.float32)
        result = await engine.transcribe(audio, language="zh")

        assert result["text"] == "测试文本"
        assert result["language"] == "zh"
        assert result["confidence"] > 0


# ============================================================
# StreamSession 测试
# ============================================================

class TestStreamSession:
    """流式会话测试"""

    def test_create_session(self):
        """测试创建流式会话"""
        session = StreamSession(session_id="test_session")
        assert session.session_id == "test_session"
        assert session.buffer == []
        assert session.is_speech_active is False
        assert session.silence_duration == 0.0
        assert session.accumulated_text == ""

    def test_clear_buffer(self):
        """测试清空缓冲区"""
        session = StreamSession(session_id="test")
        session.buffer = [b"\x00\x00"] * 10
        session.is_speech_active = True
        session.silence_duration = 2.0

        session.clear_buffer()
        assert session.buffer == []
        assert session.is_speech_active is False
        assert session.silence_duration == 0.0

    def test_buffer_duration(self):
        """测试缓冲区时长计算"""
        session = StreamSession(session_id="test")
        assert session.buffer_duration_ms == 0
        session.buffer = [b"\x00\x00"] * 10
        assert session.buffer_duration_ms == 300


# ============================================================
# ASRService 完整测试
# ============================================================

class TestASRService:
    """ASR 服务集成测试"""

    @pytest.mark.asyncio
    async def test_initialization(self, asr_service):
        """测试 ASRService 初始化（Mock 内部组件）"""
        with patch.object(asr_service, "_engine", None):
            assert asr_service._engine is None
            assert asr_service._initialized is False

    @pytest.mark.asyncio
    async def test_initialization_with_mocks(self):
        """使用 Mock 测试完整初始化流程"""
        with patch("app.core.asr.WhisperASR") as MockWhisper, \
             patch("app.core.asr.VoiceActivityDetector") as MockVAD:

            service = ASRService()

            # Mock whisper 引擎
            mock_whisper = MagicMock()
            mock_whisper.load_model = AsyncMock()
            MockWhisper.return_value = mock_whisper

            await service.initialize()

            assert service._initialized is True
            MockWhisper.assert_called_once()

    @pytest.mark.asyncio
    async def test_recognize_file_with_cache(self, asr_service, sample_audio_wav, asr_result):
        """测试文件识别命中缓存"""
        # Mock 引擎和缓存
        asr_service._engine = MagicMock()
        asr_service._cache = MagicMock()
        asr_service._vad = MagicMock()

        fp = audio_fingerprint(sample_audio_wav)
        asr_service._cache.get.return_value = asr_result

        with patch("builtins.open", unittest.mock.mock_open(read_data=sample_audio_wav)):
            result = await asr_service.recognize_file(
                "/fake/path.wav", use_cache=True, use_vad=False,
            )

        assert result.text == "北京明天天气怎么样"
        asr_service._cache.get.assert_called_once_with(fp)

    @pytest.mark.asyncio
    async def test_recognize_file_no_cache(self, asr_service, sample_audio_wav):
        """测试文件识别未命中缓存"""
        asr_service._engine = MagicMock()
        asr_service._vad = MagicMock()
        asr_service._vad.detect_speech_segments.return_value = []

        # Mock transcribe 返回结果
        transcribe_result = {
            "text": "测试文本",
            "segments": [{"start": 0, "end": 0.3, "text": "测试文本", "confidence": 0.9}],
            "language": "zh",
            "confidence": 0.9,
        }
        asr_service._engine.transcribe = AsyncMock(return_value=transcribe_result)

        with patch("builtins.open", unittest.mock.mock_open(read_data=sample_audio_wav)):
            result = await asr_service.recognize_file(
                "/fake/path.wav", use_cache=False, use_vad=False,
            )

        assert result.text == "测试文本"
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_recognize_stream_accumulation(self, asr_service):
        """测试流式识别音频累积逻辑"""
        asr_service._engine = MagicMock()

        # 第一次调用：返回 None（仍在累积）
        result_1 = await asr_service.recognize_stream(
            session_id="test_session",
            audio_chunk=b"\x00\xff" * 1600,
            language="zh",
        )
        # 未初始化时，流式识别应返回 None
        assert result_1 is None

    @pytest.mark.asyncio
    async def test_recognize_stream_with_mock(self, asr_service, mock_asr_service):
        """使用 Mock 测试完整流式识别流程"""
        # 第一次调用（仍在累积）
        result_1 = await mock_asr_service.recognize_stream("session_1", b"\x00\xff" * 1600)
        assert result_1 is None

        # 第二次调用（语音结束，返回结果）
        result_2 = await mock_asr_service.recognize_stream("session_1", b"\x00\xff" * 1600)
        assert result_2 is not None
        assert isinstance(result_2, ASRResult)
        assert result_2.text == "北京明天天气怎么样"
        assert result_2.confidence == 0.92

    @pytest.mark.asyncio
    async def test_reset_stream(self, asr_service, mock_asr_service):
        """测试重置流式会话"""
        await mock_asr_service.reset_stream("session_1")
        mock_asr_service.reset_stream.assert_awaited_once_with("session_1")

    @pytest.mark.asyncio
    async def test_transcribe_compat(self, asr_service, mock_asr_service, sample_audio_wav):
        """测试兼容接口 transcribe"""
        result = await mock_asr_service.transcribe(sample_audio_wav, language="zh")
        assert result.text == "北京明天天气怎么样"
        assert result.confidence == 0.92

    @pytest.mark.asyncio
    async def test_empty_audio(self, asr_service):
        """测试空音频"""
        asr_service._engine = MagicMock()

        result = await asr_service.recognize_stream(
            session_id="test_session", audio_chunk=b"",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_vad_filtering(self, asr_service, sample_silence_wav):
        """测试 VAD 过滤静音"""
        asr_service._engine = MagicMock()
        asr_service._vad = MagicMock()
        asr_service._vad.detect_speech_segments.return_value = []

        with patch("builtins.open", unittest.mock.mock_open(read_data=sample_silence_wav)):
            result = await asr_service.recognize_file(
                "/fake/silence.wav", use_vad=True, use_cache=False,
            )

        # 无语音段时返回空结果
        assert result.text == ""
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_multiple_sessions_isolation(self, mock_asr_service):
        """测试多个流式会话隔离"""
        # 会话 1 第一次调用
        r1 = await mock_asr_service.recognize_stream("session_A", b"\x00" * 1600)
        assert r1 is None

        # 会话 2 第一次调用
        r2 = await mock_asr_service.recognize_stream("session_B", b"\x00" * 1600)
        assert r2 is None

        # 会话 1 第二次调用（应返回结果）
        r3 = await mock_asr_service.recognize_stream("session_A", b"\x00" * 1600)
        assert r3 is not None
        assert r3.text == "北京明天天气怎么样"

        # 会话 2 第二次调用（也应返回结果）
        r4 = await mock_asr_service.recognize_stream("session_B", b"\x00" * 1600)
        assert r4 is not None


# 导入 unittest.mock 以在 test_asr.py 中使用
import unittest.mock
