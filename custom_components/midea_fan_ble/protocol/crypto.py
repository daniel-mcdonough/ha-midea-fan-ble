"""Cryptographic primitives for the Midea BLE protocol.

Ported from ``internal/proto/crypto.go`` in midea-ble-go. Cryptographic
operations are delegated to ``cryptography``; no primitive is implemented here.
"""

import hashlib
import os
from collections.abc import Callable

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESCCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .constants import (
    AES_KEY_LENGTH,
    CCM_NONCE_LENGTH,
    CCM_TAG_LENGTH,
    P256_PRIVATE_KEY_LENGTH,
    P256_PUBLIC_KEY_LENGTH,
    ROOT_KEY_INFO,
)
from .exceptions import MideaBleCryptoError

RandomBytes = Callable[[int], bytes]


def derive_root_key(advertis_data: bytes) -> bytes:
    """Derive the 16-byte root key using HKDF-SHA256 with empty salt."""
    if not advertis_data:
        raise MideaBleCryptoError("advertis_data must not be empty")
    return HKDF(
        algorithm=hashes.SHA256(), length=AES_KEY_LENGTH, salt=None, info=ROOT_KEY_INFO
    ).derive(advertis_data)


def create_keypair(*, private_key: bytes | None = None) -> tuple[bytes, bytes]:
    """Create a P-256 pair as ``(private32, X||Y)``.

    ``private_key`` is an intentional deterministic test seam.
    """
    try:
        if private_key is None:
            key = ec.generate_private_key(ec.SECP256R1())
        else:
            if len(private_key) != P256_PRIVATE_KEY_LENGTH:
                raise MideaBleCryptoError("P-256 private key must be 32 bytes")
            value = int.from_bytes(private_key, "big")
            if value == 0:
                raise MideaBleCryptoError("P-256 private key must be non-zero")
            key = ec.derive_private_key(value, ec.SECP256R1())
    except ValueError as err:
        raise MideaBleCryptoError("invalid P-256 private key") from err
    numbers = key.public_key().public_numbers()
    public = numbers.x.to_bytes(32, "big") + numbers.y.to_bytes(32, "big")
    private = key.private_numbers().private_value.to_bytes(32, "big")
    return private, public


def derive_session_key(private_key: bytes, peer_public_key: bytes) -> bytes:
    """Return ``SHA256(P-256 ECDH shared X)[:16]``."""
    if len(private_key) != P256_PRIVATE_KEY_LENGTH:
        raise MideaBleCryptoError("P-256 private key must be 32 bytes")
    if len(peer_public_key) != P256_PUBLIC_KEY_LENGTH:
        raise MideaBleCryptoError("P-256 peer public key must be 64 bytes")
    try:
        private = ec.derive_private_key(int.from_bytes(private_key, "big"), ec.SECP256R1())
        peer = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(), b"\x04" + peer_public_key
        )
        shared_x = private.exchange(ec.ECDH(), peer)
    except ValueError as err:
        raise MideaBleCryptoError("invalid P-256 key material") from err
    return hashlib.sha256(shared_x).digest()[:AES_KEY_LENGTH]


def cipher_message(
    key: bytes, plaintext: bytes, *, random_bytes: RandomBytes = os.urandom
) -> bytes:
    """Encrypt as ``nonce8 || ciphertext || tag8`` using AES-128-CCM."""
    if len(key) != AES_KEY_LENGTH:
        raise MideaBleCryptoError("AES-CCM key must be 16 bytes")
    nonce = random_bytes(CCM_NONCE_LENGTH)
    if len(nonce) != CCM_NONCE_LENGTH:
        raise MideaBleCryptoError("nonce source must return exactly 8 bytes")
    return nonce + AESCCM(key, tag_length=CCM_TAG_LENGTH).encrypt(nonce, plaintext, None)


def decipher_message(key: bytes, blob: bytes) -> bytes:
    """Authenticate and decrypt ``nonce8 || ciphertext || tag8``."""
    if len(key) != AES_KEY_LENGTH:
        raise MideaBleCryptoError("AES-CCM key must be 16 bytes")
    if len(blob) < CCM_NONCE_LENGTH + CCM_TAG_LENGTH:
        raise MideaBleCryptoError("cipher blob is too short")
    nonce, ciphertext_and_tag = blob[:CCM_NONCE_LENGTH], blob[CCM_NONCE_LENGTH:]
    try:
        return AESCCM(key, tag_length=CCM_TAG_LENGTH).decrypt(
            nonce, ciphertext_and_tag, None
        )
    except InvalidTag as err:
        raise MideaBleCryptoError("AES-CCM authentication failed") from err
