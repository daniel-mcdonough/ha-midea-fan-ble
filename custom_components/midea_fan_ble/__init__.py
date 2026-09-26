"""Local Bluetooth control of Midea fans.

Home Assistant imports stay inside functions so that ``protocol`` and
``client`` can be used without Home Assistant installed (tools and tests).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import MideaFanConfigEntry

PLATFORMS = ["fan", "select", "sensor", "switch"]


async def async_setup_entry(hass: HomeAssistant, entry: MideaFanConfigEntry) -> bool:
    """Set up a Midea fan from a config entry."""
    from homeassistant.components import bluetooth
    from homeassistant.const import CONF_ADDRESS
    from homeassistant.exceptions import ConfigEntryNotReady

    from .const import DOMAIN
    from .coordinator import MideaFanCoordinator

    address: str = entry.data[CONF_ADDRESS]
    if not bluetooth.async_ble_device_from_address(hass, address, connectable=True):
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="device_not_found",
            translation_placeholders={"address": address},
        )
    coordinator = MideaFanCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MideaFanConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.client.disconnect()
    return unload_ok
