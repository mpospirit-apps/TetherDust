"""Fernet-based encryption helpers for sensitive model fields.

The encrypt path fails loudly in production (``DEBUG=False``) when no usable
encryption key is configured, so a misconfigured deploy can never silently
persist DB passwords or agent credentials in plaintext. In ``DEBUG`` it warns
once and falls back to plaintext for development convenience.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

if TYPE_CHECKING:
    from cryptography.fernet import Fernet

logger = logging.getLogger("engine")

# Module-level guard so the plaintext-fallback warning is emitted once, not on
# every save.
_warned_no_encryption = False


def _get_fernet_cls() -> type[Fernet] | None:
    """Return the Fernet class if cryptography is installed, else None."""
    try:
        from cryptography.fernet import Fernet as _Fernet

        return _Fernet
    except ImportError:
        return None


def get_fernet() -> Fernet | None:
    """Return a Fernet instance, or None if encryption is unavailable/disabled."""
    fernet_cls = _get_fernet_cls()
    if fernet_cls is None:
        return None
    key = settings.TETHERDUST_ENCRYPTION_KEY
    if not key:
        return None
    return fernet_cls(key.encode() if isinstance(key, str) else key)


def _encryption_unavailable_reason() -> str:
    if _get_fernet_cls() is None:
        return "the 'cryptography' package is not installed"
    return "TETHERDUST_ENCRYPTION_KEY is not set"


def _on_plaintext_fallback() -> None:
    """Fail in production, warn once in DEBUG, when a value cannot be encrypted."""
    reason = _encryption_unavailable_reason()
    if not settings.DEBUG:
        raise ImproperlyConfigured(
            f"Cannot encrypt sensitive field: {reason}. Refusing to store "
            "credentials in plaintext. Generate a key with: "
            'python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())" and set '
            "TETHERDUST_ENCRYPTION_KEY."
        )
    global _warned_no_encryption
    if not _warned_no_encryption:
        logger.warning(
            "Encryption disabled (%s) — sensitive fields (DB passwords, agent "
            "API keys/tokens) are being stored UNENCRYPTED. Set "
            "TETHERDUST_ENCRYPTION_KEY before any non-development use.",
            reason,
        )
        _warned_no_encryption = True


def encrypt_value(value: str) -> str:
    """Encrypt a string value.

    Raises ImproperlyConfigured in production if no encryption key is configured,
    rather than silently storing plaintext.
    """
    if not value:
        return value
    fernet = get_fernet()
    if fernet is None:
        _on_plaintext_fallback()
        return value
    return fernet.encrypt(value.encode()).decode()


def decrypt_value(value: str) -> str:
    """Decrypt a string value, tolerating already-plaintext/legacy values."""
    if not value:
        return value
    fernet = get_fernet()
    if fernet is None:
        return value
    from cryptography.fernet import InvalidToken

    try:
        return fernet.decrypt(value.encode()).decode()
    except InvalidToken:
        # Value may not be encrypted (legacy, or written while encryption was off).
        return value
