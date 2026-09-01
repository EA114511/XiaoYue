"""
语音识别模块 (ASR - Automatic Speech Recognition)
基于 OpenAI Whisper 实现，包含音频预处理、VAD、缓存和流式识别功能

功能概览:
  - 文件识别: recognize_file(audio_path) -> str
  - 流式识别: recognize_stream(session_id, audio_chunk) -> str
  - 音频预处理: 自动重采样至 16000Hz、单声道、归一化
  - 模型选择: tiny / base / small / medium / large
  - VAD: 基于 webrtcvad 的语音活动检测
  - 缓存: 基于音频 SHA256 指纹避免重复识别
"""

import asyncio
import hashlib
import io
import logging
import struct
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import numpy as np

from app.core.config import settings

logger = logging.getLogger("voice-assistant.asr")


# ============================================================
# 常量
# ============================================================
TARGET_SAMPLE_RATE = 16000  # Whisper 要求的采样率
TARGET_CHANNELS = 1         # 单声道
# 从配置读取缓存大小
MAX_CACHE_SIZE = settings.ASR_CACHE_SIZE if hasattr(settings, "ASR_CACHE_SIZE") else 128


# ---- 并发控制: ASR 请求信号量 ----
# 限制同时进行的 ASR 识别数量，防止 GPU/OOM 过载
_asr_semaphore = asyncio.Semaphore(
    settings.ASR_MAX_CONCURRENCY if hasattr(settings, "ASR_MAX_CONCURRENCY") else 2
)


# ============================================================
# 音频预处理工具
# ============================================================
def preprocess_audio(
    audio_bytes: bytes,
    source_rate: int = 16000,
    source_channels: int = 1,
) -> Tuple[np.ndarray, int]:
    """
    音频预处理流水线

    1. 将原始字节解码为 numpy 数组
    2. 重采样至 16000Hz
    3. 转换为单声道
    4. 归一化到 [-1, 1] 范围
    5. 转为 float32 格式（Whisper 要求）

    参数:
        audio_bytes: 原始音频字节数据（支持 WAV / PCM 格式）
        source_rate: 原始采样率（默认 16000）
        source_channels: 原始声道数（默认 1，即单声道）

    返回:
        (audio_array, sample_rate)
        - audio_array: float32 类型的 numpy 数组，值域 [-1, 1]
        - sample_rate: 16000
    """
    # ---- 解码音频字节 ----
    # 默认按 16-bit PCM 处理；若为 WAV 则从头部读取实际位宽
    sample_width = 2
    try:
        import wave
        with io.BytesIO(audio_bytes) as buf:
            with wave.open(buf, "rb") as wf:
                source_rate = wf.getframerate()
                source_channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                raw_frames = wf.readframes(wf.getnframes())
    except (wave.Error, struct.error):
        # 不是 WAV 格式，当作原始 PCM 处理
        raw_frames = audio_bytes

    # ---- 字节转 numpy 数组 ----
    if sample_width == 2:
        audio_array = np.frombuffer(raw_frames, dtype=np.int16).astype(np.float32)
    elif sample_width == 4:
        audio_array = np.frombuffer(raw_frames, dtype=np.int32).astype(np.float32)
    else:
        # 默认当作 int16 处理
        audio_array = np.frombuffer(raw_frames, dtype=np.int16).astype(np.float32)

    # ---- 转换为单声道 ----
    if source_channels > 1:
        audio_array = audio_array.reshape(-1, source_channels)
        audio_array = audio_array.mean(axis=1)  # 取平均降为单声道

    # ---- 重采样至 16000Hz ----
    if source_rate != TARGET_SAMPLE_RATE:
        audio_array = _resample(audio_array, source_rate, TARGET_SAMPLE_RATE)

    # ---- 归一化 ----
    max_val = np.max(np.abs(audio_array))
    if max_val > 0:
        audio_array = audio_array / max_val

    # ---- 确保 float32 ----
    audio_array = audio_array.astype(np.float32)

    return audio_array, TARGET_SAMPLE_RATE


