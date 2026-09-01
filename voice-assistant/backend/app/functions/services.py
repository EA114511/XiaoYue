"""
功能调用模块
实现天气查询、设备控制、信息查询等功能
"""

from typing import Dict, Any, Optional

from app.functions.weather import get_weather as fetch_real_weather
from app.functions.device import device_manager


class WeatherService:
    """天气查询服务（委托 weather.py 的真实 API 调用）"""

    async def get_current_weather(self, city: str) -> Dict[str, Any]:
        """获取当前天气（联网查询 + 5 分钟缓存）"""
        result = await fetch_real_weather(city)
        return result


class DeviceControlService:
    """设备控制服务（委托 device.py 的完整 DeviceManager）"""

    async def control(self, device_id: str, action: str, parameters: Dict = None) -> Dict[str, Any]:
        """控制设备"""
        params = parameters or {}

        if action == "turn_on":
            success = device_manager.turn_on(device_id)
        elif action == "turn_off":
            success = device_manager.turn_off(device_id)
        elif action == "set_temperature":
            value = params.get("temperature", 26)
            success = device_manager.set_value(device_id, value)
        elif action == "set_value":
            value = params.get("value", 0)
            success = device_manager.set_value(device_id, value)
        else:
            return {"success": False, "message": f"不支持的操作: {action}"}

        if not success:
            return {"success": False, "message": f"设备 {device_id} 不存在"}

        device = device_manager.get_device(device_id)
        return {
            "success": True,
            "message": f"{device['name'] if device else device_id} 已执行 {action} 操作",
            "device_status": device,
        }

    async def get_device_status(self, device_id: str) -> Optional[Dict[str, Any]]:
        """获取设备状态"""
        return device_manager.get_device(device_id)


class FunctionService:
    """功能服务总入口"""

    def __init__(self):
        self.weather = WeatherService()
        self.devices = DeviceControlService()

    async def execute(self, function_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """执行功能调用"""
        if function_name == "get_weather":
            city = parameters.get("city", "北京")
            return await self.weather.get_current_weather(city)

        elif function_name == "control_device":
            device_id = parameters.get("device_id")
            action = parameters.get("action")
            params = parameters.get("parameters", {})
            return await self.devices.control(device_id, action, params)

        else:
            return {
                "success": False,
                "message": f"不支持的功能: {function_name}"
            }
