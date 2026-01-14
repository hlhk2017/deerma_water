"""Button entities for Deerma Water Purifier."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
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
    """Set up Deerma Water Purifier button entities."""
    coordinator: DeermaWaterCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        DeermaQuick55Button(coordinator, entry),
    ]

    async_add_entities(entities)


class DeermaBaseButton(CoordinatorEntity, ButtonEntity):
    """Base class for Deerma button entities."""

    def __init__(
        self,
        coordinator: DeermaWaterCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the button entity."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id or "unknown")},
            name=coordinator.device_name or "飞利浦水健康",
            manufacturer="Deerma",
            model="Water Purifier",
        )


class DeermaQuick55Button(DeermaBaseButton):
    """Button for quick setting 55°C water temperature."""

    _attr_unique_id = "deerma_quick_55"
    _attr_name = "一键55度"
    _attr_icon = "mdi:thermometer-water"

    def __init__(
        self,
        coordinator: DeermaWaterCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the quick 55°C button."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{coordinator.device_id}_quick_55"

    async def async_press(self) -> None:
        """Handle the button press."""
        # 55度对应代码 "6" (根据 valueMapping: "6": "55℃")
        success = await self.coordinator.async_set_temperature("6")
        if success:
            _LOGGER.info("已通过按钮设置水温为55度")
        else:
            _LOGGER.error("通过按钮设置55度水温失败")