def _resample(
    audio: np.ndarray,
    orig_rate: int,
    target_rate: int,
) -> np.ndarray:
    """
    将音频重采样到目标采样率

    使用 scipy.signal.resample 在频域进行重采样。

    参数:
        audio: 原始音频数组
        orig_rate: 原始采样率
        target_rate: 目标采样率

    返回:
        重采样后的音频数组
    """
    try:
        from scipy import signal
        number_of_samples = int(len(audio) * target_rate / orig_rate)
        resampled = signal.resample(audio, number_of_samples)
        return resampled.astype(np.float32)
    except ImportError:
        logger.warning("scipy 未安装，使用线性插值重采样")
        # 降采样回退：每隔 N 个取一个
        ratio = orig_rate / target_rate
        indices = np.round(np.arange(0, len(audio), ratio)).astype(int)
        indices = indices[indices < len(audio)]
        return audio[indices].astype(np.float32)


def audio_fingerprint(audio_bytes: bytes) -> str:
    """
    计算音频指纹（SHA256 哈希的前 16 位）

    用于缓存键值，避免重复识别完全相同的音频。

    参数:
        audio_bytes: 原始音频字节数据

    返回:
        16 字符的十六进制哈希字符串
    """
    return hashlib.sha256(audio_bytes).hexdigest()[:16]


# ============================================================
# VAD 语音活动检测
# ============================================================
class VoiceActivityDetector:
    """
    基于 WebRTC VAD 的语音活动检测器

    用于检测音频片段中是否包含有效语音，过滤静音和噪声。
    """

    def __init__(self, sensitivity: int = None):
        """
        初始化 VAD 检测器

        参数:
            sensitivity: VAD 灵敏度 (0-3)
                        0 = 最宽松（捕获更多语音，容忍更多噪声）
                        3 = 最严格（只捕获清晰语音）
                        默认从 settings.VAD_SENSITIVITY 读取
        """
        self.sensitivity = sensitivity if sensitivity is not None else settings.VAD_SENSITIVITY
        self._vad = None

    def _get_vad(self):
        """延迟初始化 webrtcvad"""
        if self._vad is None:
            import webrtcvad
            self._vad = webrtcvad.Vad(self.sensitivity)
        return self._vad

    def is_speech(self, audio_bytes: bytes, sample_rate: int = 16000) -> bool:
        """
        检测音频片段是否包含语音

        WebRTC VAD 要求输入为 16-bit PCM 格式，
        且帧长为 10ms / 20ms / 30ms。

        参数:
            audio_bytes: PCM 音频字节数据
            sample_rate: 采样率 (8000, 16000, 32000, 48000)

        返回:
            True 表示检测到语音，False 表示静音/噪声
        """
        vad = self._get_vad()

        # 转换为 16-bit PCM
        audio_array = np.frombuffer(audio_bytes, dtype=np.int16)

        # WebRTC VAD 要求帧长为 10ms / 20ms / 30ms
        frame_ms = 30
        frame_size = int(sample_rate * frame_ms / 1000)

        # 将音频切分为固定帧长，逐帧检测
        speech_frames = 0
        total_frames = 0

        for start in range(0, len(audio_array), frame_size):
            frame = audio_array[start:start + frame_size]
            if len(frame) < frame_size:
                break  # 丢弃不足一帧的尾部

            total_frames += 1
            try:
                if vad.is_speech(frame.tobytes(), sample_rate):
                    speech_frames += 1
            except Exception:
                continue

        if total_frames == 0:
            return False

        # 超过 30% 的帧被判定为语音 → 认为包含有效语音
        speech_ratio = speech_frames / total_frames
        return speech_ratio > 0.3

    def detect_speech_segments(
        self,
        audio_array: np.ndarray,
        sample_rate: int = 16000,
    ) -> list:
        """
        检测音频中的语音段落（起止时间戳）

        参数:
            audio_array: float32 音频数组
            sample_rate: 采样率

        返回:
            [(start_sec, end_sec), ...] 语音段落的起止时间列表
        """
        # 转回 int16 PCM
        pcm_int16 = (audio_array * 32767).astype(np.int16)

        vad = self._get_vad()
        frame_ms = 30
        frame_size = int(sample_rate * frame_ms / 1000)

        segments = []
        in_speech = False
        seg_start = 0.0

        for start in range(0, len(pcm_int16), frame_size):
            frame = pcm_int16[start:start + frame_size]
            if len(frame) < frame_size:
                break

            timestamp = start / sample_rate
            is_speech = False
            try:
                is_speech = vad.is_speech(frame.tobytes(), sample_rate)
            except Exception:
                continue

            if is_speech and not in_speech:
                # 语音开始
                in_speech = True
                seg_start = timestamp
            elif not is_speech and in_speech:
                # 语音结束
                in_speech = False
                segments.append((seg_start, timestamp))

        # 处理最后一段未闭合的语音
        if in_speech:
            segments.append((seg_start, len(pcm_int16) / sample_rate))

        return segments


