"""API client for Deerma Water Purifier."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

import aiohttp
import requests

from .const import API_BASE_URL, API_SESSION, API_CAPTCHA, API_DEVICE_LIST, API_DEVICE_STATUS, APP_ID

_LOGGER = logging.getLogger(__name__)


class DeermaAPIClient:
    """Client for Deerma API."""

    def __init__(self, phone: str, password: str = None, captcha: str = None, login_type: str = "password") -> None:
        """Initialize the API client.
        
        Args:
            phone: Phone number
            password: Password (for password login)
            captcha: Captcha code (for captcha login)
            login_type: "password" or "captcha"
        """
        self.phone = phone
        self.password = password
        self.captcha = captcha
        self.login_type = login_type  # "password" or "captcha"
        self.token: str | None = None
        self.user_id: str | None = None
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()

    def login_sync(self) -> dict[str, Any]:
        """Synchronous login method (for use with executor)."""
        # Format phone number - ensure it has country code
        phone = self.phone.strip().replace(" ", "").replace("-", "")
        
        # Handle different phone number formats
        if phone.startswith("+86"):
            # Already has country code
            pass
        elif phone.startswith("86") and len(phone) > 2:
            # Has country code without +
            phone = "+" + phone
        elif phone.startswith("1") and len(phone) == 11:
            # Chinese mobile number (11 digits starting with 1)
            phone = "+86" + phone
        elif phone.startswith("0"):
            # Remove leading 0 and add country code
            phone = "+86" + phone.lstrip("0")
        else:
            # Assume it's a Chinese number, add country code
            phone = "+86" + phone
        
        _LOGGER.debug("Formatted phone number: %s (original: %s)", phone, self.phone)
        
        # Prepare login data based on HAR file analysis
        # For password login: {"account":"+8618963907553","language":"zh-CN","pin":"flp2025","registrationId":"140fe1da9f81611e292","system":"android","verify":"password"}
        # For captcha login: {"account":"+8618963907553","language":"zh-CN","pin":"861838","registrationId":"140fe1da9f81611e292","system":"android","verify":"captcha"}
        if self.login_type == "captcha":
            if not self.captcha:
                raise Exception("验证码登录需要提供验证码")
            pin = self.captcha
            verify = "captcha"
        else:
            if not self.password:
                raise Exception("密码登录需要提供密码")
            pin = self.password
            verify = "password"
        
        login_data = {
            "account": phone,
            "language": "zh-CN",
            "pin": pin,
            "registrationId": "140fe1da9f81611e292",
            "system": "android",
            "verify": verify
        }
        
        headers = {
            "app_id": APP_ID,
            "accept-language": "zh-CN",
            "content-type": "application/json; charset=UTF-8",
            "user-agent": "okhttp/4.12.0",
        }
        
        _LOGGER.debug("Login request - phone: %s, type: %s, data: %s", phone, self.login_type, {**login_data, "pin": "***"})  # Hide password/captcha in log
        
        try:
            # Based on actual API, send JSON directly (not base64 encoded)
            response = requests.post(
                f"{API_BASE_URL}{API_SESSION}",
                headers=headers,
                json=login_data,  # Send as JSON directly
                timeout=10,
            )
            
            result = {}
            
            _LOGGER.debug("Login response status: %s, headers: %s, body: %s", 
                         response.status_code, dict(response.headers), response.text[:500])
            
            # Parse response
            try:
                result = response.json()
            except:
                # If response is not JSON, it might be base64 encoded
                try:
                    decoded = base64.b64decode(response.text).decode("utf-8")
                    result = json.loads(decoded)
                except:
                    result = {"message": response.text, "raw": response.text}
            
            # Parse response - based on actual API response structure
            if result.get("code") == 0 or result.get("success"):
                # Access token is in data.accessToken
                data = result.get("data", {})
                access_token = data.get("accessToken")
                refresh_token = data.get("refreshToken")
                user_id = data.get("userID")
                
                if not access_token:
                    # Try alternative: maybe the response itself is the token
                    if isinstance(result, str):
                        access_token = result
                    elif "data" in result and isinstance(result["data"], str):
                        access_token = result["data"]
                
                if access_token:
                    self.token = access_token
                    self.user_id = user_id
                    return {
                        "access_token": access_token,
                        "refresh_token": refresh_token,
                        "user_id": user_id,
                        "raw": result,
                    }
                else:
                    _LOGGER.error("Login response: %s", result)
                    raise Exception(f"Login failed: No token in response. Response: {result.get('message', 'Unknown error')}")
            else:
                error_msg = result.get("message") or result.get("msg") or result.get("error") or "Unknown error"
                _LOGGER.error("Login failed: %s, Response: %s", error_msg, result)
                raise Exception(f"Login failed: {error_msg}")
        except requests.RequestException as err:
            _LOGGER.error("Error during login: %s", err)
            raise
        except Exception as err:
            _LOGGER.error("Unexpected error during login: %s", err)
            raise

    def get_devices_sync(self) -> list[dict[str, Any]]:
        """Synchronous method to get device list."""
        if not self.token:
            self.login_sync()
        
        headers = {
            "app_id": APP_ID,
            "accept-language": "zh-CN",
            "authorization": f"Bearer {self.token}",
            "user-agent": "okhttp/4.12.0",
        }
        
        try:
            response = requests.get(
                f"{API_BASE_URL}{API_DEVICE_LIST}",
                headers=headers,
                timeout=10,
            )
            response.raise_for_status()
            result = response.json()
            
            _LOGGER.debug("Get devices response: code=%s, success=%s, data type=%s", 
                         result.get("code"), result.get("success"), type(result.get("data")))
            
            if result.get("code") == 0 or result.get("success"):
                # Based on actual API response, devices are in data[0].devices
                data = result.get("data", [])
                devices = []
                if data and isinstance(data, list):
                    for room_data in data:
                        room_devices = room_data.get("devices", [])
                        if room_devices:
                            devices.extend(room_devices)
                            _LOGGER.debug("Found %d devices in room", len(room_devices))
                
                _LOGGER.debug("Total devices found: %d", len(devices))
                if devices:
                    _LOGGER.debug("First device: %s", devices[0].get("device", {}).get("id", "unknown"))
                
                return devices
            else:
                error_msg = result.get("message") or "Unknown error"
                _LOGGER.warning("Failed to get devices: code=%s, message=%s, full response: %s", 
                               result.get("code"), error_msg, result)
                return []
        except requests.RequestException as err:
            _LOGGER.error("Error getting devices: %s", err)
            return []

    async def login(self) -> dict[str, Any]:
        """Login and get session token (async version)."""
        # Use sync version via executor to ensure consistency
        return await asyncio.get_event_loop().run_in_executor(None, self.login_sync)

    async def get_devices(self) -> list[dict[str, Any]]:
        """Get list of devices."""
        if not self.token:
            await self.login()
        
        session = await self._get_session()
        headers = {
            "app_id": APP_ID,
            "accept-language": "zh-CN",
            "authorization": f"Bearer {self.token}",
            "user-agent": "okhttp/4.12.0",
        }
        
        try:
            async with session.get(
                f"{API_BASE_URL}{API_DEVICE_LIST}",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                response.raise_for_status()
                result = await response.json()
                
                if result.get("code") == 0 or result.get("success"):
                    # Based on actual API response, devices are in data[0].devices
                    data = result.get("data", [])
                    devices = []
                    if data and isinstance(data, list):
                        for room_data in data:
                            room_devices = room_data.get("devices", [])
                            if room_devices:
                                devices.extend(room_devices)
                    return devices
                else:
                    _LOGGER.warning("Failed to get devices: %s", result.get("message"))
                    return []
        except aiohttp.ClientError as err:
            _LOGGER.error("Error getting devices: %s", err)
            return []

    async def get_device_status(self, device_id: str) -> dict[str, Any]:
        """Get device status."""
        if not self.token:
            await self.login()
        
        session = await self._get_session()
        headers = {
            "app_id": APP_ID,
            "accept-language": "zh-CN",
            "authorization": f"Bearer {self.token}",
            "user-agent": "okhttp/4.12.0",
        }
        
        try:
            async with session.get(
                f"{API_BASE_URL}{API_DEVICE_STATUS}",
                headers=headers,
                params={"device_id": device_id},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                response.raise_for_status()
                result = await response.json()
                
                if result.get("code") == 0 or result.get("success"):
                    return result.get("data", {}) or result
                else:
                    _LOGGER.warning("Failed to get device status: %s", result.get("message"))
                    return {}
        except aiohttp.ClientError as err:
            _LOGGER.error("Error getting device status: %s", err)
            return {}

    async def get_water_data(self, device_id: str) -> dict[str, Any]:
        """Get water usage data (total, daily, weekly, monthly)."""
        if not self.token:
            await self.login()
        
        session = await self._get_session()
        headers = {
            "app_id": APP_ID,
            "accept-language": "zh-CN",
            "authorization": f"Bearer {self.token}",
            "user-agent": "okhttp/4.12.0",
        }
        
        try:
            # Get total water data
            async with session.get(
                f"{API_BASE_URL}/api/app/devices/{device_id}/totalWater?product_type=WaterPurifier",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as total_response:
                total_response.raise_for_status()
                total_data = await total_response.json()
            
            # Get daily data
            async with session.get(
                f"{API_BASE_URL}/api/app/devices/{device_id}/water/?product_type=WaterPurifier&period=day&s_type=water",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as daily_response:
                daily_response.raise_for_status()
                daily_data = await daily_response.json()
            
            # Get weekly data
            async with session.get(
                f"{API_BASE_URL}/api/app/devices/{device_id}/water/?product_type=WaterPurifier&period=week&s_type=water",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as weekly_response:
                weekly_response.raise_for_status()
                weekly_data = await weekly_response.json()
            
            # Get monthly data
            async with session.get(
                f"{API_BASE_URL}/api/app/devices/{device_id}/water/?product_type=WaterPurifier&period=month&s_type=water",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as monthly_response:
                monthly_response.raise_for_status()
                monthly_data = await monthly_response.json()
            
            return {
                "total": total_data.get("data", {}),
                "daily": daily_data.get("data", []),
                "weekly": weekly_data.get("data", []),
                "monthly": monthly_data.get("data", [])
            }
        except aiohttp.ClientError as err:
            _LOGGER.error("Error getting water data: %s", err)
            return {
                "total": {},
                "daily": [],
                "weekly": [],
                "monthly": []
            }

    def request_captcha_sync(self) -> bool:
        """Request captcha code (synchronous version)."""
        phone = self.phone.strip().replace(" ", "").replace("-", "")
        
        # Format phone number
        if phone.startswith("+86"):
            pass
        elif phone.startswith("86") and len(phone) > 2:
            phone = "+" + phone
        elif phone.startswith("1") and len(phone) == 11:
            phone = "+86" + phone
        elif phone.startswith("0"):
            phone = "+86" + phone.lstrip("0")
        else:
            phone = "+86" + phone
        
        captcha_data = {
            "account": phone,
            "accountType": "mobile",
            "areaCode": "+86",
            "captchaType": "login"
        }
        
        headers = {
            "app_id": APP_ID,
            "accept-language": "zh-CN",
            "content-type": "application/json; charset=UTF-8",
            "user-agent": "okhttp/4.12.0",
        }
        
        try:
            response = requests.post(
                f"{API_BASE_URL}{API_CAPTCHA}",
                headers=headers,
                json=captcha_data,
                timeout=10,
            )
            
            result = response.json()
            
            if result.get("code") == 0 or result.get("success"):
                _LOGGER.info("验证码已发送到 %s", phone)
                return True
            else:
                error_msg = result.get("message") or "Unknown error"
                _LOGGER.error("请求验证码失败: %s", error_msg)
                raise Exception(f"请求验证码失败: {error_msg}")
        except requests.RequestException as err:
            _LOGGER.error("请求验证码时出错: %s", err)
            raise

    async def request_captcha(self) -> bool:
        """Request captcha code (async version)."""
        return await asyncio.get_event_loop().run_in_executor(None, self.request_captcha_sync)

    async def get_mqtt_config(self, device_id: str) -> dict[str, Any]:
        """Get MQTT connection configuration for device."""
        if not self.token:
            await self.login()
        
        session = await self._get_session()
        headers = {
            "app_id": APP_ID,
            "accept-language": "zh-CN",
            "authorization": f"Bearer {self.token}",
            "user-agent": "okhttp/4.12.0",
        }
        
        try:
            async with session.get(
                f"{API_BASE_URL}/api/app/devices/{device_id}/mqtt",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                response.raise_for_status()
                result = await response.json()
                
                if result.get("code") == 0 or result.get("success"):
                    return result.get("data", {})
                else:
                    _LOGGER.warning("Failed to get MQTT config: %s", result.get("message"))
                    return {}
        except aiohttp.ClientError as err:
            _LOGGER.error("Error getting MQTT config: %s", err)
            return {}
