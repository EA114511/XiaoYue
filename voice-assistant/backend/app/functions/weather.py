"""
天气查询模块 (Weather API)

基于免费天气 API（wttr.in）提供实时天气查询，支持：
  - wttr.in 主 API（免费，无需 Key）
  - OpenWeatherMap 备用 API（需配置 API Key）
  - 5 分钟缓存（同一城市不重复请求）
  - 从文本中自动提取城市名
  - 结构化和文本化两种返回格式
"""

import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

import httpx

from app.core.config import settings
from app.core.http_client import get_http_client

logger = logging.getLogger("voice-assistant.weather")

# ============================================================
# 默认城市 & 城市名称映射
# ============================================================

DEFAULT_CITY = "北京"

# 中文城市名 → 英文名（wttr.in 支持中文拼音/英文）
CITY_NAME_MAP: Dict[str, str] = {
    "北京": "Beijing",
    "上海": "Shanghai",
    "广州": "Guangzhou",
    "深圳": "Shenzhen",
    "杭州": "Hangzhou",
    "成都": "Chengdu",
    "武汉": "Wuhan",
    "南京": "Nanjing",
    "天津": "Tianjin",
    "重庆": "Chongqing",
    "苏州": "Suzhou",
    "西安": "Xi'an",
    "长沙": "Changsha",
    "青岛": "Qingdao",
    "大连": "Dalian",
    "厦门": "Xiamen",
    "宁波": "Ningbo",
    "福州": "Fuzhou",
    "合肥": "Hefei",
    "郑州": "Zhengzhou",
    "昆明": "Kunming",
    "沈阳": "Shenyang",
    "哈尔滨": "Harbin",
    "香港": "Hong Kong",
    "台北": "Taipei",
    "澳门": "Macau",
}

# 城市中文名正则（用于从文本中提取）
CITY_PATTERN = "|".join(re.escape(name) for name in CITY_NAME_MAP.keys())

# ============================================================
# 缓存
# ============================================================

# 缓存格式: {city_key: {"data": dict, "timestamp": float}}
_weather_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL = 300  # 5 分钟（秒）


def _cache_key(city: str) -> str:
    """生成缓存的哈希键"""
    raw = city.strip().lower()
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _get_from_cache(city: str) -> Optional[Dict[str, Any]]:
    """读取缓存，未命中或过期返回 None"""
    key = _cache_key(city)
    entry = _weather_cache.get(key)
    if entry is None:
        return None
    if time.time() - entry["timestamp"] > CACHE_TTL:
        del _weather_cache[key]
        return None
    return entry["data"]


def _set_cache(city: str, data: Dict[str, Any]):
    """写入缓存"""
    key = _cache_key(city)
    _weather_cache[key] = {"data": data, "timestamp": time.time()}


# ============================================================
# 城市名提取
# ============================================================

def extract_city(text: str) -> Optional[str]:
    """从用户输入文本中提取城市名

    示例:
        "北京明天天气" → "北京"
        "上海气温"     → "上海"
    """
    match = re.search(CITY_PATTERN, text)
    if match:
        return match.group(0)
    return None


def to_api_city(city: str) -> str:
    """将城市名转为 API 请求用的英文名"""
    return CITY_NAME_MAP.get(city, city)


def to_display_city(api_city: str) -> str:
    """将 API 返回的城市名转回中文"""
    reverse_map = {v: k for k, v in CITY_NAME_MAP.items()}
    return reverse_map.get(api_city, api_city)


# ============================================================
# wttr.in API
# ============================================================

WTTR_BASE_URL = "https://wttr.in"


