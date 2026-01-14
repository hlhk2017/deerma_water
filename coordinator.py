"""Data update coordinator for Deerma Water Purifier."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api_client import DeermaAPIClient
from .mqtt_client import DeermaMQTTClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=30)


class DeermaWaterCoordinator(DataUpdateCoordinator):
    """Coordinator for Deerma Water Purifier data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.entry = entry
        login_type = entry.data.get("login_type", "password")
        if login_type == "captcha":
            self.api_client = DeermaAPIClient(
                entry.data["phone"],
                login_type="captcha"
            )
        else:
            self.api_client = DeermaAPIClient(
                entry.data["phone"],
                password=entry.data.get("password"),
                login_type="password"
            )
        # Set token and user_id from config if available
        if "access_token" in entry.data:
            self.api_client.token = entry.data["access_token"]
        if "user_id" in entry.data:
            self.api_client.user_id = entry.data["user_id"]
        self.mqtt_client: DeermaMQTTClient | None = None
        self.device_id: str | None = entry.data.get("device_id")
        self.device_name: str | None = None
        
        # Initialize device from config
        devices = entry.data.get("devices", [])
        if devices and len(devices) > 0:
            device_info = devices[0].get("device", {})
            if not self.device_id:
                self.device_id = device_info.get("id") or devices[0].get("device_id") or devices[0].get("id")
            self.device_name = devices[0].get("deviceNickname") or devices[0].get("name") or "飞利浦水健康"

    async def _async_update_data(self) -> dict:
        """Fetch data from API."""
        try:
            if not self.device_id:
                return self.data or {}  # Return existing data if no device_id
            
            # Preserve existing MQTT data if available
            existing_data = self.data or {}
            mqtt_data = {k: v for k, v in existing_data.items() 
                        if k not in ["water_data", "device_id"]}  # Keep MQTT data
            
            # Get water data (total, daily, weekly, monthly) like previous version
            water_data = await self.api_client.get_water_data(self.device_id)
            
            # Also get device status for real-time data
            status = await self.api_client.get_device_status(self.device_id)
            
            # Merge: MQTT data (most recent) takes priority, then API status, then water_data
            return {
                "water_data": water_data,
                "device_id": self.device_id,
                **status,  # Merge status data
                **mqtt_data,  # Merge MQTT data (overwrites status if same keys)
            }
        except Exception as err:
            # On error, return existing data to preserve state
            if self.data:
                _LOGGER.warning("Error updating data, preserving existing data: %s", err)
                return self.data
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    async def async_config_entry_first_refresh(self) -> None:
        """Refresh data for the first time."""
        # Only login if we don't have a token
        if not self.api_client.token:
            _LOGGER.debug("No token found, logging in...")
            await self.api_client.login()
        await super().async_config_entry_first_refresh()
        
        # Setup MQTT if device_id is available
        if self.device_id:
            await self._setup_mqtt()

    async def _setup_mqtt(self) -> None:
        """Setup MQTT client for real-time updates."""
        if not self.device_id:
            _LOGGER.warning("Cannot setup MQTT: device_id is not available")
            return
        
        try:
            _LOGGER.info("Setting up MQTT client for device: %s", self.device_id)
            mqtt_config = {
                "access_token": self.entry.data.get("access_token"),
                "device_id": self.device_id
            }
            self.mqtt_client = DeermaMQTTClient(
                hass=self.hass,
                device_id=self.device_id or "",
                callback=self._mqtt_callback,
                mqtt_config=mqtt_config,
                config_entry=self.entry,
            )
            # Use async_connect method (like previous version)
            success = await self.mqtt_client.async_connect()
            if success:
                _LOGGER.info("MQTT client connected successfully")
            else:
                _LOGGER.error("MQTT client connection failed")
                self.mqtt_client = None
        except Exception as err:
            _LOGGER.error("Failed to setup MQTT: %s", err, exc_info=True)
            self.mqtt_client = None

    def _mqtt_callback(self, payload: dict) -> None:
        """Handle MQTT message callback."""
        # Merge MQTT payload with existing data to preserve API data (like water_data)
        current_data = self.data or {}
        merged_data = {
            **current_data,  # Keep existing data (water_data, etc.)
            **payload,  # Update with MQTT data (overwrites if same keys)
        }
        # Update coordinator data with merged payload
        self.async_set_updated_data(merged_data)

    async def async_set_temperature(self, temp_code: str) -> bool:
        """Set temperature setting via MQTT."""
        if not self.device_id or not self.mqtt_client:
            _LOGGER.warning("MQTT client not available, cannot set temperature")
            return False
        return await self.mqtt_client.async_set_temperature(temp_code)

    async def async_set_water_volume(self, volume_code: str) -> bool:
        """Set water volume setting via MQTT."""
        if not self.device_id or not self.mqtt_client:
            _LOGGER.warning("MQTT client not available, cannot set water volume")
            return False
        return await self.mqtt_client.async_set_volume(volume_code)

    async def async_shutdown(self) -> None:
        """Shutdown coordinator."""
        if self.mqtt_client:
            await self.mqtt_client.disconnect()
        await self.api_client.close()
