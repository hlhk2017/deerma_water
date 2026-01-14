"""MQTT client for Deerma Water Purifier using WebSocket."""
from __future__ import annotations

import asyncio
import json
import logging
import socket
import time
from typing import Any, Callable, Optional

import websockets
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)


class DeermaMQTTClient:
    """MQTT client for Deerma devices using AWS IoT WebSocket."""

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        callback: Callable[[dict[str, Any]], None],
        mqtt_config: Optional[dict] = None,
        config_entry: Optional[Any] = None,
    ) -> None:
        """Initialize MQTT client."""
        self.hass = hass
        self.device_id = device_id
        self.callback = callback
        self.mqtt_config = mqtt_config or {}
        self.config_entry = config_entry
        self._websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.connected = False
        self._connect_lock = asyncio.Lock()
        self._listen_task: Optional[asyncio.Task] = None
        self._listening = False
        self._session = async_get_clientsession(hass)
        
        # MQTT主题配置（基于AWS IoT Shadow）
        self.command_topic = f"$aws/things/{device_id}/shadow/update"
        self.state_topic = f"$aws/things/{device_id}/shadow/get/accepted"
        self.response_topic = f"$aws/things/{device_id}/shadow/update/accepted"
        self.get_topic = f"$aws/things/{device_id}/shadow/get"

    def _get_latest_access_token(self) -> Optional[str]:
        """从配置项中获取最新的 access_token"""
        if self.config_entry:
            latest_token = self.config_entry.data.get("access_token")
            if latest_token:
                return latest_token
        return self.mqtt_config.get("access_token")

    async def _get_mqtt_config_from_api(self) -> dict:
        """从API获取MQTT配置"""
        access_token = self._get_latest_access_token()
        if not access_token:
            _LOGGER.warning("缺少 access token，无法获取 MQTT 配置")
            return {}
        
        url = f"https://iot.deerma.com/api/app/devices/{self.device_id}/mqtt"
        headers = {
            "app_id": "9c3b124649fa11e98b6e02461a5b364e",
            "authorization": f"Bearer {access_token}",
            "accept-language": "zh-CN",
            "user-agent": "okhttp/4.12.0"
        }
        
        try:
            _LOGGER.debug("请求MQTT配置: %s", url)
            async with self._session.get(url, headers=headers, timeout=15) as response:
                data = await response.json()
                
                if response.status == 401 or data.get("code") == 401:
                    _LOGGER.warning("Token 已过期，尝试从配置项重新读取")
                    latest_token = self._get_latest_access_token()
                    if latest_token and latest_token != access_token:
                        headers["authorization"] = f"Bearer {latest_token}"
                        async with self._session.get(url, headers=headers, timeout=15) as retry_response:
                            retry_data = await retry_response.json()
                            if retry_response.status == 200 and retry_data.get("code") == 0 and retry_data.get("data"):
                                return retry_data["data"]
                
                if response.status != 200 or data.get("code") != 0:
                    _LOGGER.error("获取MQTT配置失败: status=%s, code=%s, message=%s", 
                                response.status, data.get("code"), data.get("message"))
                    return {}
                
                if not data.get("data"):
                    _LOGGER.error("MQTT配置返回成功但数据为空")
                    return {}
                
                config = data["data"]
                _LOGGER.info("获取到MQTT配置: endpoint=%s, clientID=%s", 
                            config.get("endpoint"), config.get("clientID"))
                return config
        except Exception as err:
            _LOGGER.error("获取MQTT配置时发生错误: %s", err)
            return {}

    def _encode_mqtt_remaining_length(self, length: int) -> bytes:
        """编码 MQTT 剩余长度（支持多字节编码）"""
        encoded = bytearray()
        while True:
            byte = length % 128
            length = length // 128
            if length > 0:
                byte = byte | 0x80
            encoded.append(byte)
            if length == 0:
                break
        return bytes(encoded)

    def _build_mqtt_connect_packet(self, client_id: str) -> bytes:
        """构建 MQTT CONNECT 数据包"""
        client_id_bytes = client_id.encode("utf-8")
        protocol_name = b"MQTT"
        remaining_length = 2 + len(protocol_name) + 1 + 1 + 2 + 2 + len(client_id_bytes)
        remaining_length_bytes = self._encode_mqtt_remaining_length(remaining_length)
        fixed_header = bytes([0x10]) + remaining_length_bytes
        
        protocol_name_length = bytes([len(protocol_name) >> 8, len(protocol_name) & 0xFF])
        protocol_level = bytes([0x04])  # MQTT 3.1.1
        connect_flags = bytes([0x02])   # 清理会话
        keep_alive = bytes([0x00, 0x3C])  # 60秒
        
        client_id_length = bytes([len(client_id_bytes) >> 8, len(client_id_bytes) & 0xFF])
        
        packet = (
            fixed_header
            + protocol_name_length
            + protocol_name
            + protocol_level
            + connect_flags
            + keep_alive
            + client_id_length
            + client_id_bytes
        )
        return packet

    def _build_mqtt_subscribe_packet(self, topic: str, packet_id: int = 1) -> bytes:
        """构建 MQTT SUBSCRIBE 数据包"""
        topic_bytes = topic.encode("utf-8")
        remaining_length = 2 + 2 + len(topic_bytes) + 1
        remaining_length_bytes = self._encode_mqtt_remaining_length(remaining_length)
        fixed_header = bytes([0x82]) + remaining_length_bytes  # SUBSCRIBE + QoS 1
        
        packet_id_bytes = bytes([packet_id >> 8, packet_id & 0xFF])
        topic_length = bytes([len(topic_bytes) >> 8, len(topic_bytes) & 0xFF])
        qos = bytes([0x01])  # QoS 1
        
        packet = (
            fixed_header
            + packet_id_bytes
            + topic_length
            + topic_bytes
            + qos
        )
        return packet

    def _build_mqtt_publish_packet(self, topic: str, payload: dict, packet_id: int = 2) -> bytes:
        """构建 MQTT PUBLISH 数据包（QoS 1）"""
        payload_str = json.dumps(payload, separators=(',', ':'))
        payload_bytes = payload_str.encode("utf-8")
        topic_bytes = topic.encode("utf-8")
        
        remaining_length = 2 + len(topic_bytes) + 2 + len(payload_bytes)
        remaining_length_bytes = self._encode_mqtt_remaining_length(remaining_length)
        fixed_header = bytes([0x32]) + remaining_length_bytes  # PUBLISH + QoS 1
        
        topic_length = bytes([len(topic_bytes) >> 8, len(topic_bytes) & 0xFF])
        packet_id_bytes = bytes([packet_id >> 8, packet_id & 0xFF])
        
        packet = (
            fixed_header
            + topic_length
            + topic_bytes
            + packet_id_bytes
            + payload_bytes
        )
        return packet

    def _parse_mqtt_remaining_length(self, packet: bytes, start_pos: int) -> tuple:
        """解析 MQTT 剩余长度，返回 (剩余长度, 下一个位置)"""
        pos = start_pos
        remaining_length = 0
        multiplier = 1
        while pos < len(packet) and pos < start_pos + 4:
            byte = packet[pos]
            remaining_length += (byte & 0x7F) * multiplier
            multiplier *= 128
            pos += 1
            if (byte & 0x80) == 0:
                break
        return remaining_length, pos

    def _parse_mqtt_publish_packet(self, packet: bytes) -> tuple:
        """解析 MQTT PUBLISH 数据包，返回 (topic, payload)"""
        if len(packet) < 4:
            return None, None
        
        remaining_length, pos = self._parse_mqtt_remaining_length(packet, 1)
        
        if pos + 2 > len(packet) or remaining_length == 0:
            return None, None
        
        topic_length = (packet[pos] << 8) | packet[pos + 1]
        pos += 2
        
        if pos + topic_length > len(packet):
            return None, None
        
        topic = packet[pos:pos + topic_length].decode("utf-8", errors="ignore")
        pos += topic_length
        
        qos = (packet[0] & 0x06) >> 1
        if qos >= 1:
            if pos + 2 > len(packet):
                return None, None
            pos += 2
        
        payload_length = remaining_length - 2 - topic_length - (2 if qos >= 1 else 0)
        if payload_length < 0 or pos + payload_length > len(packet):
            payload_bytes = packet[pos:]
        else:
            payload_bytes = packet[pos:pos + payload_length]
        
        return topic, payload_bytes

    def _handle_mqtt_packet(self, packet: bytes):
        """处理 MQTT 数据包"""
        if len(packet) < 2:
            return
        
        packet_type = (packet[0] & 0xF0) >> 4
        
        if packet_type == 0x02:  # CONNACK
            if len(packet) >= 4:
                connack_code = packet[3]
                if connack_code == 0:
                    _LOGGER.info("MQTT 连接已确认")
                else:
                    _LOGGER.error("MQTT 连接失败，CONNACK 代码: 0x%02X", connack_code)
        elif packet_type == 0x09:  # SUBACK
            _LOGGER.debug("MQTT 订阅成功")
        elif packet_type == 0x03:  # PUBLISH
            topic, payload_bytes = self._parse_mqtt_publish_packet(packet)
            if topic and payload_bytes:
                _LOGGER.debug("收到 PUBLISH 消息，主题: %s", topic)
                
                if "/shadow/get/accepted" in topic or "/shadow/update/accepted" in topic:
                    try:
                        payload_str = payload_bytes.decode("utf-8")
                        payload_data = json.loads(payload_str)
                        
                        # Handle both /shadow/get/accepted and /shadow/update/accepted
                        # /shadow/get/accepted has reported state
                        # /shadow/update/accepted may have reported state after device accepts desired state
                        state = payload_data.get("state", {})
                        reported = state.get("reported", {})
                        
                        if reported:
                            _LOGGER.debug("设备状态更新 (reported): %s", reported)
                            self.callback(reported)
                        elif "desired" in state:
                            # If only desired state, wait for reported state update
                            _LOGGER.debug("收到 desired 状态，等待 reported 状态更新")
                    except Exception as err:
                        _LOGGER.error("解析 PUBLISH payload 失败: %s", err)

    async def _listen_messages(self):
        """监听 WebSocket 消息"""
        if not self._websocket or not self.connected:
            return
        
        if self._listening:
            return
        
        self._listening = True
        try:
            while self.connected and self._websocket:
                try:
                    message = await self._websocket.recv()
                    
                    if isinstance(message, bytes):
                        self._handle_mqtt_packet(message)
                except websockets.exceptions.ConnectionClosedOK:
                    _LOGGER.info("WebSocket 连接正常关闭")
                    break
                except websockets.exceptions.ConnectionClosedError as e:
                    _LOGGER.warning("WebSocket 连接异常关闭: %s", e)
                    break
                except Exception as err:
                    _LOGGER.error("接收 WebSocket 消息出错: %s", err)
                    await asyncio.sleep(1)
        except Exception as err:
            _LOGGER.error("监听 WebSocket 消息时出错: %s", err)
        finally:
            self._listening = False
            self.connected = False
            # 自动重连
            for delay in [5, 10, 15, 30]:
                if not self.connected:
                    _LOGGER.info("尝试重连 WebSocket，延迟 %s 秒", delay)
                    await asyncio.sleep(delay)
                    if await self.connect():
                        break

    async def connect(self) -> bool:
        """连接 MQTT broker via WebSocket"""
        if self.connected:
            _LOGGER.debug("MQTT already connected")
            return True
        
        async with self._connect_lock:
            if self.connected:
                return True
            
            try:
                _LOGGER.info("开始连接MQTT WebSocket，device_id=%s", self.device_id)
                
                mqtt_config = await self._get_mqtt_config_from_api()
                if not mqtt_config:
                    _LOGGER.error("无法获取MQTT配置")
                    return False
                
                wss_url = mqtt_config.get("host")
                if not wss_url:
                    _LOGGER.error("未获取到有效的 WSS 连接地址")
                    return False
                
                client_id = mqtt_config.get("clientID") or self.device_id
                _LOGGER.debug("使用 WSS URL: %s, clientID: %s", wss_url[:50] + "...", client_id)
                
                # 建立 WebSocket 连接
                import ssl
                def _create_ssl_context():
                    return ssl.create_default_context()
                
                ssl_context = await self.hass.async_add_executor_job(_create_ssl_context)
                
                self._websocket = await websockets.connect(
                    wss_url,
                    subprotocols=["mqtt"],
                    open_timeout=30,
                    close_timeout=10,
                    ping_interval=None,
                    ping_timeout=None,
                    ssl=ssl_context
                )
                
                self.connected = True
                _LOGGER.info("WebSocket 连接成功")
                
                # 发送 MQTT CONNECT 包
                connect_packet = self._build_mqtt_connect_packet(client_id)
                await self._websocket.send(connect_packet)
                _LOGGER.debug("已发送 MQTT CONNECT 包")
                
                # 等待连接确认
                await asyncio.sleep(0.5)
                
                # 订阅主题
                subscribe_topics = [
                    f"$aws/things/{self.device_id}/shadow/get/#",
                    f"$aws/things/{self.device_id}/shadow/update/accepted"
                ]
                for i, topic in enumerate(subscribe_topics, 1):
                    subscribe_packet = self._build_mqtt_subscribe_packet(topic, packet_id=i)
                    await self._websocket.send(subscribe_packet)
                    _LOGGER.debug("已订阅主题: %s", topic)
                
                # 启动消息监听任务
                if self._listen_task and not self._listen_task.done():
                    try:
                        self._listen_task.cancel()
                    except Exception:
                        pass
                
                self._listen_task = self.hass.async_create_task(self._listen_messages())
                
                # 请求当前设备状态
                await self._request_device_state()
                
                return True
                
            except Exception as err:
                _LOGGER.error("WebSocket 连接失败: %s", err, exc_info=True)
                self.connected = False
                if self._websocket:
                    try:
                        await self._websocket.close()
                    except Exception:
                        pass
                    self._websocket = None
                return False

    async def async_connect(self) -> bool:
        """Connect to MQTT broker (async version, compatible with previous version)."""
        return await self.connect()

    async def _request_device_state(self) -> None:
        """请求设备当前状态"""
        if not self.connected or not self._websocket:
            return
        
        try:
            get_packet = self._build_mqtt_publish_packet(self.get_topic, {}, packet_id=3)
            await self._websocket.send(get_packet)
            _LOGGER.debug("已请求设备状态")
        except Exception as err:
            _LOGGER.error("请求设备状态失败: %s", err)

    async def async_set_temperature(self, temp_code: str) -> bool:
        """设置水温"""
        if not await self._ensure_connected():
            return False
        
        try:
            temp_mapping = {
                "0": 0, "1": 1, "2": 2, "3": 3, "4": 4,
                "5": 5, "6": 6, "7": 7, "8": 8, "9": 9, "10": 10
            }
            
            target_temp = temp_mapping.get(temp_code, 0)
            
            # From WebSocket data analysis, the payload format should be simpler
            # Only include necessary fields
            payload = {
                "state": {
                    "desired": {
                        "SetTemp": target_temp,
                        "CommandType": "app",
                        "EnduserId": self.device_id
                    }
                }
            }
            
            publish_packet = self._build_mqtt_publish_packet(self.command_topic, payload, packet_id=4)
            await self._websocket.send(publish_packet)
            
            _LOGGER.info("已发送水温设置指令: code=%s, temp=%s", temp_code, target_temp)
            return True
            
        except Exception as err:
            _LOGGER.error("设置水温失败: %s", err)
            return False

    async def async_set_volume(self, volume_code: str) -> bool:
        """设置出水量"""
        if not await self._ensure_connected():
            return False
        
        try:
            # SetOutlet 的值直接就是代码值，不需要转换
            # 从 WebSocket 数据看，SetOutlet 的值直接对应 valueMapping 的 key
            target_volume = int(volume_code)
            
            # From WebSocket data analysis, the payload format should be simpler
            # Only include necessary fields
            payload = {
                "state": {
                    "desired": {
                        "SetOutlet": target_volume,
                        "CommandType": "app",
                        "EnduserId": self.device_id
                    }
                }
            }
            
            publish_packet = self._build_mqtt_publish_packet(self.command_topic, payload, packet_id=5)
            await self._websocket.send(publish_packet)
            
            _LOGGER.info("已发送出水量设置指令: code=%s, SetOutlet=%s", volume_code, target_volume)
            return True
            
        except Exception as err:
            _LOGGER.error("设置出水量失败: %s", err)
            return False

    async def _ensure_connected(self) -> bool:
        """确保MQTT连接"""
        if not self.connected:
            try:
                await self.connect()
            except Exception as err:
                _LOGGER.error("无法建立MQTT连接: %s", err)
                return False
        return self.connected

    async def async_disconnect(self) -> None:
        """Disconnect from MQTT broker (async version, compatible with previous version)."""
        await self.disconnect()

    async def disconnect(self) -> None:
        """断开MQTT连接"""
        self.connected = False
        self._listening = False
        
        if self._listen_task and not self._listen_task.done():
            try:
                self._listen_task.cancel()
            except Exception:
                pass
        
        if self._websocket:
            try:
                disconnect_packet = bytes([0xE0, 0x00])  # DISCONNECT 包
                await self._websocket.send(disconnect_packet)
                await self._websocket.close()
                _LOGGER.info("WebSocket MQTT 连接已断开")
            except Exception as err:
                _LOGGER.error("断开 WebSocket 连接时出错: %s", err)
        
        self._websocket = None
