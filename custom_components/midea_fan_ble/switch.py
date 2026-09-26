"""Display and buzzer switches for Midea BLE fans."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MideaFanConfigEntry
from .entity import MideaFanEntity


@dataclass(frozen=True, kw_only=True)
class FanSwitchDescription(SwitchEntityDescription):
    field: str


SWITCHES = (
    FanSwitchDescription(
        key="display", translation_key="display", field="display", entity_category=EntityCategory.CONFIG
    ),
    FanSwitchDescription(
        key="buzzer", translation_key="buzzer", field="buzzer", entity_category=EntityCategory.CONFIG
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MideaFanConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(FanSwitch(entry.runtime_data, d) for d in SWITCHES)


class FanSwitch(MideaFanEntity, SwitchEntity):
    """A boolean fan setting."""

    entity_description: FanSwitchDescription

    def __init__(self, coordinator, description: FanSwitchDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        return getattr(self.coordinator.data, self.entity_description.field)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set(**{self.entity_description.field: True})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set(**{self.entity_description.field: False})
