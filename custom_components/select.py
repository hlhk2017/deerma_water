"""Select entities for Deerma Water Purifier."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DeermaWaterCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Deerma Water Purifier select entities."""
    coordinator: DeermaWaterCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        DeermaTemperatureSelect(coordinator, entry),
        DeermaWaterVolumeSelect(coordinator, entry),
    ]

    async_add_entities(entities)


class DeermaBaseSelect(CoordinatorEntity, SelectEntity):
    """Base class for Deerma select entities."""

    def __init__(
        self,
        coordinator: DeermaWaterCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id or "unknown")},
            name=coordinator.device_name or "飞利浦水健康",
            manufacturer="Deerma",
            model="Water Purifier",
        )


class DeermaTemperatureSelect(DeermaBaseSelect):
    """Select entity for water temperature."""

    _attr_unique_id = "deerma_water_temperature"
    _attr_name = "Water Temperature"
    _attr_icon = "mdi:thermometer"

    def __init__(
        self,
        coordinator: DeermaWaterCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the temperature select."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{coordinator.device_id}_temperature"
        self._attr_name = "水温设置"
        
        # Get temperature mapping from device config
        devices = entry.data.get("devices", [])
        temp_mapping = {}
        if devices and len(devices) > 0:
            show_attrs = devices[0].get("showAttributes", [])
            for attr in show_attrs:
                if attr.get("id") == "SetTemp":
                    value_mapping = attr.get("valueMapping", {})
                    # Build options list and reverse mapping
                    options = []
                    for code, value in value_mapping.items():
                        if isinstance(value, dict):
                            # Handle localized values like {"zh-CN": "常温", "en": "Normal"}
                            display_value = value.get("zh-CN") or value.get("en") or str(value)
                        else:
                            display_value = str(value)
                        options.append(display_value)
                        temp_mapping[display_value] = code
                    self._attr_options = sorted(set(options), key=lambda x: (
                        float(x.replace("℃", "").replace("°C", "").replace("常温", "0"))
                        if x.replace("℃", "").replace("°C", "").replace("常温", "0").replace(".", "").isdigit()
                        else 999
                    ))
                    self._temp_mapping = temp_mapping
                    break
        
        # Fallback to default mapping if not found
        if not hasattr(self, '_temp_mapping'):
            self._temp_mapping = {
                "常温": "0",
                "45℃": "1",
                "65℃": "2",
                "85°C": "3",
                "99℃": "4",
                "5℃": "5",
                "55℃": "6",
                "75℃": "7",
                "95℃": "8",
                "97℃": "9",
                "100℃": "10"
            }
            self._attr_options = list(self._temp_mapping.keys())

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        data = self.coordinator.data or {}
        # Get current temperature from MQTT data (SetTemp from shadow reported state)
        # MQTT callback already extracts reported state, so data should contain SetTemp directly
        temp_code = (
            data.get("SetTemp")  # From MQTT shadow reported state
            or data.get("setTemp")
            or data.get("temperature_code")
        )
        if temp_code is not None:
            # Find option by code
            temp_code_str = str(temp_code)
            for option, code in self._temp_mapping.items():
                if str(code) == temp_code_str:
                    _LOGGER.debug("SetTemp=%s -> code=%s -> option=%s", temp_code, temp_code_str, option)
                    return option
            
            _LOGGER.warning("无法找到 SetTemp=%s 对应的选项，映射表: %s", temp_code, self._temp_mapping)
        
        # Default to first option
        default_option = self._attr_options[0] if self._attr_options else "常温"
        _LOGGER.debug("使用默认选项: %s", default_option)
        return default_option

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        # Get code from mapping
        temp_code = self._temp_mapping.get(option)
        if not temp_code:
            _LOGGER.error("Unknown temperature option: %s", option)
            return
        
        success = await self.coordinator.async_set_temperature(temp_code)
        if success:
            # Update local state immediately
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to set temperature to %s", option)


class DeermaWaterVolumeSelect(DeermaBaseSelect):
    """Select entity for water volume."""

    _attr_unique_id = "deerma_water_volume"
    _attr_name = "Water Volume"
    _attr_icon = "mdi:cup-water"

    def __init__(
        self,
        coordinator: DeermaWaterCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the water volume select."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{coordinator.device_id}_water_volume"
        self._attr_name = "出水量设置"
        
        # Get volume mapping from device config
        devices = entry.data.get("devices", [])
        volume_mapping = {}
        if devices and len(devices) > 0:
            show_attrs = devices[0].get("showAttributes", [])
            for attr in show_attrs:
                if attr.get("id") == "SetOutlet":
                    value_mapping = attr.get("valueMapping", {})
                    # Build options list and reverse mapping
                    options = []
                    for code, value in value_mapping.items():
                        display_value = str(value)
                        options.append(display_value)
                        volume_mapping[display_value] = code
                    self._attr_options = sorted(set(options), key=lambda x: (
                        float(x.replace("mL", "").replace("ml", ""))
                        if x.replace("mL", "").replace("ml", "").isdigit()
                        else 999
                    ))
                    self._volume_mapping = volume_mapping
                    break
        
        # Fallback to default mapping if not found
        if not hasattr(self, '_volume_mapping'):
            self._volume_mapping = {
                "200mL": "0",
                "500mL": "1",
                "1000mL": "2",
                "1500mL": "3",
                "250mL": "4",
                "350mL": "5",
                "2000mL": "6"
            }
            self._attr_options = list(self._volume_mapping.keys())

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        data = self.coordinator.data or {}
        # Get current volume from MQTT data (SetOutlet from shadow reported state)
        # MQTT callback already extracts reported state, so data should contain SetOutlet directly
        volume_code = (
            data.get("SetOutlet")  # From MQTT shadow reported state
            or data.get("setOutlet")
            or data.get("volume_code")
        )
        if volume_code is not None:
            # From WebSocket data analysis: SetOutlet value directly corresponds to code in valueMapping
            # SetOutlet=2 -> code "2" -> "1000mL"
            # SetOutlet=4 -> code "4" -> "250mL"
            # SetOutlet=5 -> code "5" -> "350mL"
            # No conversion needed, SetOutlet value IS the code
            code_str = str(int(volume_code)) if isinstance(volume_code, (int, float)) else str(volume_code)
            
            # Find option by code
            for option, code in self._volume_mapping.items():
                if str(code) == code_str:
                    _LOGGER.debug("SetOutlet=%s -> code=%s -> option=%s", volume_code, code_str, option)
                    return option
            
            _LOGGER.warning("无法找到 SetOutlet=%s (code=%s) 对应的选项，映射表: %s", 
                          volume_code, code_str, self._volume_mapping)
        
        # Default to first option
        default_option = self._attr_options[0] if self._attr_options else "200mL"
        _LOGGER.debug("使用默认选项: %s", default_option)
        return default_option

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        # Get code from mapping
        volume_code = self._volume_mapping.get(option)
        if not volume_code:
            _LOGGER.error("Unknown volume option: %s", option)
            return
        
        success = await self.coordinator.async_set_water_volume(volume_code)
        if success:
            # Update local state immediately
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to set water volume to %s", option)
