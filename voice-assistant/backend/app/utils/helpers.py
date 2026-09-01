"""
工具函数模块
提供通用的辅助函数
"""

import json
import hashlib
import uuid
from datetime import datetime
from typing import Any, Dict, Optional


def generate_id(prefix: str = "") -> str:
    """生成唯一ID"""
    unique_id = str(uuid.uuid4()).replace("-", "")[:16]
    return f"{prefix}_{unique_id}" if prefix else unique_id


def generate_hash(data: str) -> str:
    """生成字符串哈希"""
    return hashlib.md5(data.encode()).hexdigest()


def format_timestamp(timestamp: Optional[datetime] = None) -> str:
    """格式化时间戳"""
    if timestamp is None:
        timestamp = datetime.now()
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")


def parse_json_safe(data: str) -> Optional[Dict[str, Any]]:
    """安全解析JSON字符串"""
    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return None


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """截断文本"""
    if len(text) <= max_length:
        return text
    return text[:max_length].rstrip() + suffix


def convert_audio_format(audio_data: bytes, target_format: str = "mp3") -> bytes:
    """转换音频格式（占位函数）"""
    # 实际项目中会调用ffmpeg等工具进行格式转换
    return audio_data


def validate_audio_data(audio_data: bytes) -> bool:
    """验证音频数据是否有效"""
    # 检查文件大小
    if len(audio_data) == 0:
        return False
    # 检查文件头
    supported_headers = [b"RIFF", b"OggS", b"fLaC", b"ID3"]
    return any(audio_data.startswith(header) for header in supported_headers)


class Logger:
    """简易日志工具类"""

    @staticmethod
    def info(message: str):
        """记录信息日志"""
        print(f"[INFO] {format_timestamp()} - {message}")

    @staticmethod
    def error(message: str, exc_info: bool = False):
        """记录错误日志"""
        print(f"[ERROR] {format_timestamp()} - {message}")
        if exc_info:
            import traceback
            traceback.print_exc()

    @staticmethod
    def warning(message: str):
        """记录警告日志"""
        print(f"[WARN] {format_timestamp()} - {message}")

    @staticmethod
    def debug(message: str):
        """记录调试日志"""
        print(f"[DEBUG] {format_timestamp()} - {message}")