# ============================================================
# ASR 缓存
# ============================================================
class ASRResult:
    """ASR 识别结果"""

    def __init__(
        self,
        text: str,
        confidence: float = 0.0,
        language: str = "zh",
        segments: Optional[list] = None,
        duration: float = 0.0,
    ):
        self.text = text
        self.confidence = confidence
        self.language = language
        self.segments = segments or []
        self.duration = duration

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "confidence": self.confidence,
            "language": self.language,
            "segments": self.segments,
            "duration": self.duration,
        }


class ASRResultCache:
    """
    ASR 识别结果缓存

    基于音频指纹缓存识别结果，避免重复识别相同音频。
    使用 LRU 策略淘汰，最大缓存条目数由 MAX_CACHE_SIZE 控制。
    """

    def __init__(self, max_size: int = MAX_CACHE_SIZE):
        self._max_size = max_size
        # OrderedDict 实现 LRU 淘汰
        self._cache: OrderedDict = OrderedDict()

    def get(self, fingerprint: str) -> Optional[ASRResult]:
        """从缓存中获取识别结果"""
        if fingerprint in self._cache:
            # 移到末尾（最近使用）
            self._cache.move_to_end(fingerprint)
            logger.debug(f"[ASR缓存] 命中: {fingerprint}")
            return self._cache[fingerprint]
        return None

    def put(self, fingerprint: str, result: ASRResult):
        """存入缓存"""
        if fingerprint in self._cache:
            self._cache.move_to_end(fingerprint)
        else:
            if len(self._cache) >= self._max_size:
                # 淘汰最久未使用的
                self._cache.popitem(last=False)
            logger.debug(f"[ASR缓存] 存入: {fingerprint}")
        self._cache[fingerprint] = result

    def clear(self):
        """清空缓存"""
        self._cache.clear()
        logger.info("[ASR缓存] 已清空")

    @property
    def size(self) -> int:
        return len(self._cache)


# ============================================================
# 流式识别 — 会话缓冲区
# ============================================================
@dataclass
class StreamSession:
    """
    流式识别会话

    为每个连接维护独立的音频缓冲区和状态。
    当检测到语音结束（静音超时）时触发识别。
    """
    session_id: str
    buffer: list = field(default_factory=list)  # 音频块列表
    last_audio_time: float = 0.0                 # 最后接收音频的时间戳
    is_speech_active: bool = False               # 当前是否在语音中
    silence_duration: float = 0.0                # 当前静音时长
    accumulated_text: str = ""                   # 已累计的识别文本

    @property
    def buffer_duration_ms(self) -> int:
        """缓冲区总时长（毫秒）"""
        # 每块按 30ms 估算，实际应通过采样率计算
        return len(self.buffer) * 30

    def clear_buffer(self):
        """清空音频缓冲区"""
        self.buffer.clear()
        self.is_speech_active = False
        self.silence_duration = 0.0


