"""Base entity for Midea BLE fans."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MideaFanCoordinator


class MideaFanEntity(CoordinatorEntity[MideaFanCoordinator]):
    """Common device info and unique ID."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MideaFanCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.serial}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.serial)},
            connections={(CONNECTION_BLUETOOTH, coordinator.address)},
            manufacturer="Midea",
            name=coordinator.config_entry.title,
            serial_number=coordinator.serial,
        )
