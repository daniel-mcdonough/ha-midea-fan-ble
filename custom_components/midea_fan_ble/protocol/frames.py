"""Strict codecs and reassembly for Midea BLE protocol frames.

Ported from ``internal/proto/frame.go`` and the receive-buffer logic in
``internal/ac/session.go`` in midea-ble-go.
"""

from dataclasses import dataclass

from .exceptions import MideaBleFrameError

CONN_T1 = 0x01
CONN_T2 = 0x02
CONN_T3 = 0x03
SEC_C1 = 0x01
SEC_C2 = 0x02
SEC_C3 = 0x03
SEC_C4 = 0x04

_CONN_TYPES = frozenset((CONN_T1, CONN_T2, CONN_T3))
_SECURITY_COMMANDS = frozenset((SEC_C1, SEC_C2, SEC_C3, SEC_C4))


def _negative_checksum(data: bytes) -> int:
    return -sum(data) & 0xFF


@dataclass(frozen=True, slots=True)
class ConnFrame:
    """Decoded connection-layer frame."""

    frame_type: int
    sequence: int
    body: bytes


@dataclass(frozen=True, slots=True)
class SecurityFrame:
    """Decoded security-layer frame."""

    command: int
    sequence: int
    body: bytes


@dataclass(frozen=True, slots=True)
class BizFrame:
    """Decoded business-layer frame."""

    frame_type: int
    body: bytes


def encode_conn(frame_type: int, body: bytes, sequence: int) -> bytes:
    """Encode ``AA 55 LEN SEQ TYPE body CHECKSUM``."""
    if frame_type not in _CONN_TYPES:
        raise MideaBleFrameError(f"unknown conn frame type: 0x{frame_type:02x}")
    if not 0 <= sequence <= 0xFF:
        raise MideaBleFrameError("conn sequence must fit in one byte")
    length = len(body) + 4
    if length > 0xFF:
        raise MideaBleFrameError("conn body is too long")
    frame = bytearray((0xAA, 0x55, length, sequence, frame_type))
    frame.extend(body)
    frame.append(_negative_checksum(bytes(frame[2:])))
    return bytes(frame)


def decode_conn(raw: bytes) -> ConnFrame:
    """Decode and fully validate one connection-layer frame."""
    if len(raw) < 6:
        raise MideaBleFrameError("conn frame is too short")
    if raw[:2] != b"\xaa\x55":
        raise MideaBleFrameError("conn sync mismatch")
    expected = 2 + raw[2]
    if len(raw) != expected:
        raise MideaBleFrameError(
            f"conn length mismatch: got {len(raw)}, expected {expected}"
        )
    if raw[4] not in _CONN_TYPES:
        raise MideaBleFrameError(f"unknown conn frame type: 0x{raw[4]:02x}")
    if sum(raw[2:]) & 0xFF:
        raise MideaBleFrameError("conn checksum mismatch")
    return ConnFrame(frame_type=raw[4], sequence=raw[3], body=bytes(raw[5:-1]))


def encode_security(command: int, body: bytes, sequence: int) -> bytes:
    """Encode ``CMD SEQ LEN body``."""
    if command not in _SECURITY_COMMANDS:
        raise MideaBleFrameError(f"unknown security command: 0x{command:02x}")
    if not 0 <= sequence <= 0xFF:
        raise MideaBleFrameError("security sequence must fit in one byte")
    if len(body) > 0xFF:
        raise MideaBleFrameError("security body is too long")
    return bytes((command, sequence, len(body))) + body


def decode_security(raw: bytes) -> SecurityFrame:
    """Decode and fully validate one security-layer frame."""
    if len(raw) < 3:
        raise MideaBleFrameError("security frame is too short")
    if raw[0] not in _SECURITY_COMMANDS:
        raise MideaBleFrameError(f"unknown security command: 0x{raw[0]:02x}")
    expected = 3 + raw[2]
    if len(raw) != expected:
        raise MideaBleFrameError(
            f"security length mismatch: got {len(raw)}, expected {expected}"
        )
    return SecurityFrame(command=raw[0], sequence=raw[1], body=bytes(raw[3:]))


def encode_biz(frame_type: int, body: bytes) -> bytes:
    """Encode ``TYPE LEN RESERVED body CHECKSUM``."""
    if not 0 <= frame_type <= 0xFF:
        raise MideaBleFrameError("biz frame type must fit in one byte")
    length = len(body) + 4
    if length > 0xFF:
        raise MideaBleFrameError("biz body is too long")
    frame = bytearray((frame_type, length, 0))
    frame.extend(body)
    frame.append(_negative_checksum(bytes(frame)))
    return bytes(frame)


def decode_biz(raw: bytes) -> BizFrame:
    """Decode one business-layer frame.

    Real devices may return a non-zero additive checksum here. The containing
    security frame is authenticated by AES-CCM and the nested appliance frame
    has its own checksum, so this matches Go's intentionally tolerant decoder.
    """
    if len(raw) < 4:
        raise MideaBleFrameError("biz frame is too short")
    if len(raw) != raw[1]:
        raise MideaBleFrameError(
            f"biz length mismatch: got {len(raw)}, expected {raw[1]}"
        )
    if raw[2] != 0:
        raise MideaBleFrameError("biz reserved byte is not zero")
    return BizFrame(frame_type=raw[0], body=bytes(raw[3:-1]))


class ConnFrameBuffer:
    """Reassemble complete conn frames from arbitrary BLE notification chunks."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> list[bytes]:
        """Append a chunk and return every newly completed raw conn frame."""
        self._buffer.extend(chunk)
        frames: list[bytes] = []
        while True:
            start = self._buffer.find(b"\xaa\x55")
            if start < 0:
                # Retain a trailing 0xAA because it may be half of the sync word.
                self._buffer[:] = b"\xaa" if self._buffer.endswith(b"\xaa") else b""
                break
            if start:
                del self._buffer[:start]
            if len(self._buffer) < 3:
                break
            total = 2 + self._buffer[2]
            if len(self._buffer) < total:
                break
            frames.append(bytes(self._buffer[:total]))
            del self._buffer[:total]
        return frames
