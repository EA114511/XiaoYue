"""
设备控制模块 (Device Control)

提供智能家居设备的统一控制接口，支持：
  - 5 种设备类型：灯、空调、电视、窗帘、风扇
  - 操作：打开、关闭、调节（温度/音量/亮度/风速）
  - 模拟控制（预留 MQTT / HTTP 真实调用接口）
  - 设备状态持久化管理
  - 批量操作（如"关闭所有灯"）
  - 按位置（客厅/卧室/厨房）过滤设备
"""

import copy
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("voice-assistant.device")

# ============================================================
# 类型定义
# ============================================================


class DeviceType(str, Enum):
    """设备类型枚举"""

    LIGHT = "light"           # 灯 / 灯光
    AC = "air_conditioner"    # 空调
    TV = "tv"                 # 电视
    CURTAIN = "curtain"       # 窗帘
    FAN = "fan"               # 风扇


class DeviceAction(str, Enum):
    """设备操作枚举"""

    TURN_ON = "turn_on"       # 打开
    TURN_OFF = "turn_off"     # 关闭
    SET_TEMP = "set_temperature"     # 调节温度（空调）
    SET_VOLUME = "set_volume"        # 调节音量（电视）
    SET_BRIGHTNESS = "set_brightness"  # 调节亮度（灯）
    SET_SPEED = "set_speed"          # 调节风速（风扇）


# ============================================================
# 设备状态模型
# ============================================================


@dataclass
class DeviceState:
    """单个设备的完整状态"""

    device_id: str
    name: str                     # 显示名，如"客厅灯"
    device_type: DeviceType       # 设备类型
    location: str = ""            # 位置：客厅/卧室/厨房/书房/阳台
    status: str = "off"           # on / off
    temperature: int = 26         # 空调目标温度 (°C)
    volume: int = 30              # 电视音量 (0-100)
    brightness: int = 80          # 灯光亮度 (0-100)
    speed: int = 3                # 风扇风速 (1-5)
    curtain_position: str = "closed"  # 窗帘状态: open / closed
    last_updated: str = ""        # 最后更新时间

    def __post_init__(self):
        if not self.last_updated:
            self.last_updated = datetime.now().strftime("%H:%M:%S")

    def to_dict(self) -> Dict[str, Any]:
        """转为字典"""
        return asdict(self)


# ============================================================
# MQTT / HTTP 回调接口（预留）
# ============================================================


class MqttCallback:
    """MQTT 消息发送接口（预留，需外部注入）

    用法:
        DeviceManager.mqtt = MyMqttClient()
        await DeviceManager.mqtt.publish("home/light_1/command", '{"action": "turn_on"}')
    """

    async def publish(self, topic: str, payload: str):
        """向 MQTT Broker 发布消息"""
        logger.debug(f"[MQTT] 预留接口: topic={topic}, payload={payload}")
        # TODO: 接入真实 MQTT 客户端
        # import paho.mqtt.client as mqtt
        # client.publish(topic, payload)
        pass


class HttpCallback:
    """HTTP API 调用接口（预留，需外部注入）

    用法:
        DeviceManager.http = MyHttpClient()
        await DeviceManager.http.post("http://192.168.1.100/api/device/control", json={...})
    """

    async def post(self, url: str, json: Dict[str, Any]):
        """发送 HTTP POST 请求"""
        logger.debug(f"[HTTP] 预留接口: url={url}, json={json}")
        # TODO: 接入真实 HTTP API
        # async with httpx.AsyncClient() as client:
        #     await client.post(url, json=json)
        pass


# ============================================================
# 设备管理器
# ============================================================