async def _fetch_from_wttr(city: str) -> Optional[Dict[str, Any]]:
    """通过 wttr.in（免费，无需 Key）查询天气

    请求 https://wttr.in/{city}?format=j1 返回 JSON。
    """
    api_city = to_api_city(city)
    url = f"{WTTR_BASE_URL}/{api_city}?format=j1"

    logger.debug(f"[天气-wttr] 请求: {url}")

    try:
        client = get_http_client()
        resp = await client.get(url, headers={"User-Agent": "curl/8.0"}, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
    except httpx.TimeoutException:
        logger.warning(f"[天气-wttr] 请求超时: {city}")
        return None
    except httpx.HTTPStatusError as e:
        logger.warning(f"[天气-wttr] HTTP {e.response.status_code} for {city}")
        return None
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"[天气-wttr] 解析失败: {e}")
        return None
    except Exception as e:
        logger.warning(f"[天气-wttr] 异常: {e}")
        return None

    # ---- 解析 wttr.in JSON ----
    try:
        current = data["current_condition"][0]
        location = data.get("nearest_area", [{}])[0]
        area_name = location.get("areaName", [{}])[0].get("value", city)

        temperature = current.get("temp_C", "N/A")
        weather_desc = current.get("weatherDesc", [{}])[0].get("value", "未知")
        humidity = current.get("humidity", "N/A")
        wind_speed = current.get("windspeedKmph", "N/A")
        wind_dir = current.get("winddir16Point", "")
        feels_like = current.get("FeelsLikeC", "N/A")
        visibility = current.get("visibility", "N/A")
        uv_index = current.get("uvIndex", "N/A")

        # 风速显示
        wind_display = f"{wind_speed}km/h {wind_dir}" if wind_dir else f"{wind_speed}km/h"

        result = {
            "city": to_display_city(area_name),
            "temperature": f"{temperature}°C",
            "weather": weather_desc,
            "humidity": f"{humidity}%",
            "wind": wind_display,
            "feels_like": f"{feels_like}°C",
            "visibility": f"{visibility}km",
            "uv_index": uv_index,
            "update_time": datetime.now().strftime("%H:%M"),
            "source": "wttr.in",
        }

        logger.info(f"[天气-wttr] {city} 查询成功: {temperature}°C, {weather_desc}")
        return result

    except (KeyError, IndexError, TypeError) as e:
        logger.warning(f"[天气-wttr] 数据解析异常: {e}")
        return None


# ============================================================
# OpenWeatherMap API (备用)
# ============================================================

OWM_BASE_URL = "https://api.openweathermap.org/data/2.5"