# ============================================================
# Whisper 语音识别引擎
# ============================================================
class WhisperASR:
    """
    OpenAI Whisper 语音识别引擎

    支持模型:
      - tiny    (39M 参数, 速度快, 准确率较低)
      - base    (74M 参数, 平衡速度和准确率)
      - small   (244M 参数)
      - medium  (769M 参数)
      - large   (1550M 参数, 准确率最高, 速度最慢)
    """

    # 模型名称到参数的映射
    MODEL_SIZES = {
        "tiny": "tiny",
        "base": "base",
        "small": "small",
        "medium": "medium",
        "large": "large",
    }

    def __init__(self, model_size: str = None):
        """
        初始化 Whisper 引擎

        参数:
            model_size: 模型大小 (tiny/base/small/medium/large)
                        默认从 settings.WHISPER_MODEL_SIZE 读取
        """
        self.model_size = model_size or settings.WHISPER_MODEL_SIZE
        if self.model_size not in self.MODEL_SIZES:
            logger.warning(
                f"不支持的模型大小: {self.model_size}，"
                f"使用默认值 'base'"
            )
            self.model_size = "base"

        self._model = None
        logger.info(f"[Whisper] 初始化引擎，模型: {self.model_size}")

    async def load_model(self):
        """
        加载 Whisper 模型

        Whisper 的 load_model 是 CPU 密集型操作，
        使用 run_in_executor 避免阻塞事件循环。
        """
        import whisper

        loop = asyncio.get_event_loop()
        logger.info(f"[Whisper] 正在加载模型 '{self.model_size}'...")

        def _load():
            return whisper.load_model(self.model_size)

        self._model = await loop.run_in_executor(None, _load)
        logger.info(f"[Whisper] 模型 '{self.model_size}' 加载完成")
        return self

    async def transcribe(
        self,
        audio: np.ndarray,
        language: Optional[str] = None,
        **kwargs,
    ) -> dict:
        """
        执行语音识别

        参数:
            audio: float32 格式的音频数组 (16000Hz, 单声道)
            language: 语言代码 (zh/en/ja/None=自动检测)
            **kwargs: 传递给 whisper 的额外参数

        返回:
            {
                "text": "识别文本",
                "segments": [...],
                "language": "zh",
                "confidence": 0.95,
            }
        """
        if self._model is None:
            await self.load_model()

        loop = asyncio.get_event_loop()

        def _transcribe():
            transcribe_opts = {
                "language": language,
            }
            transcribe_opts.update(kwargs)
            result = self._model.transcribe(audio, **transcribe_opts)

            # 计算平均置信度
            avg_confidence = 0.0
            if result.get("segments"):
                confs = [s.get("confidence", 0) for s in result["segments"] if s.get("confidence")]
                avg_confidence = sum(confs) / len(confs) if confs else 0.0

            return {
                "text": result.get("text", "").strip(),
                "segments": result.get("segments", []),
                "language": result.get("language", language or "zh"),
                "confidence": avg_confidence,
            }

        return await loop.run_in_executor(None, _transcribe)