class DeviceManager:
    """
    设备管理器

    维护所有设备的当前状态，提供设备控制、查询和批量操作接口。
    默认使用模拟控制模式，可切换为 MQTT / HTTP 真实控制。

    用法:
        mgr = DeviceManager()

        # 单设备控制
        result = await mgr.control("灯", "打开", location="客厅")

        # 批量控制
        result = await mgr.control("灯", "关闭", batch=True)

        # 调节
        result = await mgr.control("空调", "调节", params={"temperature": 24})
    """

    # 类级别回调（可全局注入）
    mqtt: Optional[MqttCallback] = None
    http: Optional[HttpCallback] = None

    def __init__(self):
        # ---------- 设备清单 ----------
        # device_id: {name, type, location, ...}
        self._device_config: Dict[str, Dict[str, Any]] = {
            # 灯
            "light_1":  {"name": "客厅灯",   "type": DeviceType.LIGHT, "location": "客厅"},
            "light_2":  {"name": "卧室灯",   "type": DeviceType.LIGHT, "location": "卧室"},
            "light_3":  {"name": "厨房灯",   "type": DeviceType.LIGHT, "location": "厨房"},
            "light_4":  {"name": "阳台灯",   "type": DeviceType.LIGHT, "location": "阳台"},
            # 空调
            "ac_1":     {"name": "客厅空调", "type": DeviceType.AC,    "location": "客厅"},
            "ac_2":     {"name": "卧室空调", "type": DeviceType.AC,    "location": "卧室"},
            # 电视
            "tv_1":     {"name": "客厅电视", "type": DeviceType.TV,    "location": "客厅"},
            "tv_2":     {"name": "卧室电视", "type": DeviceType.TV,    "location": "卧室"},
            # 窗帘
            "curtain_1":{"name": "客厅窗帘", "type": DeviceType.CURTAIN, "location": "客厅"},
            "curtain_2":{"name": "卧室窗帘", "type": DeviceType.CURTAIN, "location": "卧室"},
            # 风扇
            "fan_1":    {"name": "客厅风扇", "type": DeviceType.FAN,   "location": "客厅"},
            "fan_2":    {"name": "卧室风扇", "type": DeviceType.FAN,   "location": "卧室"},
        }

        # ---------- 设备当前状态 ----------
        self._states: Dict[str, DeviceState] = {}
        for dev_id, cfg in self._device_config.items():
            self._states[dev_id] = DeviceState(
                device_id=dev_id,
                name=cfg["name"],
                device_type=cfg["type"],
                location=cfg.get("location", ""),
            )

        # ---------- 名称索引 ----------
        self._name_index: Dict[str, List[str]] = {}
        self._rebuild_index()

    def _rebuild_index(self):
        """重建名称 → device_id 索引（支持模糊匹配）"""
        self._name_index.clear()
        for dev_id, cfg in self._device_config.items():
            name = cfg["name"]
            self._name_index.setdefault(name, []).append(dev_id)
            # 类型名
            t = cfg["type"].value
            if t == "light":
                self._name_index.setdefault("灯", []).append(dev_id)
                self._name_index.setdefault("灯光", []).append(dev_id)
            elif t == "air_conditioner":
                self._name_index.setdefault("空调", []).append(dev_id)
            elif t == "tv":
                self._name_index.setdefault("电视", []).append(dev_id)
            elif t == "curtain":
                self._name_index.setdefault("窗帘", []).append(dev_id)
            elif t == "fan":
                self._name_index.setdefault("风扇", []).append(dev_id)

    # ============================================================
    # 公共属性
    # ============================================================

    @property
    def all_devices(self) -> List[DeviceState]:
        """所有设备状态"""
        return list(self._states.values())

    @property
    def device_count(self) -> int:
        """设备总数"""
        return len(self._states)

    def get_device(self, device_id: str) -> Optional[DeviceState]:
        """获取指定设备的状态"""
        return self._states.get(device_id)

    def get_devices_by_location(self, location: str) -> List[DeviceState]:
        """按位置（如"客厅"）获取设备列表"""
        return [
            s for s in self._states.values()
            if s.location == location
        ]

    def get_devices_by_type(self, device_type: str) -> List[DeviceState]:
        """按类型（如"light"）获取设备列表"""
        return [
            s for s in self._states.values()
            if s.device_type.value == device_type
        ]

    def get_device_summary(self) -> str:
        """返回所有设备状态的摘要文本"""
        on_count = sum(1 for s in self._states.values() if s.status == "on")
        return f"共 {len(self._states)} 台设备，其中 {on_count} 台已开启"

    # ============================================================
    # 核心控制方法
    # ============================================================

    async def control(
        self,
        device_name: str,
        action: str,
        location: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        batch: bool = False,
    ) -> Dict[str, Any]:
        """
        控制设备

        参数:
            device_name: 设备名，如 "灯"、"空调"、"客厅灯"、"电视"
            action:      操作，如 "打开" / "关闭" / "调节"
            location:    位置过滤，如 "客厅"（可选）
            params:      调节参数，如 {"temperature": 24, "volume": 50}
            batch:       是否批量操作（True = 匹配所有设备）

        返回:
            {
                "success": bool,
                "message": str,              # 语音播报用
                "affected": int,             # 影响的设备数
                "devices": [DeviceState],    # 变更后的设备列表
                "details": [str],            # 每台设备的详细结果
            }
        """
        # ---- 1. 设备匹配 ----
        target_ids = self._resolve_devices(device_name, location, batch)
        if not target_ids:
            msg = f"未找到{location or ''}{device_name}"
            if location:
                msg = f"{location}未找到{device_name}"
            return {
                "success": False,
                "message": msg,
                "affected": 0,
                "devices": [],
                "details": [],
            }

        # ---- 2. 动作映射 ----
        action_id = self._map_action(action, device_name)
        if action_id is None:
            return {
                "success": False,
                "message": f"不支持的操作：{action}",
                "affected": 0,
                "devices": [],
                "details": [],
            }

        # ---- 3. 逐个执行 ----
        details: List[str] = []
        changed_states: List[DeviceState] = []

        for dev_id in target_ids:
            result = await self._apply_action(dev_id, action_id, params or {})
            details.append(result["message"])
            changed_states.append(result["state"])

        # ---- 4. 回调通知（预留）----
        await self._notify(target_ids, action_id, params)

        # ---- 5. 汇总消息 ----
        success_count = sum(1 for d in details if "失败" not in d)
        if len(target_ids) == 1:
            summary_msg = details[0]
        else:
            summary_msg = f"已{'成功' if success_count > 0 else '尝试'}{action}{len(target_ids)}台{device_name}"

        return {
            "success": success_count > 0,
            "message": summary_msg,
            "affected": len(target_ids),
            "devices": changed_states,
            "details": details,
        }

    # ============================================================
    # 内部方法
    # ============================================================

    def _resolve_devices(
        self,
        device_name: str,
        location: Optional[str] = None,
        batch: bool = False,
    ) -> List[str]:
        """解析设备名 → 匹配的 device_id 列表"""
        candidates: List[str] = []

        # 1) 精确名称匹配
        if device_name in self._name_index:
            candidates = list(self._name_index[device_name])
        else:
            # 2) 模糊匹配（名称包含关键字）
            for dev_id, cfg in self._device_config.items():
                if device_name in cfg["name"] or device_name in cfg["type"].value:
                    candidates.append(dev_id)

        if not candidates:
            return []

        # 3) 按位置过滤
        if location:
            candidates = [
                d for d in candidates
                if self._states[d].location == location
            ]

        # 4) 非批量模式 → 只取第一个
        if not batch and len(candidates) > 1:
            # 如果用户指定了具体名称（如"客厅灯"），取精确匹配
            exact = [
                d for d in candidates
                if self._device_config[d]["name"] == device_name
            ]
            if exact:
                candidates = exact[:1]
            else:
                candidates = candidates[:1]

        return candidates

    @staticmethod
    def _map_action(action: str, device_name: str) -> Optional[str]:
        """中文操作 → 内部 action_id"""
        mapping = {
            "打开": DeviceAction.TURN_ON.value,
            "开": DeviceAction.TURN_ON.value,
            "开启": DeviceAction.TURN_ON.value,
            "关闭": DeviceAction.TURN_OFF.value,
            "关": DeviceAction.TURN_OFF.value,
            "关闭": DeviceAction.TURN_OFF.value,
            "调节": None,  # 由 _apply_action 根据设备类型决定
            "调整": None,
            "设置": None,
        }
        return mapping.get(action)

    async def _apply_action(
        self, device_id: str, action_id: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """对单台设备执行操作"""
        state = self._states[device_id]
        cfg = self._device_config[device_id]

        # ---- 如果 action 是"调节"，根据设备类型推断 ----
        if action_id is None:
            return await self._apply_adjust(state, cfg, params)

        # ---- 打开 / 关闭 ----
        if action_id == DeviceAction.TURN_ON.value:
            if state.status == "on":
                return {
                    "message": f"{state.name}已经是开启状态",
                    "state": copy.deepcopy(state),
                }
            state.status = "on"
            # 窗帘特殊处理
            if state.device_type == DeviceType.CURTAIN:
                state.curtain_position = "open"
            state.last_updated = datetime.now().strftime("%H:%M:%S")
            return {
                "message": f"{state.name}已打开",
                "state": copy.deepcopy(state),
            }

        if action_id == DeviceAction.TURN_OFF.value:
            if state.status == "off":
                return {
                    "message": f"{state.name}已经是关闭状态",
                    "state": copy.deepcopy(state),
                }
            state.status = "off"
            if state.device_type == DeviceType.CURTAIN:
                state.curtain_position = "closed"
            state.last_updated = datetime.now().strftime("%H:%M:%S")
            return {
                "message": f"{state.name}已关闭",
                "state": copy.deepcopy(state),
            }

        return {
            "message": f"不支持的操作：{action_id}",
            "state": copy.deepcopy(state),
        }

    async def _apply_adjust(
        self, state: DeviceState, cfg: Dict[str, Any], params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """调节设备参数"""
        dtype = state.device_type

        # 空调 → 调温度
        if dtype == DeviceType.AC:
            temp = params.get("temperature", params.get("temp", 26))
            try:
                temp = max(16, min(30, int(temp)))
            except (ValueError, TypeError):
                temp = 26
            state.temperature = temp
            state.status = "on"  # 调节时自动开启
            state.last_updated = datetime.now().strftime("%H:%M:%S")
            return {
                "message": f"{state.name}温度已设为{temp}°C",
                "state": copy.deepcopy(state),
            }

        # 电视 → 调音量
        if dtype == DeviceType.TV:
            vol = params.get("volume", params.get("音量", 30))
            try:
                vol = max(0, min(100, int(vol)))
            except (ValueError, TypeError):
                vol = 30
            state.volume = vol
            state.status = "on"
            state.last_updated = datetime.now().strftime("%H:%M:%S")
            return {
                "message": f"{state.name}音量已设为{vol}",
                "state": copy.deepcopy(state),
            }

        # 灯 → 调亮度
        if dtype == DeviceType.LIGHT:
            bri = params.get("brightness", params.get("亮度", params.get("brightness", 80)))
            try:
                bri = max(1, min(100, int(bri)))
            except (ValueError, TypeError):
                bri = 80
            state.brightness = bri
            state.status = "on"
            state.last_updated = datetime.now().strftime("%H:%M:%S")
            return {
                "message": f"{state.name}亮度已设为{bri}%",
                "state": copy.deepcopy(state),
            }

        # 风扇 → 调风速
        if dtype == DeviceType.FAN:
            spd = params.get("speed", params.get("风速", params.get("speed", 3)))
            try:
                spd = max(1, min(5, int(spd)))
            except (ValueError, TypeError):
                spd = 3
            state.speed = spd
            state.status = "on"
            state.last_updated = datetime.now().strftime("%H:%M:%S")
            return {
                "message": f"{state.name}风速已设为{spd}档",
                "state": copy.deepcopy(state),
            }

        return {
            "message": f"{state.name}不支持调节操作",
            "state": copy.deepcopy(state),
        }

    async def _notify(
        self, device_ids: List[str], action: str, params: Dict[str, Any]
    ):
        """通过 MQTT / HTTP 通知外部（预留）"""
        for dev_id in device_ids:
            payload = {
                "device_id": dev_id,
                "action": action,
                "params": params,
                "timestamp": datetime.now().isoformat(),
            }
            # MQTT
            if self.__class__.mqtt is not None:
                topic = f"home/{dev_id}/command"
                await self.__class__.mqtt.publish(topic, str(payload))
            # HTTP
            if self.__class__.http is not None:
                url = f"http://device-api/{dev_id}/control"
                await self.__class__.http.post(url, payload)

    # ============================================================
    # 查询接口
    # ============================================================

    def query(self, device_name: str, location: Optional[str] = None) -> List[DeviceState]:
        """查询设备状态"""
        ids = self._resolve_devices(device_name, location, batch=True)
        return [copy.deepcopy(self._states[d]) for d in ids]

    def format_status(self, device_name: str, location: Optional[str] = None) -> str:
        """格式化设备状态为语音播报文本"""
        devices = self.query(device_name, location)
        if not devices:
            return f"未找到{location or ''}{device_name}"

        parts = []
        for d in devices:
            if d.device_type == DeviceType.LIGHT:
                parts.append(f"{d.name}：{'已开启' if d.status == 'on' else '已关闭'}，亮度{d.brightness}%")
            elif d.device_type == DeviceType.AC:
                parts.append(f"{d.name}：{'已开启' if d.status == 'on' else '已关闭'}，设定温度{d.temperature}°C")
            elif d.device_type == DeviceType.TV:
                parts.append(f"{d.name}：{'已开启' if d.status == 'on' else '已关闭'}，音量{d.volume}")
            elif d.device_type == DeviceType.CURTAIN:
                pos = "已打开" if d.curtain_position == "open" else "已关闭"
                parts.append(f"{d.name}：{pos}")
            elif d.device_type == DeviceType.FAN:
                parts.append(f"{d.name}：{'已开启' if d.status == 'on' else '已关闭'}，风速{d.speed}档")
            else:
                parts.append(f"{d.name}：{'已开启' if d.status == 'on' else '已关闭'}")

        return "；".join(parts)


# ============================================================
# 全局单例 & 便捷函数
# ============================================================

_manager: Optional[DeviceManager] = None


def get_manager() -> DeviceManager:
    """获取 DeviceManager 全局单例"""
    global _manager
    if _manager is None:
        _manager = DeviceManager()
    return _manager


async def control_device(
    device: str,
    action: str,
    location: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
    batch: bool = False,
) -> Dict[str, Any]:
    """
    控制设备的便捷入口

    参数:
        device:   设备名（"灯" / "空调" / "电视" / "窗帘" / "风扇" / "客厅灯"）
        action:   操作（"打开" / "关闭" / "调节"）
        location: 位置（"客厅" / "卧室" / "厨房"，可选）
        params:   调节参数（{"temperature": 24, "volume": 50, "亮度": 60}）
        batch:    是否批量（True = 控制所有匹配设备）

    返回:
        {"success": bool, "message": str, "affected": int, ...}

    用法:
        await control_device("灯", "打开")
        await control_device("灯", "关闭", batch=True)           # 关所有灯
        await control_device("空调", "调节", params={"温度": 24})
        await control_device("风扇", "打开", location="客厅")
    """
    mgr = get_manager()
    return await mgr.control(device, action, location, params, batch)


def query_device(
    device: str,
    location: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """查询设备状态（返回列表）"""
    mgr = get_manager()
    return [s.to_dict() for s in mgr.query(device, location)]


def get_device_status_text(device: str, location: Optional[str] = None) -> str:
    """获取设备状态的语音播报文本"""
    mgr = get_manager()
    return mgr.format_status(device, location)


# 全局设备管理器实例（供 services.py 和 endpoints.py 使用）
device_manager = DeviceManager()
