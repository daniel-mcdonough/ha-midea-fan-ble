"""Midea fan (appliance type 0xFA) appliance-frame codec.

Field layout ported from midea-local's ``midealocal/devices/fa`` (MIT,
Copyright (c) 2021 George Zhao), restricted to the protocol-5 fields that
matter for a stand fan. Frames are the standard Midea UART framing::

    AA LEN FA 00 00 00 00 00 PROTO MSGTYPE BODY... CHECKSUM

Status bodies are offset by one from set bodies because byte 0 of the
response body is the body type.

Oscillation on the MSFS07RW6GB (verified live) does not follow midea-local:
set byte 7 selects an axis group in bits 1-3 (1 horizontal, 2 vertical,
6 both) and on/off in bit 0; the angle, in degrees / 5, goes in set byte 50
(horizontal) or 24 (vertical). The fan ignores "on" without a valid angle.
"""

from dataclasses import dataclass

from .constants import DEVICE_TYPE_FAN
from .exceptions import MideaBleFrameError

MSG_SET = 0x02
MSG_QUERY = 0x03
MSG_NOTIFY = 0x04
DEFAULT_PROTOCOL_VERSION = 2

HEADER_LENGTH = 10
SET_BODY_LENGTH = 49
NO_CHANGE = 0x80

OSC_GROUP_HORIZONTAL = 1
OSC_GROUP_VERTICAL = 2
OSC_GROUP_BOTH = 6
SET_VERTICAL_ANGLE_BYTE = 24
SET_HORIZONTAL_ANGLE_BYTE = 50
HORIZONTAL_ANGLES = (30, 60, 120)
VERTICAL_ANGLES = (30, 60, 135)

MAX_SPEED = 26
TEMPERATURE_OFFSET = 41

# Modes the MSFS07RW6GB accepts. 22 is presumed "auto": it is accepted and
# picks its own speed, but that name has not been confirmed on the panel.
MSFS07_MODES: dict[int, str] = {20: "normal", 2: "natural", 18: "sleep", 22: "auto"}

BUZZER_ON = 0x04
BUZZER_OFF = 0x08


def _checksum(data: bytes) -> int:
    return (~sum(data) + 1) & 0xFF


def build_frame(
    msg_type: int, body: bytes, protocol_version: int = DEFAULT_PROTOCOL_VERSION
) -> bytes:
    """Wrap an appliance body in the Midea UART header and checksum."""
    frame = bytearray(
        (
            0xAA,
            HEADER_LENGTH + len(body),
            DEVICE_TYPE_FAN,
            0,
            0,
            0,
            0,
            0,
            protocol_version,
            msg_type,
        )
    )
    frame.extend(body)
    frame.append(_checksum(bytes(frame[1:])))
    return bytes(frame)


def build_query(protocol_version: int = DEFAULT_PROTOCOL_VERSION) -> bytes:
    """Build the full-status query."""
    return build_frame(MSG_QUERY, b"", protocol_version)


