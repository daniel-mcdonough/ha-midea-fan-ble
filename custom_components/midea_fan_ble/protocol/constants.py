"""Constants shared by the Midea BLE protocol implementation."""

from typing import Final

MIDEA_MANUFACTURER_ID: Final = 0x06A8
MIDEA_ADVERTISEMENT_MARKER: Final = 0x01
MIDEA_SERVICE_UUID: Final = "0000ffa0-0000-1000-8000-00805f9b34fb"
MIDEA_WRITE_CHAR_UUID: Final = "0000ffa1-0000-1000-8000-00805f9b34fb"
MIDEA_NOTIFY_CHAR_UUID: Final = "0000ffa2-0000-1000-8000-00805f9b34fb"

ROOT_KEY_INFO: Final = b"midea_bleapp"
AES_KEY_LENGTH: Final = 16
CCM_NONCE_LENGTH: Final = 8
CCM_TAG_LENGTH: Final = 8
P256_PRIVATE_KEY_LENGTH: Final = 32
P256_PUBLIC_KEY_LENGTH: Final = 64

# Midea appliance type codes. The first byte of the root-key input is the
# appliance type (0xAC for air conditioners, 0xFA for fans).
DEVICE_TYPE_FAN: Final = 0xFA

# Business-frame type carrying a raw appliance (UART) frame.
BIZ_TYPE_APPLIANCE: Final = 0x20
