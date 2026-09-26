"""Constants for the Midea fan BLE integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "midea_fan_ble"
CONF_SERIAL: Final = "serial"

UPDATE_INTERVAL: Final = timedelta(seconds=60)
# Seconds a connection stays open after the last request. Midea BLE devices
# accept one central at a time, so this is kept short to let the phone app in.
IDLE_TIMEOUT: Final = 15.0
# How long setup waits for the advertisement that carries the serial.
SERIAL_ADVERTISEMENT_TIMEOUT: Final = 120