def build_set(
    *,
    power: bool | None = None,
    mode: int | None = None,
    speed: int | None = None,
    horizontal_angle: int | None = None,
    vertical_angle: int | None = None,
    display: bool | None = None,
    buzzer: bool | None = None,
    protocol_version: int = DEFAULT_PROTOCOL_VERSION,
) -> bytes:
    """Build a set command; fields left as None are not changed.

    Setting ``mode`` also powers the fan on, as the mode shares a byte with
    the power bit. Oscillation angles are in degrees; 0 turns that axis off.
    """
    length = SET_BODY_LENGTH if horizontal_angle is None else SET_HORIZONTAL_ANGLE_BYTE + 1
    body = bytearray(length)
    body[3] = NO_CHANGE
    body[7] = NO_CHANGE
    if power is not None:
        body[3] = int(power)
    if mode is not None:
        if not 1 <= mode <= 31:
            raise ValueError(f"mode must be 1..31, got {mode}")
        body[3] = 1 | ((mode << 1) & 0x3E)
    if speed is not None:
        if not 1 <= speed <= MAX_SPEED:
            raise ValueError(f"speed must be 1..{MAX_SPEED}")
        body[4] = speed
    if horizontal_angle is not None and vertical_angle is not None:
        if bool(horizontal_angle) != bool(vertical_angle):
            raise ValueError("set both axes on or both off, or send separate commands")
        body[7] = OSC_GROUP_BOTH << 1 | bool(horizontal_angle)
    elif horizontal_angle is not None:
        body[7] = OSC_GROUP_HORIZONTAL << 1 | bool(horizontal_angle)
    elif vertical_angle is not None:
        body[7] = OSC_GROUP_VERTICAL << 1 | bool(vertical_angle)
    if horizontal_angle:
        if horizontal_angle not in HORIZONTAL_ANGLES:
            raise ValueError(f"horizontal angle must be one of {HORIZONTAL_ANGLES}")
        body[SET_HORIZONTAL_ANGLE_BYTE] = horizontal_angle // 5
    if vertical_angle:
        if vertical_angle not in VERTICAL_ANGLES:
            raise ValueError(f"vertical angle must be one of {VERTICAL_ANGLES}")
        body[SET_VERTICAL_ANGLE_BYTE] = vertical_angle // 5
    if display is not None:
        body[18] = 0x40 if display else 0x80
    if buzzer is not None:
        body[1] = BUZZER_ON if buzzer else BUZZER_OFF
    return build_frame(MSG_SET, b"\x00" + bytes(body), protocol_version)


@dataclass(frozen=True, slots=True)
class FanStatus:
    """Decoded fan state."""

    power: bool
    mode: int
    speed: int
    horizontal_angle: int
    vertical_angle: int
    display: bool
    buzzer: bool
    temperature: int | None
    error_code: int
    fa_protocol: int
    raw: bytes

    @property
    def mode_name(self) -> str | None:
        """Return the model-specific mode name, if known."""
        return MSFS07_MODES.get(self.mode)

    @property
    def oscillate(self) -> bool:
        """Return whether either axis is oscillating."""
        return bool(self.horizontal_angle or self.vertical_angle)


def parse_status(frame: bytes) -> FanStatus:
    """Validate and decode a query/set/notify response frame."""
    if len(frame) < HEADER_LENGTH + 2 or frame[0] != 0xAA:
        raise MideaBleFrameError("appliance frame too short or bad sync")
    if frame[1] != len(frame) - 1:
        raise MideaBleFrameError("appliance frame length mismatch")
    if frame[2] != DEVICE_TYPE_FAN:
        raise MideaBleFrameError(f"not a fan frame: type 0x{frame[2]:02x}")
    if _checksum(frame[1:-1]) != frame[-1]:
        raise MideaBleFrameError("appliance frame checksum mismatch")
    if frame[9] not in (MSG_SET, MSG_QUERY, MSG_NOTIFY):
        raise MideaBleFrameError(f"unexpected message type 0x{frame[9]:02x}")
    body = frame[HEADER_LENGTH:-1]
    if len(body) < 26:
        raise MideaBleFrameError("status body too short")
    temp_raw = body[13]
    return FanStatus(
        power=bool(body[4] & 0x01),
        mode=(body[4] & 0x3E) >> 1,
        speed=body[5] if 1 <= body[5] <= MAX_SPEED else 0,
        horizontal_angle=body[51] * 5 if len(body) > 51 and body[8] & 0x01 else 0,
        vertical_angle=body[25] * 5 if body[8] & 0x01 else 0,
        display=(body[19] & 0xC0) >> 6 == 1,
        buzzer=body[2] != BUZZER_OFF,
        temperature=temp_raw - TEMPERATURE_OFFSET if 0 < temp_raw <= 91 else None,
        error_code=body[1],
        fa_protocol=body[23],
        raw=bytes(frame),
    )
