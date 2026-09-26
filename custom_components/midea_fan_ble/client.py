"""Async BLE client for Midea fans. Depends on bleak only, not Home Assistant."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from contextlib import suppress

from bleak import BleakClient

from .protocol.constants import (
    BIZ_TYPE_APPLIANCE,
    MIDEA_NOTIFY_CHAR_UUID,
    MIDEA_WRITE_CHAR_UUID,
)
from .protocol.exceptions import (
    MideaBleAuthenticationError,
    MideaBleConnectionError,
    MideaBleError,
)
from .protocol.fa import FanStatus, build_query, build_set, parse_status
from .protocol.frames import ConnFrameBuffer
from .protocol.handshake import HandshakeState, ReceiveInfo

_LOGGER = logging.getLogger(__name__)

# connect(disconnected_callback) -> connected BleakClient
Connector = Callable[[Callable[[BleakClient], None]], Awaitable[BleakClient]]
StatusCallback = Callable[[FanStatus], None]

DEFAULT_IDLE_TIMEOUT = 20.0


class _Session:
    """One connected, authenticated BLE session."""

    def __init__(
        self, client: BleakClient, advertis_data: bytes, on_push: Callable[[bytes], None]
    ) -> None:
        self.client = client
        self._state = HandshakeState(advertis_data, os.urandom(6))
        self._buffer = ConnFrameBuffer()
        self._queue: asyncio.Queue[ReceiveInfo | BaseException] = asyncio.Queue()
        self._on_push = on_push
        self._awaiting_biz = False

    def _on_notify(self, _sender: object, data: bytearray) -> None:
        for raw in self._buffer.feed(bytes(data)):
            try:
                info = self._state.on_receive(raw)
            except BaseException as err:
                self._queue.put_nowait(err)
                continue
            if info.kind == "biz" and not self._awaiting_biz and info.biz_body:
                self._on_push(info.biz_body)
            else:
                self._queue.put_nowait(info)

    async def _exchange(
        self, frame: Callable[[], bytes] | bytes, kind: str, attempts: int, timeout: float
    ) -> ReceiveInfo:
        for _ in range(attempts):
            data = frame() if callable(frame) else frame
            await self.client.write_gatt_char(MIDEA_WRITE_CHAR_UUID, data, response=True)
            try:
                async with asyncio.timeout(timeout):
                    while True:
                        item = await self._queue.get()
                        if isinstance(item, BaseException):
                            raise item
                        if item.kind == "security_error":
                            raise MideaBleAuthenticationError(
                                f"device security error: {item.body.hex()}"
                            )
                        if item.kind == kind:
                            return item
            except TimeoutError:
                continue
        raise MideaBleConnectionError(f"timed out waiting for {kind}")

    async def handshake(self) -> None:
        await self.client.start_notify(MIDEA_NOTIFY_CHAR_UUID, self._on_notify)
        await asyncio.sleep(0.3)
        # C1 is rebuilt per attempt; C2/C3 must be resent byte-identical.
        c1 = await self._exchange(self._state.build_c1, "c1", attempts=10, timeout=1.5)
        if c1.result != 0:
            raise MideaBleAuthenticationError(f"unexpected C1 result: {c1.result}")
        c2 = await self._exchange(self._state.build_c2(), "c2", attempts=6, timeout=1.5)
        if c2.peer_public_key is None:
            raise MideaBleAuthenticationError("C2 omitted the peer public key")
        self._state.establish_session(c2.peer_public_key)
        c3 = await self._exchange(self._state.build_c3(), "c3", attempts=6, timeout=1.5)
        if c3.result != 1:
            raise MideaBleAuthenticationError(f"C3 result was {c3.result}")

    async def request(
        self, appliance_frame: bytes, attempts: int = 3, timeout: float = 3.0
    ) -> bytes:
        while not self._queue.empty():
            self._queue.get_nowait()
        self._awaiting_biz = True
        try:
            reply = await self._exchange(
                lambda: self._state.build_biz(BIZ_TYPE_APPLIANCE, appliance_frame),
                "biz",
                attempts,
                timeout,
            )
        finally:
            self._awaiting_biz = False
        if not reply.biz_body:
            raise MideaBleError("business reply omitted the appliance frame")
        return reply.biz_body


class MideaFanClient:
    """Serialized query/set access with a short-lived persistent connection."""

    def __init__(
        self,
        advertis_data: bytes,
        connector: Connector,
        *,
        idle_timeout: float = DEFAULT_IDLE_TIMEOUT,
        on_status: StatusCallback | None = None,
    ) -> None:
        self._advertis_data = advertis_data
        self._connector = connector
        self._idle_timeout = idle_timeout
        self._on_status = on_status
        self._lock = asyncio.Lock()
        self._session: _Session | None = None
        self._idle_handle: asyncio.TimerHandle | None = None

    def _handle_disconnect(self, _client: BleakClient) -> None:
        _LOGGER.debug("Fan disconnected")
        self._session = None

    def _handle_push(self, frame: bytes) -> None:
        try:
            status = parse_status(frame)
        except MideaBleError as err:
            _LOGGER.debug("Ignoring unsolicited frame %s: %s", frame.hex(), err)
            return
        if self._on_status:
            self._on_status(status)

    async def _ensure_session(self) -> _Session:
        if self._session is not None and self._session.client.is_connected:
            return self._session
        client = await self._connector(self._handle_disconnect)
        session = _Session(client, self._advertis_data, self._handle_push)
        try:
            await session.handshake()
        except BaseException:
            with suppress(Exception):
                await client.disconnect()
            raise
        self._session = session
        return session

    def _schedule_idle_disconnect(self) -> None:
        if self._idle_handle:
            self._idle_handle.cancel()
        loop = asyncio.get_running_loop()
        self._idle_handle = loop.call_later(
            self._idle_timeout, lambda: loop.create_task(self.disconnect())
        )

    async def _request(self, frame: bytes) -> FanStatus:
        async with self._lock:
            for attempt in range(2):
                try:
                    session = await self._ensure_session()
                    raw = await session.request(frame)
                    break
                except (MideaBleConnectionError, OSError, EOFError, TimeoutError) as err:
                    # Stale connection; drop it and retry once from scratch.
                    await self._drop()
                    if attempt:
                        raise MideaBleConnectionError(str(err)) from err
                    _LOGGER.debug("Retrying after error: %s", err)
                except Exception:
                    await self._drop()
                    raise
            self._schedule_idle_disconnect()
        status = parse_status(raw)
        if self._on_status:
            self._on_status(status)
        return status

    async def _drop(self) -> None:
        session, self._session = self._session, None
        if session is not None:
            with suppress(Exception):
                await session.client.disconnect()

    async def query(self) -> FanStatus:
        """Read the full fan status."""
        return await self._request(build_query())

    async def set(self, **fields: bool | int | None) -> FanStatus:
        """Change fields (see protocol.fa.build_set) and return the new status."""
        return await self._request(build_set(**fields))  # type: ignore[arg-type]

    async def disconnect(self) -> None:
        """Close the connection if idle."""
        if self._idle_handle:
            self._idle_handle.cancel()
            self._idle_handle = None
        async with self._lock:
            await self._drop()
