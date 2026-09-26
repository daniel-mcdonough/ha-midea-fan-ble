"""Config flow for Midea BLE fans.

The fan alternates two advertisements and only one carries the serial the
handshake key is derived from. Depending on the adapter, Home Assistant may
see that one rarely, so the flow waits for it with a progress step and falls
back to asking for the serial.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from bleak.exc import BleakError

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import CONF_SERIAL, DOMAIN, SERIAL_ADVERTISEMENT_TIMEOUT
from .protocol.advertisement import FanAdvertisement, parse_serial_payload
from .protocol.constants import DEVICE_TYPE_FAN, MIDEA_ADVERTISEMENT_MARKER, MIDEA_MANUFACTURER_ID
from .protocol.exceptions import MideaBleAdvertisementError, MideaBleError

_LOGGER = logging.getLogger(__name__)


def _parse(info: BluetoothServiceInfoBleak) -> FanAdvertisement | None:
    payload = info.manufacturer_data.get(MIDEA_MANUFACTURER_ID)
    if payload is None:
        return None
    try:
        return parse_serial_payload(payload, info.address)
    except MideaBleAdvertisementError:
        return None


class MideaFanConfigFlow(ConfigFlow, domain=DOMAIN):
    """Discover a fan, get its serial, and verify the BLE handshake."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, BluetoothServiceInfoBleak] = {}
        self._address: str | None = None
        self._fan: FanAdvertisement | None = None
        self._serial_task: asyncio.Task[FanAdvertisement | None] | None = None

    async def _async_wait_for_serial(self, address: str) -> FanAdvertisement | None:
        found: list[FanAdvertisement] = []

        def _match(info: BluetoothServiceInfoBleak) -> bool:
            if parsed := _parse(info):
                found.append(parsed)
                return True
            return False

        try:
            await bluetooth.async_process_advertisements(
                self.hass,
                _match,
                {"address": address},
                BluetoothScanningMode.ACTIVE,
                SERIAL_ADVERTISEMENT_TIMEOUT,
            )
        except TimeoutError:
            return None
        return found[0] if found else None

    async def _async_test(self, fan: FanAdvertisement) -> str | None:
        """Handshake and query once; return an error key or None."""
        from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

        from .client import MideaFanClient

        async def _connect(disconnected_callback):
            device = bluetooth.async_ble_device_from_address(self.hass, fan.address, connectable=True)
            if device is None:
                raise MideaBleError("device not reachable")
            return await establish_connection(
                BleakClientWithServiceCache, device, fan.serial, disconnected_callback
            )

        client = MideaFanClient(fan.advertis_data, _connect)
        try:
            await client.query()
        except (MideaBleError, BleakError, TimeoutError) as err:
            _LOGGER.debug("Test connection to %s failed: %s", fan.address, err)
            return "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error testing %s", fan.address)
            return "unknown"
        finally:
            await client.disconnect()
        return None

    async def _async_select(self, info: BluetoothServiceInfoBleak) -> ConfigFlowResult:
        """Continue with a chosen device, waiting for its serial if needed."""
        self._address = info.address
        if (fan := _parse(info)) is not None:
            return await self._async_finish(fan)
        return await self.async_step_wait_serial()

    async def _async_finish(self, fan: FanAdvertisement) -> ConfigFlowResult:
        if fan.device_type != DEVICE_TYPE_FAN:
            return self.async_abort(reason="not_supported")
        self._fan = fan
        return await self.async_step_test()

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        fan = _parse(discovery_info)
        if fan is not None and fan.device_type != DEVICE_TYPE_FAN:
            return self.async_abort(reason="not_supported")
        self._discovered[discovery_info.address] = discovery_info
        self._address = discovery_info.address
        self.context["title_placeholders"] = {"name": f"Midea fan ({discovery_info.address})"}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._address is not None
        if user_input is not None:
            return await self._async_select(self._discovered[self._address])
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm", description_placeholders={"address": self._address}
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return await self._async_select(self._discovered[address])

        current = self._async_current_ids(include_ignore=False)
        for info in async_discovered_service_info(self.hass, connectable=True):
            payload = info.manufacturer_data.get(MIDEA_MANUFACTURER_ID)
            if info.address in current or not payload or payload[0] != MIDEA_ADVERTISEMENT_MARKER:
                continue
            fan = _parse(info)
            if fan is None or fan.device_type == DEVICE_TYPE_FAN:
                self._discovered[info.address] = info
        if not self._discovered:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_ADDRESS): vol.In({a: f"{i.name} ({a})" for a, i in self._discovered.items()})}
            ),
        )

    async def async_step_wait_serial(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._address is not None
        if self._serial_task is None:
            self._serial_task = self.hass.async_create_task(self._async_wait_for_serial(self._address))
        if not self._serial_task.done():
            return self.async_show_progress(
                step_id="wait_serial",
                progress_action="wait_serial",
                progress_task=self._serial_task,
                description_placeholders={"address": self._address},
            )
        self._fan = self._serial_task.result()
        self._serial_task = None
        return self.async_show_progress_done(
            next_step_id="serial_found" if self._fan else "manual_serial"
        )

    async def async_step_serial_found(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._fan is not None
        return await self._async_finish(self._fan)

    async def async_step_manual_serial(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._address is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            payload = bytes((MIDEA_ADVERTISEMENT_MARKER,)) + user_input[CONF_SERIAL].strip().encode()
            try:
                fan = parse_serial_payload(payload, self._address)
            except (MideaBleAdvertisementError, UnicodeEncodeError):
                errors[CONF_SERIAL] = "invalid_serial"
            else:
                return await self._async_finish(fan)
        return self.async_show_form(
            step_id="manual_serial",
            data_schema=vol.Schema({vol.Required(CONF_SERIAL): str}),
            description_placeholders={"address": self._address},
            errors=errors,
        )

    async def async_step_test(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Verify the handshake; on failure let the user retry."""
        assert self._fan is not None
        errors: dict[str, str] = {}
        if (error := await self._async_test(self._fan)) is None:
            return self.async_create_entry(
                title=f"Midea fan {self._fan.serial[-4:]}",
                data={CONF_ADDRESS: self._fan.address, CONF_SERIAL: self._fan.serial},
            )
        errors["base"] = error
        return self.async_show_form(step_id="test", errors=errors)
