"""C1/C2/C3 handshake message construction and receive parsing.

Ported from ``internal/proto/handshake.go`` in midea-ble-go. BLE timing and
retransmission policy intentionally remain in the transport/session layer.
"""

import os
from collections.abc import Callable
from dataclasses import dataclass

from .crypto import (
    cipher_message,
    create_keypair,
    decipher_message,
    derive_root_key,
    derive_session_key,
)
from .exceptions import MideaBleHandshakeError
from .frames import (
    CONN_T1,
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

RandomBytes = Callable[[int], bytes]


@dataclass(frozen=True, slots=True)
class ReceiveInfo:
    """Result of decoding one complete conn frame."""

    kind: str
    result: int | None = None
    peer_public_key: bytes | None = None
    biz_body: bytes | None = None
    body: bytes = b""


class HandshakeState:
    """Hold ephemeral keys and build/parse handshake protocol messages."""

    def __init__(
        self,
        advertis_data: bytes,
        open_id: bytes,
        *,
        random_bytes: RandomBytes = os.urandom,
    ) -> None:
        if len(advertis_data) < 11:
            raise MideaBleHandshakeError("advertis_data must be at least 11 bytes")
        if len(open_id) != 6:
            raise MideaBleHandshakeError("open_id must be exactly 6 bytes")
        self.advertis_data = bytes(advertis_data)
        self.open_id = bytes(open_id)
        self.root_key = derive_root_key(self.advertis_data)
        self.session_key: bytes | None = None
        self.private_key: bytes | None = None
        self.public_key: bytes | None = None
        self.peer_public_key: bytes | None = None
        self._random_bytes = random_bytes
        self._conn_sequence = self._random_nonzero_byte()
        self._security_sequence = self._random_nonzero_byte()

    def _random_nonzero_byte(self) -> int:
        value = self._random_bytes(1)
        if len(value) != 1:
            raise MideaBleHandshakeError("random source must return the requested bytes")
        return value[0] or 1

    @staticmethod
    def _next_sequence(value: int) -> int:
        value = (value + 1) & 0xFF
        return value or 1

    def _next_conn_sequence(self) -> int:
        self._conn_sequence = self._next_sequence(self._conn_sequence)
        return self._conn_sequence

    def _next_security_sequence(self) -> int:
        self._security_sequence = self._next_sequence(self._security_sequence)
        return self._security_sequence

    def _cipher(self, key: bytes, plaintext: bytes) -> bytes:
        return cipher_message(key, plaintext, random_bytes=self._random_bytes)

    def build_get_version(self) -> bytes:
        """Build the optional T1 get-version frame."""
        return encode_conn(CONN_T1, bytes((1, *([0] * 9))), self._next_conn_sequence())

    def build_c1(self) -> bytes:
        """Build a fresh C1 frame; retries must call this again."""
        security = encode_security(SEC_C1, self.open_id, self._next_security_sequence())
        return encode_conn(
            CONN_T2,
            self._cipher(self.root_key, security),
            self._next_conn_sequence(),
        )

    def build_c2(self) -> bytes:
        """Build C2; a transport must reuse the exact bytes for retries."""
        security = encode_security(SEC_C2, b"", self._next_security_sequence())
        return encode_conn(
            CONN_T2,
            self._cipher(self.root_key, security),
            self._next_conn_sequence(),
        )

    def establish_session(self, peer_public_key: bytes) -> None:
        """Create a local P-256 pair and derive the session key from peer C2."""
        if len(peer_public_key) != 64:
            raise MideaBleHandshakeError("C2 peer public key must be exactly 64 bytes")
        private_key, public_key = create_keypair()
        self.peer_public_key = bytes(peer_public_key)
        self.private_key = private_key
        self.public_key = public_key
        self.session_key = derive_session_key(private_key, peer_public_key)

    def build_c3(self) -> bytes:
        """Build C3; a transport must reuse the exact bytes for retries."""
        if self.session_key is None or self.public_key is None:
            raise MideaBleHandshakeError("C2 must establish a session before C3")
        proof = self._cipher(self.session_key, self.advertis_data)
        security = encode_security(
            SEC_C3, self.public_key + proof, self._next_security_sequence()
        )
        return encode_conn(
            CONN_T2,
            self._cipher(self.root_key, security),
            self._next_conn_sequence(),
        )

    def build_biz(self, frame_type: int, body: bytes) -> bytes:
        """Build a post-handshake C4 business frame."""
        if self.session_key is None:
            raise MideaBleHandshakeError("handshake is not complete")
        security = encode_security(
            SEC_C4, encode_biz(frame_type, body), self._next_security_sequence()
        )
        return encode_conn(
            CONN_T3,
            self._cipher(self.session_key, security),
            self._next_conn_sequence(),
        )

    def on_receive(self, raw: bytes) -> ReceiveInfo:
        """Decode one complete connection frame using the active keys."""
        conn = decode_conn(raw)
        if conn.frame_type == CONN_T1:
            return ReceiveInfo(kind="t1", body=conn.body)
        if len(conn.body) < 16:
            return ReceiveInfo(kind="security_error", body=conn.body)
        if conn.frame_type == CONN_T2:
            plaintext = decipher_message(self.root_key, conn.body)
        elif conn.frame_type == CONN_T3:
            if self.session_key is None:
                raise MideaBleHandshakeError("received T3 before session key establishment")
            plaintext = decipher_message(self.session_key, conn.body)
        else:  # Kept explicit even though decode_conn validates known types.
            raise MideaBleHandshakeError("unsupported connection frame type")
        security = decode_security(plaintext)
        if security.command == SEC_C1:
            result = security.body[0] if security.body else None
            return ReceiveInfo(kind="c1", result=result)
        if security.command == SEC_C2:
            return ReceiveInfo(kind="c2", peer_public_key=security.body)
        if security.command == SEC_C3:
            result = security.body[0] if security.body else None
            return ReceiveInfo(kind="c3", result=result)
        if security.command == SEC_C4:
            biz = decode_biz(security.body)
            return ReceiveInfo(kind="biz", biz_body=biz.body)
        raise MideaBleHandshakeError("unsupported security command")
