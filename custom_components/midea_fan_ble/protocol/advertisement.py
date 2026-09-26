"""Parse Midea fan BLE advertisements.

The fan alternates between two 0x06A8 manufacturer payloads:

* serial form: ``01`` + 14 ASCII serial characters, e.g. ``12345678FA0001``.
  Characters 8..10 hold the appliance type in hex (``FA`` for fans).
* address form: ``01`` + 3 opaque bytes + the BLE MAC reversed + ``00``.

Only the serial form carries what the root key needs; the MAC comes from the
observed BLE address. The root-key input is
``type_byte + serial[0:8] + mac`` (15 bytes).
"""

from dataclasses import dataclass

from .constants import DEVICE_TYPE_FAN, MIDEA_ADVERTISEMENT_MARKER
from .exceptions import MideaBleAdvertisementError

SERIAL_LENGTH = 14


@dataclass(frozen=True, slots=True)
class FanAdvertisement:
    """Validated identity of a Midea BLE appliance."""

    address: str
    serial: str
    device_type: int

    @property
    def advertis_data(self) -> bytes:
        """Return the root-key derivation input."""
        return build_advertis_data(self.address, self.serial, self.device_type)


def _mac_bytes(address: str) -> bytes:
    parts = address.split(":")
    if len(parts) != 6 or any(len(p) != 2 for p in parts):
        raise MideaBleAdvertisementError(f"invalid Bluetooth address: {address}")
    try:
        return bytes.fromhex("".join(parts))
    except ValueError as err:
        raise MideaBleAdvertisementError(f"invalid Bluetooth address: {address}") from err


def build_advertis_data(address: str, serial: str, device_type: int = DEVICE_TYPE_FAN) -> bytes:
    """Build the 15-byte root-key input from identity fields."""
    short = serial[:8].encode("ascii")
    if len(short) != 8:
        raise MideaBleAdvertisementError("serial must have at least 8 characters")
    return bytes((device_type,)) + short + _mac_bytes(address)


def parse_serial_payload(payload: bytes, address: str) -> FanAdvertisement:
    """Parse the serial form of the manufacturer payload.

    Raises MideaBleAdvertisementError for the address form or anything else.
    """
    if len(payload) < 1 + SERIAL_LENGTH or payload[0] != MIDEA_ADVERTISEMENT_MARKER:
        raise MideaBleAdvertisementError("not a Midea serial advertisement")
    try:
        serial = payload[1 : 1 + SERIAL_LENGTH].decode("ascii")
    except UnicodeDecodeError as err:
        raise MideaBleAdvertisementError("serial is not ASCII") from err
    if not serial.isalnum():
        raise MideaBleAdvertisementError("serial is not alphanumeric")
    try:
        device_type = int(serial[8:10], 16)
    except ValueError as err:
        raise MideaBleAdvertisementError("serial has no appliance type") from err
    _mac_bytes(address)
    return FanAdvertisement(address=address.upper(), serial=serial, device_type=device_type)
