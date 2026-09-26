"""Exceptions raised by the pure Midea BLE protocol package."""


class MideaBleError(Exception):
    """Base exception for Midea BLE protocol errors."""


class MideaBleAdvertisementError(MideaBleError):
    """Raised when an advertisement is not a supported Midea payload."""


class MideaBleCryptoError(MideaBleError):
    """Raised when cryptographic input or authentication is invalid."""


class MideaBleFrameError(MideaBleError):
    """Raised when a wire-protocol frame is malformed."""


class MideaBleHandshakeError(MideaBleError):
    """Raised when the C1/C2/C3 exchange fails."""


class MideaBleAuthenticationError(MideaBleHandshakeError):
    """Raised when peer authentication fails."""


class MideaBleConnectionError(MideaBleError):
    """Raised when a BLE connection cannot be established or used."""
