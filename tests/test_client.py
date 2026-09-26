"""Client tests against a simulated fan running the device side of the protocol."""

import asyncio

import pytest

from custom_components.midea_fan_ble.client import MideaFanClient
from custom_components.midea_fan_ble.protocol.crypto import (
    cipher_message,
    create_keypair,
    decipher_message,
    derive_root_key,
    derive_session_key,
)
from custom_components.midea_fan_ble.protocol.fa import build_frame
from custom_components.midea_fan_ble.protocol.frames import (
    CONN_T2,
    CONN_T3,
    SEC_C1,
    SEC_C2,
    SEC_C3,
    SEC_C4,
    decode_biz,
    decode_conn,
    decode_security,
    encode_biz,
    encode_conn,
    encode_security,
)
from tests.test_protocol import ADVERTIS_DATA, STATUS_SPEED1


class FakeFan:
    """Minimal device: handshake, echoes status, applies speed from set frames."""

    def __init__(self, wrong_key=False):
        self.root_key = derive_root_key(b"\x00" * 15 if wrong_key else ADVERTIS_DATA)
        self.private, self.public = create_keypair()
        self.session_key = None
        self.status = bytearray(STATUS_SPEED1)
        self.callback = None
        self.is_connected = True
        self.writes = 0

    def _frame_status(self, msg_type):
        body = bytes(self.status[10:-1])
        return build_frame(msg_type, body)

    async def start_notify(self, _uuid, callback):
        self.callback = callback

    async def stop_notify(self, _uuid):
        pass

    async def disconnect(self):
        self.is_connected = False

    def _send(self, conn_type, key, command, body):
        sec = encode_security(command, body, 1)
        self.callback(None, bytearray(encode_conn(conn_type, cipher_message(key, sec), 1)))

    def push(self, speed):
        self.status[15] = speed
        self.status[-1] = 0
        frame = self._frame_status(0x04)
        self._send(CONN_T3, self.session_key, SEC_C4, encode_biz(0x20, frame))

    async def write_gatt_char(self, _uuid, data, response=True):
        self.writes += 1
        conn = decode_conn(data)
        key = self.session_key if conn.frame_type == CONN_T3 else self.root_key
        try:
            sec = decode_security(decipher_message(key, conn.body))
        except Exception:
            self.callback(None, bytearray(encode_conn(CONN_T2, b"\xff\x04", 1)))
            return
        if sec.command == SEC_C1:
            self._send(CONN_T2, self.root_key, SEC_C1, b"\x00")
        elif sec.command == SEC_C2:
            self._send(CONN_T2, self.root_key, SEC_C2, self.public)
        elif sec.command == SEC_C3:
            self.session_key = derive_session_key(self.private, sec.body[:64])
            assert decipher_message(self.session_key, sec.body[64:]) == ADVERTIS_DATA
            self._send(CONN_T2, self.root_key, SEC_C3, b"\x01")
        elif sec.command == SEC_C4:
            frame = decode_biz(sec.body).body
            if frame[9] == 0x02 and frame[10 + 5]:
                self.status[15] = frame[10 + 5]
            reply = self._frame_status(frame[9])
            self._send(CONN_T3, self.session_key, SEC_C4, encode_biz(0x20, reply))


def make_client(fan, pushed=None, **kw):
    connects = []

    async def connector(_cb):
        connects.append(1)
        fan.is_connected = True
        return fan

    client = MideaFanClient(ADVERTIS_DATA, connector, on_status=pushed, **kw)
    return client, connects


async def test_query_and_set():
    fan = FakeFan()
    client, connects = make_client(fan)
    assert (await client.query()).speed == 1
    assert (await client.set(speed=7)).speed == 7
    assert len(connects) == 1  # connection reused
    await client.disconnect()
    assert not fan.is_connected


async def test_reconnects_after_disconnect():
    fan = FakeFan()
    client, connects = make_client(fan)
    await client.query()
    fan.is_connected = False
    client._handle_disconnect(fan)
    await client.query()
    assert len(connects) == 2
    await client.disconnect()


async def test_unsolicited_status_is_pushed():
    fan = FakeFan()
    seen = []
    client, _ = make_client(fan, pushed=seen.append)
    await client.query()
    fan.push(9)
    assert seen[-1].speed == 9
    await client.disconnect()


async def test_wrong_key_fails_authentication():
    from custom_components.midea_fan_ble.protocol.exceptions import MideaBleError

    client, _ = make_client(FakeFan(wrong_key=True))
    with pytest.raises(MideaBleError):
        await client.query()


async def test_idle_disconnect():
    fan = FakeFan()
    client, _ = make_client(fan, idle_timeout=0.05)
    await client.query()
    await asyncio.sleep(0.2)
    assert not fan.is_connected
