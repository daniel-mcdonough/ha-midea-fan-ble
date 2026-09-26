"""Protocol tests using frames captured from a real MSFS07RW6GB."""

import pytest

from custom_components.midea_fan_ble.protocol.advertisement import (
    build_advertis_data,
    parse_serial_payload,
)
from custom_components.midea_fan_ble.protocol.crypto import derive_root_key
from custom_components.midea_fan_ble.protocol.exceptions import (
    MideaBleAdvertisementError,
    MideaBleFrameError,
)
from custom_components.midea_fan_ble.protocol.fa import build_query, build_set, parse_status
from custom_components.midea_fan_ble.protocol.handshake import HandshakeState

ADDRESS = "AA:BB:CC:DD:EE:FF"
SERIAL_PAYLOAD = bytes.fromhex("013132333435363738464130303031")
ADDRESS_PAYLOAD = bytes.fromhex("01123456ffeeddccbbaa00")
ADVERTIS_DATA = bytes.fromhex("fa3132333435363738aabbccddeeff")
ROOT_KEY = bytes.fromhex("350ad556fca2b9d7d34ba601ac2b6460")
C1_REPLY = bytes.fromhex("aa5518d9024c4614971680908bb5a2a6a4fb9933c0c254c95abe")

STATUS_SPEED1 = bytes.fromhex(
    "aa3efa0000000000020300000400290100000000000000440000000000600000150540"
    "000000000001000000000000001a000000000000000000000000007c"
)
STATUS_OSC_BOTH = bytes.fromhex(
    "aa3efa0000000000020300000400290100000d000000004300000000006000001505401b"
    "0000000001000000000000001a000000000000000000000000183d"
)
SET_SPEED2 = bytes.fromhex(
    "aa3cfa0000000000020200000000800200008000000000000000000000000000000000"
    "00000000000000000000000000000000000000000000000000c4"
)
SET_SPEED1 = bytes.fromhex(
    "aa3cfa0000000000020200000000800100008000000000000000000000000000000000"
    "00000000000000000000000000000000000000000000000000c5"
)


def test_parse_serial_advertisement():
    adv = parse_serial_payload(SERIAL_PAYLOAD, ADDRESS)
    assert adv.serial == "12345678FA0001"
    assert adv.device_type == 0xFA
    assert adv.advertis_data == ADVERTIS_DATA


def test_address_advertisement_is_rejected():
    with pytest.raises(MideaBleAdvertisementError):
        parse_serial_payload(ADDRESS_PAYLOAD, ADDRESS)


def test_root_key_matches_live_handshake():
    assert build_advertis_data(ADDRESS, "12345678FA0001") == ADVERTIS_DATA
    assert derive_root_key(ADVERTIS_DATA) == ROOT_KEY
    info = HandshakeState(ADVERTIS_DATA, bytes(6)).on_receive(C1_REPLY)
    assert (info.kind, info.result) == ("c1", 0)


def test_build_query():
    assert build_query() == bytes.fromhex("aa0afa00000000000203f7")


def test_build_set_speed_matches_capture():
    assert build_set(speed=2) == SET_SPEED2
    assert build_set(speed=1) == SET_SPEED1


def test_build_set_fields():
    body = build_set(power=False, display=False, buzzer=False)[10:-1]
    assert body[0] == 0  # body type
    assert body[1 + 1] == 0x08  # buzzer off
    assert body[1 + 3] == 0  # power off
    assert body[1 + 7] == 0x80  # oscillation unchanged
    assert body[1 + 18] == 0x80  # display off
    mode_body = build_set(mode=2)[10:-1]
    assert mode_body[1 + 3] == 0x05  # on + natural


def test_build_set_oscillation_matches_live_encoding():
    horiz = build_set(horizontal_angle=120)[10:-1]
    assert len(horiz) == 52 and horiz[1 + 7] == 0x03 and horiz[1 + 50] == 24
    vert = build_set(vertical_angle=135)[10:-1]
    assert vert[1 + 7] == 0x05 and vert[1 + 24] == 27
    both = build_set(horizontal_angle=0, vertical_angle=0)[10:-1]
    assert both[1 + 7] == 0x0C
    assert build_set(horizontal_angle=0)[10:-1][1 + 7] == 0x02
    assert build_set(vertical_angle=0)[10:-1][1 + 7] == 0x04


def test_build_set_rejects_bad_values():
    with pytest.raises(ValueError):
        build_set(speed=0)
    with pytest.raises(ValueError):
        build_set(mode=99)
    with pytest.raises(ValueError):
        build_set(horizontal_angle=90)
    with pytest.raises(ValueError):
        build_set(horizontal_angle=120, vertical_angle=0)


def test_parse_status():
    s = parse_status(STATUS_SPEED1)
    assert s.power and s.speed == 1 and s.mode == 20
    assert not s.oscillate and s.display and s.buzzer and s.mode_name == "normal"
    assert s.temperature == 27 and s.fa_protocol == 5 and s.error_code == 0


def test_parse_status_oscillating_both_axes():
    s = parse_status(STATUS_OSC_BOTH)
    assert (s.horizontal_angle, s.vertical_angle) == (120, 135) and s.oscillate


def test_parse_status_rejects_bad_checksum():
    bad = STATUS_SPEED1[:-1] + bytes((STATUS_SPEED1[-1] ^ 1,))
    with pytest.raises(MideaBleFrameError):
        parse_status(bad)
