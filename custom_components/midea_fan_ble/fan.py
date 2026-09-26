"""Fan platform for Midea BLE fans."""

from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.percentage import (
    percentage_to_ranged_value,
    ranged_value_to_percentage,
)
from homeassistant.util.scaling import int_states_in_range

from .coordinator import MideaFanConfigEntry
from .entity import MideaFanEntity
from .protocol.fa import HORIZONTAL_ANGLES, MSFS07_MODES

SPEED_RANGE = (1, 12)
MODE_BY_NAME = {name: number for number, name in MSFS07_MODES.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MideaFanConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the fan entity."""
    async_add_entities([MideaFan(entry.runtime_data)])


class MideaFan(MideaFanEntity, FanEntity):
    """The fan itself."""

    _attr_name = None
    _attr_translation_key = "fan"
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.OSCILLATE
        | FanEntityFeature.PRESET_MODE
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )
    _attr_speed_count = int_states_in_range(SPEED_RANGE)

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "fan")
        self._attr_preset_modes = list(MODE_BY_NAME)
        self._last_horizontal = HORIZONTAL_ANGLES[-1]

    @property
    def is_on(self) -> bool:
        """Return whether the fan is on."""
        return self.coordinator.data.power

    @property
    def percentage(self) -> int | None:
        """Return the speed as a percentage."""
        status = self.coordinator.data
        if not status.power or not status.speed:
            return 0
        return ranged_value_to_percentage(SPEED_RANGE, status.speed)

    @property
    def preset_mode(self) -> str | None:
        """Return the active preset."""
        return self.coordinator.data.mode_name

    @property
    def oscillating(self) -> bool:
        """Return whether either axis oscillates."""
        return self.coordinator.data.oscillate

    @callback
    def _handle_coordinator_update(self) -> None:
        if angle := self.coordinator.data.horizontal_angle:
            self._last_horizontal = angle
        super()._handle_coordinator_update()

    @staticmethod
    def _speed(percentage: int) -> int:
        return max(1, round(percentage_to_ranged_value(SPEED_RANGE, percentage)))

    async def async_turn_on(
        self, percentage: int | None = None, preset_mode: str | None = None, **kwargs: Any
    ) -> None:
        """Turn on, optionally with a speed or preset."""
        fields: dict[str, Any] = {"power": True}
        if preset_mode is not None:
            fields = {"mode": MODE_BY_NAME[preset_mode]}
        if percentage:
            fields["speed"] = self._speed(percentage)
        await self.coordinator.async_set(**fields)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the fan off."""
        await self.coordinator.async_set(power=False)

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed; 0 turns the fan off."""
        if percentage == 0:
            await self.async_turn_off()
            return
        await self.coordinator.async_set(power=True, speed=self._speed(percentage))

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Switch to a preset mode."""
        await self.coordinator.async_set(mode=MODE_BY_NAME[preset_mode])

    async def async_oscillate(self, oscillating: bool) -> None:
        """Oscillate horizontally, or stop both axes."""
        if oscillating:
            await self.coordinator.async_set(horizontal_angle=self._last_horizontal)
        else:
            await self.coordinator.async_set(horizontal_angle=0, vertical_angle=0)
