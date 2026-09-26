"""Oscillation angle selects for Midea BLE fans."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MideaFanConfigEntry
from .entity import MideaFanEntity
from .protocol.fa import HORIZONTAL_ANGLES, VERTICAL_ANGLES, FanStatus

OFF = "off"


@dataclass(frozen=True, kw_only=True)
class AngleSelectDescription(SelectEntityDescription):
    """Describes an oscillation-angle select."""

    field: str
    angles: tuple[int, ...]


SELECTS = (
    AngleSelectDescription(
        key="horizontal_oscillation",
        translation_key="horizontal_oscillation",
        field="horizontal_angle",
        angles=HORIZONTAL_ANGLES,
        options=[OFF, *map(str, HORIZONTAL_ANGLES)],
    ),
    AngleSelectDescription(
        key="vertical_oscillation",
        translation_key="vertical_oscillation",
        field="vertical_angle",
        angles=VERTICAL_ANGLES,
        options=[OFF, *map(str, VERTICAL_ANGLES)],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MideaFanConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the oscillation selects."""
    async_add_entities(AngleSelect(entry.runtime_data, d) for d in SELECTS)


class AngleSelect(MideaFanEntity, SelectEntity):
    """Oscillation angle for one axis; "off" stops that axis."""

    entity_description: AngleSelectDescription

    def __init__(self, coordinator, description: AngleSelectDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def current_option(self) -> str | None:
        """Return the axis angle, or off."""
        status: FanStatus = self.coordinator.data
        if not status.power:
            return None
        angle = getattr(status, self.entity_description.field)
        return str(angle) if angle else OFF

    async def async_select_option(self, option: str) -> None:
        """Set the axis angle, or stop it."""
        angle = 0 if option == OFF else int(option)
        await self.coordinator.async_set(**{self.entity_description.field: angle})