# ============================================================
# ASR 服务（对外的统一接口）
# ============================================================
class ASRService:
    """
    语音识别服务 — 统一对外接口

    用法:
        asr = ASRService()
        await asr.initialize()

        # 文件识别
        text = await asr.recognize_file("/path/to/audio.wav")

        # 流式识别
        await asr.recognize_stream("session_1", audio_chunk_bytes)
        # 当检测到语音结束时，返回识别结果

        # 兼容原有接口
        result = await asr.transcribe(audio_bytes, language="zh")
    """

    def __init__(self):
        # Whisper 引擎
        self._engine: Optional[WhisperASR] = None

        # VAD 检测器
        self._vad: Optional[VoiceActivityDetector] = None

        # 缓存
        self._cache = ASRResultCache()

        # 流式会话缓冲区: session_id -> StreamSession
        self._stream_sessions: Dict[str, StreamSession] = {}

        # 静音超时阈值（秒），超过此值认为语音结束
        self.silence_timeout: float = getattr(settings, "SILENCE_TIMEOUT", 1.5)

        # 最小语音长度（毫秒），低于此值忽略
        self.min_speech_ms: int = getattr(settings, "MIN_SPEECH_MS", 300)

        # 最大会话缓冲时长（毫秒），超过则强制识别
        self.max_buffer_ms: int = 30000

        self._initialized = False

    async def initialize(self):
        """
        初始化 ASR 服务

        加载 Whisper 模型和 VAD 检测器。
        在应用 startup 时调用。
        """
        logger.info("[ASR] 正在初始化...")

        # 初始化 Whisper 引擎
        self._engine = WhisperASR(model_size=settings.WHISPER_MODEL_SIZE)
        await self._engine.load_model()

        # 初始化 VAD
        self._vad = VoiceActivityDetector()

        self._initialized = True
        logger.info("[ASR] 初始化完成")
        return self

    # ============================================================
    # 文件识别
    # ============================================================

    async def recognize_file(
        self,
        audio_path: str,
        language: Optional[str] = None,
        use_vad: bool = True,
        use_cache: bool = True,
    ) -> ASRResult:
        """
        识别音频文件

        参数:
            audio_path: 音频文件路径（支持 WAV / MP3 / M4A / FLAC 等格式）
            language: 语言代码，None=自动检测
            use_vad: 是否使用 VAD 过滤静音
            use_cache: 是否使用缓存

        返回:
            ASRResult 对象
        """
        if not self._initialized:
            await self.initialize()

        logger.info(f"[ASR文件] 开始识别: {audio_path}")

        # ---- 读取文件 ----
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()

        # ---- 缓存检查 ----
        if use_cache:
            fp = audio_fingerprint(audio_bytes)
            cached = self._cache.get(fp)
            if cached:
                logger.info(f"[ASR文件] 缓存命中: {audio_path}")
                return cached

        # ---- 音频预处理 ----
        audio_array, sample_rate = preprocess_audio(audio_bytes)

        # ---- VAD 过滤 ----
        if use_vad and self._vad:
            # 仅保留语音段
            segments = self._vad.detect_speech_segments(audio_array, sample_rate)
            if segments:
                # 拼接所有语音段
                speech_parts = []
                for seg_start, seg_end in segments:
                    start_idx = int(seg_start * sample_rate)
                    end_idx = int(seg_end * sample_rate)
                    speech_parts.append(audio_array[start_idx:end_idx])

                if speech_parts:
                    audio_array = np.concatenate(speech_parts)
                    logger.info(
                        f"[ASR文件] VAD 过滤后: "
                        f"{sum(e - s for s, e in segments):.2f}s 语音"
                    )
                else:
                    logger.warning("[ASR文件] VAD 未检测到语音段")
                    result = ASRResult(text="", confidence=0, duration=0)
                    return result

        # ---- Whisper 识别 ----
        start_time = time.time()
        raw_result = await self._engine.transcribe(audio_array, language=language)
        elapsed = time.time() - start_time

        result = ASRResult(
            text=raw_result["text"],
            confidence=raw_result["confidence"],
            language=raw_result["language"],
            segments=raw_result["segments"],
            duration=elapsed,
        )

        logger.info(
            f"[ASR文件] 识别完成: "
            f"text=\"{result.text[:50]}...\" "
            f"confidence={result.confidence:.2f} "
            f"耗时={elapsed:.2f}s"
        )

        # ---- 写入缓存 ----
        if use_cache:
            self._cache.put(fp, result)

        return result

    # ============================================================
    # 流式识别
    # ============================================================

    async def recognize_stream(
        self,
        session_id: str,
        audio_chunk: bytes,
        language: Optional[str] = None,
    ) -> Optional[ASRResult]:
        """
        流式语音识别 — 接收音频块，累积识别

        调用策略:
            - 每个连接创建独立会话 (session_id)
            - 音频块被缓存到缓冲区
            - VAD 检测到语音结束时触发识别
            - 缓冲区超时 (max_buffer_ms) 强制识别
            - 返回 None 表示还在收集中

        参数:
            session_id: 会话唯一标识（由 WebSocket 模块传入）
            audio_chunk: 音频块字节数据（PCM int16, 16000Hz, 单声道）
            language: 语言代码

        返回:
            - ASRResult: 语音结束，返回识别结果
            - None: 语音还在继续，继续累积
        """
        if not self._initialized:
            await self.initialize()

        # 获取或创建会话
        if session_id not in self._stream_sessions:
            self._stream_sessions[session_id] = StreamSession(session_id=session_id)
            logger.debug(f"[ASR流式] 创建新会话: {session_id}")

        session = self._stream_sessions[session_id]
        now = time.time()

        # ---- VAD 检测当前块 ----
        is_speech = False
        if self._vad:
            is_speech = self._vad.is_speech(audio_chunk, TARGET_SAMPLE_RATE)

        if is_speech:
            # 语音活跃: 累积到缓冲区
            session.buffer.append(audio_chunk)
            session.is_speech_active = True
            session.last_audio_time = now
            session.silence_duration = 0.0
            logger.debug(f"[ASR流式] {session_id} 语音累积中: {len(session.buffer)} 块")

        else:
            # 静音
            if session.is_speech_active:
                # 语音刚结束，开始计时静音
                session.silence_duration += now - session.last_audio_time
                session.last_audio_time = now

                # 静音超时 → 触发识别
                if session.silence_duration >= self.silence_timeout:
                    return await self._flush_stream(session, language)

            # 缓冲区超时保护
            if session.buffer and session.buffer_duration_ms >= self.max_buffer_ms:
                logger.info(f"[ASR流式] {session_id} 缓冲区超时，强制识别")
                return await self._flush_stream(session, language)

        return None

    async def _flush_stream(
        self,
        session: StreamSession,
        language: Optional[str],
    ) -> ASRResult:
        """
        将流式缓冲区的音频合并并识别
        识别完毕后清空缓冲区
        """
        if not session.buffer:
            return ASRResult(text="", confidence=0, duration=0)

        # ---- 合并缓冲区音频 ----
        raw_bytes = b"".join(session.buffer)

        # ---- 缓存检查 ----
        fp = audio_fingerprint(raw_bytes)
        cached = self._cache.get(fp)
        if cached:
            session.clear_buffer()
            # 追加到已累计文本
            session.accumulated_text += cached.text
            return cached

        # ---- 音频预处理 ----
        # 流式传输的是 PCM int16，直接转为 numpy 数组
        audio_array = (
            np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32767.0
        )

        # ---- 并发控制: 通过信号量限制同时识别的请求数 ----
        raw_result = {}
        async with _asr_semaphore:
            start_time = time.time()
            raw_result = await self._engine.transcribe(audio_array, language=language)
            elapsed = time.time() - start_time

        result = ASRResult(
            text=raw_result.get("text", ""),
            confidence=raw_result.get("confidence", 0.0),
            language=raw_result.get("language", language or "zh"),
            segments=raw_result.get("segments", []),
            duration=elapsed,
        )

        # ---- 写入缓存 ----
        self._cache.put(fp, result)

        # ---- 更新会话状态 ----
        session.accumulated_text += result.text
        session.clear_buffer()

        logger.info(
            f"[ASR流式] 识别完成: "
            f"text=\"{result.text[:50]}...\" "
            f"耗时={elapsed:.2f}s"
        )

        return result

    async def reset_stream(self, session_id: str):
        """重置指定会话的流式缓冲区"""
        if session_id in self._stream_sessions:
            del self._stream_sessions[session_id]
            logger.debug(f"[ASR流式] 重置会话: {session_id}")

    def get_stream_text(self, session_id: str) -> str:
        """获取会话已累计的识别文本"""
        session = self._stream_sessions.get(session_id)
        return session.accumulated_text if session else ""

    # ============================================================
    # 兼容接口（原有 transcribe 保持可用）
    # ============================================================

    async def transcribe(
        self,
        audio_data: bytes,
        language: str = "zh",
        use_vad: bool = True,
    ) -> dict:
        """
        语音识别（兼容原有接口）

        这是从音频字节直接识别的方法，保持与旧调用方兼容。

        参数:
            audio_data: 音频字节数据
            language: 语言代码
            use_vad: 是否使用 VAD

        返回:
            {"text": str, "confidence": float, "language": str, "segments": list}
        """
        if not self._initialized:
            await self.initialize()

        # ---- 缓存检查 ----
        fp = audio_fingerprint(audio_data)
        cached = self._cache.get(fp)
        if cached:
            return cached.to_dict()

        # ---- 音频预处理 ----
        audio_array, sample_rate = preprocess_audio(audio_data)

        # ---- VAD 过滤 ----
        if use_vad and self._vad:
            if not self._vad.is_speech(audio_data):
                logger.debug("[ASR] VAD 未检测到语音")
                return {"text": "", "confidence": 0, "language": language, "segments": []}

        # ---- Whisper 识别 ----
        raw_result = await self._engine.transcribe(audio_array, language=language)

        result = ASRResult(
            text=raw_result["text"],
            confidence=raw_result["confidence"],
            language=raw_result["language"],
            segments=raw_result["segments"],
        )

        # ---- 写入缓存 ----
        self._cache.put(fp, result)

        return result.to_dict()

    # ============================================================
    # 生命周期管理
    # ============================================================

    async def cleanup(self):
        """清理 ASR 服务资源"""
        logger.info("[ASR] 正在清理资源...")

        self._cache.clear()
        self._stream_sessions.clear()

        # 释放模型引用，允许 GC 回收
        if self._engine:
            self._engine._model = None

        self._initialized = False
        logger.info("[ASR] 清理完成")

    @property
    def cache_stats(self) -> dict:
        """缓存统计信息"""
        return {
            "cache_size": self._cache.size,
            "max_cache_size": MAX_CACHE_SIZE,
            "active_stream_sessions": len(self._stream_sessions),
        }
