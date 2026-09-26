"""Data coordinator for a Midea BLE fan."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from bleak import BleakClient
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import MideaFanClient
from .const import CONF_SERIAL, DOMAIN, IDLE_TIMEOUT, UPDATE_INTERVAL
from .protocol.advertisement import build_advertis_data
from .protocol.exceptions import MideaBleConnectionError, MideaBleError
from .protocol.fa import FanStatus

_LOGGER = logging.getLogger(__name__)

type MideaFanConfigEntry = ConfigEntry[MideaFanCoordinator]


class MideaFanCoordinator(DataUpdateCoordinator[FanStatus]):
    """Poll the fan and apply updates pushed in command replies."""

    config_entry: MideaFanConfigEntry

    def __init__(self, hass: HomeAssistant, entry: MideaFanConfigEntry) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=entry.title, update_interval=UPDATE_INTERVAL
        )
        self.address: str = entry.data[CONF_ADDRESS]
        self.serial: str = entry.data[CONF_SERIAL]
        self.client = MideaFanClient(
            build_advertis_data(self.address, self.serial),
            self._connect,
            idle_timeout=IDLE_TIMEOUT,
            on_status=self._on_status,
        )

    def _ble_device(self):
        return bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True)

    async def _connect(self, disconnected_callback: Callable[[BleakClient], None]) -> BleakClient:
        device = self._ble_device()
        if device is None:
            raise MideaBleConnectionError(f"{self.address} is not reachable by any Bluetooth adapter")
        return await establish_connection(
            BleakClientWithServiceCache,
            device,
            self.name,
            disconnected_callback,
            ble_device_callback=lambda: self._ble_device() or device,
        )

    @callback
    def _on_status(self, status: FanStatus) -> None:
        self.async_set_updated_data(status)

    async def _async_update_data(self) -> FanStatus:
        try:
            return await self.client.query()
        except (MideaBleError, BleakError, TimeoutError) as err:
            raise UpdateFailed(f"Could not read fan status: {err}") from err

    async def async_set(self, **fields: Any) -> None:
        """Send a set command; the reply updates coordinator data."""
        try:
            await self.client.set(**fields)
        except (MideaBleError, BleakError, TimeoutError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err
