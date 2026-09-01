"""
功能调用注册中心 (Function Registry)

提供统一的函数注册、查询和调用接口，支持:
  1. FUNCTION_MAP — 意图名称到处理函数的映射
  2. FUNCTION_SCHEMAS — OpenAI Function Calling 格式的函数描述
  3. call_function(intent, entities) — 按意图名称自动路由
  4. 动态注册 — 运行时添加新功能
"""

import logging
from typing import Any, Callable, Dict, List, Optional

from app.functions.device import control_device as device_control
from app.functions.services import FunctionService
from app.functions.weather import get_weather_text

logger = logging.getLogger("voice-assistant.functions")

# ============================================================
# 函数类型定义
# ============================================================

# 处理函数签名: async (entities: dict, service: FunctionService) -> str
FunctionHandler = Callable[[Dict[str, Any], FunctionService], str]

# SCHEMA 条目
FunctionSchema = Dict[str, Any]


# ============================================================
# 内置处理函数
# ============================================================

async def _handle_weather(entities: Dict[str, Any], svc: FunctionService) -> str:
    """天气查询处理函数"""
    city = entities.get("city", "北京")
    result = await svc.weather.get_current_weather(city)
    return get_weather_text(result)


async def _handle_device_control(
    entities: Dict[str, Any], svc: FunctionService
) -> str:
    """设备控制处理函数（委托 device.py）"""
    device = entities.get("device", "")
    action = entities.get("action", "")
    location = entities.get("location", "")
    params = {}

    if not device:
        return "请告诉我要控制哪个设备？"

    # 检测是否为批量操作（如"所有灯"、"全部灯"）
    batch = entities.get("batch", False)

    # 提取调节参数（温度/音量/亮度/风速）
    for key in ("temperature", "temp", "volume", "brightness", "speed", "温度", "音量", "亮度", "风速"):
        if key in entities:
            params[key] = entities[key]

    result = await device_control(
        device=device,
        action=action,
        location=location or None,
        params=params or None,
        batch=batch,
    )
    return result.get("message", f"执行{device}{action}失败")


async def _handle_schedule(entities: Dict[str, Any], svc: FunctionService) -> str:
    """日程管理处理函数"""
    event = entities.get("event_name", "")
    date = entities.get("date", "")
    time = entities.get("time", "")

    if event and date:
        return f"已为您记录日程：{date} {time} {event}"
    if date:
        return f"正在查询{date}的日程安排..."
    return "请告诉我您想设置什么提醒或查询哪天的日程？"


async def _handle_music_play(entities: Dict[str, Any], svc: FunctionService) -> str:
    """音乐播放处理函数"""
    artist = entities.get("artist", "")
    song = entities.get("song", "")
    genre = entities.get("genre", "")

    if artist and song:
        return f"正在为您播放{artist}的{song}..."
    if artist:
        return f"正在为您播放{artist}的热门歌曲..."
    if genre:
        return f"正在为您播放{genre}音乐..."
    if song:
        return f"正在为您播放{song}..."
    return "正在为您播放音乐..."


# ============================================================
# 函数注册表
# ============================================================

