"""Sensor entities for Deerma Water Purifier."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import UnitOfVolume

from .const import (
    DOMAIN,
    ATTR_TOTAL_WATER,
    ATTR_TAP_WATER_TDS,
    ATTR_PURIFIED_TDS,
    ATTR_AQP_FILTER_LIFE,
    ATTR_PC5IN1_FILTER_LIFE,
    ATTR_AVG_TDS,
)
from .coordinator import DeermaWaterCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Deerma Water Purifier sensor entities."""
    coordinator: DeermaWaterCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        DeermaTotalWaterSensor(coordinator, entry),
        DeermaTapWaterTDSSensor(coordinator, entry),
        DeermaPurifiedTDSSensor(coordinator, entry),
        DeermaAQPFilterLifeSensor(coordinator, entry),
        DeermaPC5IN1FilterLifeSensor(coordinator, entry),
    ]

    async_add_entities(entities)


class DeermaBaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for Deerma sensor entities."""

    def __init__(
        self,
        coordinator: DeermaWaterCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor entity."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._entry = entry
        self._last_value = None  # Store last valid value
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id or "unknown")},
            name=coordinator.device_name or "飞利浦水健康",
            manufacturer="Deerma",
            model="Water Purifier",
        )


class DeermaTotalWaterSensor(DeermaBaseSensor):
    """Sensor for total water consumption."""

    _attr_unique_id = "deerma_total_water"
    _attr_name = "总用水量"
    _attr_native_unit_of_measurement = UnitOfVolume.LITERS
    _attr_icon = "mdi:water"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self,
        coordinator: DeermaWaterCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the total water sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{coordinator.device_id}_total_water"

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        data = self.coordinator.data or {}
        # Use API data for total water consumption
        # WaterVolume from MQTT is not the total water consumption
        water_data = data.get("water_data", {})
        total_data = water_data.get("total", {})
        total_water = total_data.get("totalWater", 0.0)
        
        if total_water is not None:
            try:
                value = float(total_water)
                self._last_value = value  # Update last valid value
                return value
            except (ValueError, TypeError):
                pass
        
        # Return last valid value if current value is None
        return self._last_value if hasattr(self, '_last_value') else 0.0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        data = self.coordinator.data or {}
        water_data = data.get("water_data", {})
        total_data = water_data.get("total", {})
        
        return {
            ATTR_TOTAL_WATER: total_data.get("totalWater", 0.0),
            ATTR_AVG_TDS: total_data.get("averageTds", 0.0),
            "daily_data": water_data.get("daily", []),
            "weekly_data": water_data.get("weekly", []),
            "monthly_data": water_data.get("monthly", []),
        }


class DeermaTapWaterTDSSensor(DeermaBaseSensor):
    """Sensor for tap water TDS value."""

    _attr_unique_id = "deerma_tap_water_tds"
    _attr_name = "自来水TDS"
    _attr_native_unit_of_measurement = "ppm"
    _attr_icon = "mdi:water-check"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: DeermaWaterCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the tap water TDS sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{coordinator.device_id}_tap_water_tds"

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        data = self.coordinator.data or {}
        # Try MQTT data first (TapWaterTDS from shadow reported state)
        tds = (
            data.get("TapWaterTDS")  # From MQTT shadow
            or data.get("TapWaterTds")
            or data.get("tapWaterTds")
            or data.get("tap_water_tds")
            or data.get("input_tds")
            or data.get("inputTds")
        )
        if tds is not None:
            try:
                value = float(tds)
                self._last_value = value  # Update last valid value
                return value
            except (ValueError, TypeError):
                pass
        # Return last valid value if current value is None
        return self._last_value


class DeermaPurifiedTDSSensor(DeermaBaseSensor):
    """Sensor for purified water TDS value."""

    _attr_unique_id = "deerma_purified_tds"
    _attr_name = "净水TDS"
    _attr_native_unit_of_measurement = "ppm"
    _attr_icon = "mdi:water-check-outline"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: DeermaWaterCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the purified TDS sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{coordinator.device_id}_purified_tds"

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        data = self.coordinator.data or {}
        # Try MQTT data first (TDS from shadow reported state)
        tds = (
            data.get("TDS")  # From MQTT shadow
            or data.get("Tds")
            or data.get("tds")
            or data.get("purified_tds")
            or data.get("purifiedTds")
            or data.get("output_tds")
            or data.get("outputTds")
        )
        if tds is not None:
            try:
                value = float(tds)
                self._last_value = value  # Update last valid value
                return value
            except (ValueError, TypeError):
                pass
        # Return last valid value if current value is None
        return self._last_value


class DeermaAQPFilterLifeSensor(DeermaBaseSensor):
    """Sensor for AQP filter life."""

    _attr_unique_id = "deerma_aqp_filter_life"
    _attr_name = "AQP滤芯寿命"
    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:filter"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: DeermaWaterCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the AQP filter life sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{coordinator.device_id}_aqp_filter_life"

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        data = self.coordinator.data or {}
        # Try MQTT data first (AQPLife from shadow reported state)
        life = (
            data.get("AQPLife")  # From MQTT shadow
            or data.get("AqpFilterLife")
            or data.get("aqpFilterLife")
            or data.get("aqp_filter_life")
            or data.get("filter1_life")
            or data.get("filter1Life")
        )
        if life is not None:
            try:
                value = float(life)
                self._last_value = value  # Update last valid value
                return value
            except (ValueError, TypeError):
                pass
        # Return last valid value if current value is None
        return self._last_value


class DeermaPC5IN1FilterLifeSensor(DeermaBaseSensor):
    """Sensor for PC5IN1 filter life."""

    _attr_unique_id = "deerma_pc5in1_filter_life"
    _attr_name = "PC5IN1滤芯寿命"
    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:filter-variant"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: DeermaWaterCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the PC5IN1 filter life sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{coordinator.device_id}_pc5in1_filter_life"

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        data = self.coordinator.data or {}
        # Try MQTT data first (PC5in1Life from shadow reported state - note the case)
        life = (
            data.get("PC5in1Life")  # From MQTT shadow (actual field name)
            or data.get("PC5IN1Life")  # Alternative case
            or data.get("Pc5in1FilterLife")
            or data.get("pc5in1FilterLife")
            or data.get("pc5in1_filter_life")
            or data.get("filter2_life")
            or data.get("filter2Life")
        )
        if life is not None:
            try:
                value = float(life)
                self._last_value = value  # Update last valid value
                return value
            except (ValueError, TypeError):
                pass
        # Return last valid value if current value is None
        return self._last_value