async def _fetch_from_owm(city: str) -> Optional[Dict[str, Any]]:
    """通过 OpenWeatherMap 查询天气（需要 API Key）

    从 settings.WEATHER_API_KEY 读取 Key。
    """
    api_key = settings.WEATHER_API_KEY
    if not api_key:
        logger.debug("[天气-OWM] 未配置 API Key，跳过")
        return None

    api_city = to_api_city(city)
    url = (
        f"{OWM_BASE_URL}/weather"
        f"?q={api_city}&appid={api_key}&units={settings.WEATHER_UNITS}&lang=zh_cn"
    )

    logger.debug(f"[天气-OWM] 请求: {url}")

    try:
        client = get_http_client()
        resp = await client.get(url, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.warning(f"[天气-OWM] 城市不存在: {city}")
        elif e.response.status_code == 401:
            logger.warning(f"[天气-OWM] API Key 无效")
        else:
            logger.warning(f"[天气-OWM] HTTP {e.response.status_code}")
        return None
    except httpx.TimeoutException:
        logger.warning(f"[天气-OWM] 请求超时: {city}")
        return None
    except Exception as e:
        logger.warning(f"[天气-OWM] 异常: {e}")
        return None

    # ---- 解析 OWM JSON ----
    try:
        temp_c = data["main"]["temp"]
        feels_like = data["main"].get("feels_like", temp_c)
        weather_desc = data["weather"][0].get("description", "未知")
        humidity = data["main"].get("humidity", "N/A")
        wind_speed = data["wind"].get("speed", "N/A")
        wind_deg = data["wind"].get("deg", "")
        visibility = data.get("visibility", "N/A")

        # 可见度 km
        visibility_km = round(visibility / 1000, 1) if isinstance(visibility, (int, float)) else visibility

        result = {
            "city": city,
            "temperature": f"{round(temp_c)}°C",
            "weather": weather_desc,
            "humidity": f"{humidity}%",
            "wind": f"{round(wind_speed)}m/s",
            "feels_like": f"{round(feels_like)}°C",
            "visibility": f"{visibility_km}km",
            "uv_index": "N/A",
            "update_time": datetime.now().strftime("%H:%M"),
            "source": "openweathermap",
        }

        logger.info(f"[天气-OWM] {city} 查询成功: {round(temp_c)}°C, {weather_desc}")
        return result

    except (KeyError, IndexError, TypeError, ValueError) as e:
        logger.warning(f"[天气-OWM] 数据解析异常: {e}")
        return None


# ============================================================
# 统一 API 接口
# ============================================================

async def get_weather(
    city: str,
    default_city: str = DEFAULT_CITY,
) -> Dict[str, Any]:
    """获取指定城市的天气信息（联网查询 + 缓存）

    策略:
      1. 检查缓存（5 分钟 TTL）
      2. 先请求 wttr.in（免费，无需 Key）
      3. 失败时降级到 OpenWeatherMap（需配置 API Key）
      4. 全部失败 → 返回错误信息

    参数:
        city: 城市名（中文名如"北京"，或英文名如"Beijing"）
        default_city: 如果 city 为空时使用的默认城市

    返回:
        {
            "city": str,
            "temperature": "25°C",
            "weather": "晴朗",
            "humidity": "45%",
            "wind": "15km/h 东南风",
            "feels_like": "23°C",
            "visibility": "10km",
            "uv_index": "5",
            "update_time": "14:30",
            "success": True,
        }
        或查询失败时:
        {
            "city": city,
            "temperature": "N/A",
            "weather": "未知",
            "humidity": "N/A",
            "wind": "N/A",
            "success": False,
            "error": str,
        }
    """
    city = city.strip() if city else default_city
    if not city:
        city = default_city

    # ---- 1. 缓存命中 ----
    cached = _get_from_cache(city)
    if cached is not None:
        logger.debug(f"[天气] 缓存命中: {city}")
        cached["from_cache"] = True
        return cached

    # ---- 2. 联网查询 ----
    logger.info(f"[天气] 正在查询: {city}")

    result = await _fetch_from_wttr(city)
    if result is None:
        result = await _fetch_from_owm(city)

    # ---- 3. 结果处理 ----
    if result is not None:
        result["success"] = True
        result["from_cache"] = False
        _set_cache(city, result)
        return result

    # ---- 4. 全部失败 ----
    error_data = {
        "city": city,
        "temperature": "N/A",
        "weather": "未知",
        "humidity": "N/A",
        "wind": "N/A",
        "feels_like": "N/A",
        "visibility": "N/A",
        "uv_index": "N/A",
        "update_time": "N/A",
        "success": False,
        "error": f"无法获取{city}的天气信息，请检查城市名或网络连接",
        "from_cache": False,
    }
    logger.warning(f"[天气] 所有 API 都查询失败: {city}")
    return error_data


def get_weather_text(data: Dict[str, Any]) -> str:
    """将天气数据格式化为可读文本（适合语音播报）

    参数:
        data: get_weather() 返回的字典

    返回:
        "北京当前天气：晴朗，温度25°C，体感温度23°C，湿度45%，风力15km/h 东南风"
    """
    if not data.get("success"):
        return data.get("error", f"抱歉，暂时无法获取{data.get('city', '')}的天气信息。")

    parts = [
        f"{data['city']}当前天气：{data['weather']}",
        f"温度{data['temperature']}",
    ]

    # 体感温度（如果与气温不同）
    feels = data.get("feels_like", "")
    if feels and feels != data.get("temperature", ""):
        parts.append(f"体感{feels}")

    parts.extend([
        f"湿度{data['humidity']}",
        f"风力{data['wind']}",
    ])

    return "，".join(parts) + "。"


def format_weather_detail(data: Dict[str, Any]) -> str:
    """返回带更多细节的天气文本（适合屏幕显示）"""
    if not data.get("success"):
        return data.get("error", f"无法获取{data.get('city', '')}天气")

    lines = [
        f"📍 {data['city']} 天气",
        f"━━━━━━━━━━━━━━━━",
        f"🌤 天气状况：{data['weather']}",
        f"🌡 当前温度：{data['temperature']}",
    ]

    feels = data.get("feels_like", "")
    if feels:
        lines.append(f"🤗 体感温度：{feels}")

    lines.extend([
        f"💧 相对湿度：{data['humidity']}",
        f"🌬 风速风向：{data['wind']}",
    ])

    vis = data.get("visibility", "")
    if vis and vis != "N/A":
        lines.append(f"👁 能见度：{vis}")

    uv = data.get("uv_index", "")
    if uv and uv != "N/A":
        lines.append(f"☀️ 紫外线指数：{uv}")

    lines.extend([
        f"━━━━━━━━━━━━━━━━",
        f"⏱ 更新于 {data.get('update_time', '')}",
    ])

    return "\n".join(lines)