class FunctionRegistry:
    """
    函数注册中心

    维护 FUNCTION_MAP（意图→处理函数）和 FUNCTION_SCHEMAS（描述信息），
    支持运行时动态注册新功能。

    用法:
        registry = FunctionRegistry()
        reply = await registry.call_function("weather_query", {"city": "北京"})
    """

    def __init__(self):
        self._service = FunctionService()

        # ---- FUNCTION_MAP: 意图名称 → 处理函数 ----
        self._function_map: Dict[str, FunctionHandler] = {
            "weather_query": _handle_weather,
            "device_control": _handle_device_control,
            "schedule": _handle_schedule,
            "music_play": _handle_music_play,
        }

        # ---- FUNCTION_SCHEMAS: OpenAI Function Calling 格式 ----
        self._function_schemas: List[FunctionSchema] = [
            {
                "name": "get_weather",
                "description": "查询指定城市的当前天气信息，包括温度、天气状况、湿度、风速等",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": '城市名，如"北京"、"上海"、"广州"等',
                        }
                    },
                    "required": ["city"],
                },
            },
            {
                "name": "control_device",
                "description": "控制智能家居设备，支持打开、关闭、调节等操作",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device": {
                            "type": "string",
                            "description": '设备名，如"灯"、"空调"、"电视"、"窗帘"等',
                        },
                        "action": {
                            "type": "string",
                            "description": '要执行的操作，"打开"或"关闭"',
                            "enum": ["打开", "关闭"],
                        },
                    },
                    "required": ["device", "action"],
                },
            },
            {
                "name": "create_schedule",
                "description": "创建日程提醒或安排事件",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "event_name": {
                            "type": "string",
                            "description": '日程事件名称，如"会议"、"生日"等',
                        },
                        "date": {
                            "type": "string",
                            "description": '日期，格式 YYYY-MM-DD，或"今天"、"明天"等',
                        },
                        "time": {
                            "type": "string",
                            "description": '时间，格式 HH:MM，如"14:30"',
                        },
                    },
                    "required": ["event_name", "date"],
                },
            },
            {
                "name": "play_music",
                "description": "播放音乐，支持按歌手名、歌曲名或音乐类型播放",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "artist": {
                            "type": "string",
                            "description": '歌手名，如"周杰伦"、"林俊杰"等',
                        },
                        "song": {
                            "type": "string",
                            "description": "歌曲名",
                        },
                        "genre": {
                            "type": "string",
                            "description": '音乐类型，如"流行"、"古典"、"摇滚"等',
                        },
                    },
                },
            },
        ]

    # ============================================================
    # 属性访问
    # ============================================================

    @property
    def function_map(self) -> Dict[str, FunctionHandler]:
        """获取所有已注册的意图→函数映射（只读视图）"""
        return dict(self._function_map)

    @property
    def function_schemas(self) -> List[FunctionSchema]:
        """获取所有已注册的函数描述（OpenAI Function Calling 格式）"""
        return list(self._function_schemas)

    # ============================================================
    # 核心方法
    # ============================================================

    async def call_function(
        self, intent: str, entities: Dict[str, Any]
    ) -> str:
        """
        按意图名称调用对应的处理函数

        参数:
            intent: 意图名称（如 "weather_query"）
            entities: 从 NLU 提取的参数字典（如 {"city": "北京"}）

        返回:
            适合语音播报的回复文本
        """
        handler = self._function_map.get(intent)
        if handler is None:
            logger.warning(f"[FuncReg] 未注册的意图: {intent}")
            return f'抱歉，我不支持"{intent}"功能。'

        logger.info(
            f"[FuncReg] 调用函数: intent={intent}, entities={entities}"
        )

        try:
            result = await handler(entities, self._service)
            logger.info(
                f"[FuncReg] 执行成功: intent={intent}, result=\"{result[:60]}...\""
            )
            return result
        except Exception as e:
            logger.error(f"[FuncReg] 执行异常: intent={intent}, error={e}")
            return f"执行{intent}时出现错误，请稍后再试。"

    def get_function_schemas(self) -> List[FunctionSchema]:
        """获取全部函数描述（用于大模型 Function Calling）"""
        return self.function_schemas

    def get_schema_by_name(self, name: str) -> Optional[FunctionSchema]:
        """根据函数名查找对应的 schema"""
        for schema in self._function_schemas:
            if schema["name"] == name:
                return schema
        return None

    # ============================================================
    # 动态注册
    # ============================================================

    def register(
        self,
        intent: str,
        handler: FunctionHandler,
        schema: Optional[FunctionSchema] = None,
    ):
        """
        动态注册一个新功能

        参数:
            intent: 意图名称（也是 FUNCTION_MAP 的键）
            handler: 异步处理函数，签名: async (entities, service) -> str
            schema: OpenAI Function Calling schema（可选）
                   提供后会自动加入 FUNCTION_SCHEMAS
        """
        if intent in self._function_map:
            logger.warning(f"[FuncReg] 覆盖已注册的意图: {intent}")

        self._function_map[intent] = handler
        logger.info(f"[FuncReg] 注册成功: intent={intent}")

        if schema is not None:
            # 检查是否已存在同名 schema
            existing = self.get_schema_by_name(schema.get("name", ""))
            if existing:
                self._function_schemas.remove(existing)
            self._function_schemas.append(schema)
            logger.info(
                f"[FuncReg] 注册 schema: name={schema.get('name')}"
            )

    def unregister(self, intent: str) -> bool:
        """
        注销一个已注册的功能

        返回:
            True 表示成功注销，False 表示意图不存在
        """
        if intent not in self._function_map:
            logger.warning(f"[FuncReg] 意图不存在，无法注销: {intent}")
            return False

        del self._function_map[intent]
        logger.info(f"[FuncReg] 注销成功: intent={intent}")
        return True

    def has_function(self, intent: str) -> bool:
        """检查意图是否已注册"""
        return intent in self._function_map


# ============================================================
# 全局单例
# ============================================================

# 创建全局 FUNCTION_MAP 字典（直接访问兼容）
FUNCTION_MAP: Dict[str, FunctionHandler] = {}

# 创建全局 FUNCTION_SCHEMAS 列表
FUNCTION_SCHEMAS: List[FunctionSchema] = []

# 全局注册表实例
_registry: Optional[FunctionRegistry] = None


def get_registry() -> FunctionRegistry:
    """获取全局 FunctionRegistry 单例"""
    global _registry, FUNCTION_MAP, FUNCTION_SCHEMAS
    if _registry is None:
        _registry = FunctionRegistry()
        # 同步全局变量
        FUNCTION_MAP.update(_registry._function_map)
        FUNCTION_SCHEMAS.extend(_registry._function_schemas)
    return _registry


def get_function_schemas() -> List[FunctionSchema]:
    """获取全部函数描述（模块级快捷方法）"""
    return get_registry().get_function_schemas()


async def call_function(intent: str, entities: Dict[str, Any]) -> str:
    """按意图名称调用函数（模块级快捷方法）"""
    return await get_registry().call_function(intent, entities)
