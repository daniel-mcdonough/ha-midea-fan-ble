"""Temperature sensor for Midea BLE fans."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MideaFanConfigEntry
from .entity import MideaFanEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MideaFanConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([TemperatureSensor(entry.runtime_data, "temperature")])


class TemperatureSensor(MideaFanEntity, SensorEntity):
    """Room temperature measured by the fan."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.temperature
