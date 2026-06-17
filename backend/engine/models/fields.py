"""Model fields that transparently encrypt their value at rest.

These wrap the Fernet helpers in :mod:`._encryption` so credentials are
encrypted on the way to the database and decrypted on the way out, while the
Python attribute behaves like a normal string/dict. Keeping the logic in a
*field* (not a model property) lets the models stay free of business logic while
call sites keep using plain attribute access (``conn.password``).

Decryption tolerates legacy plaintext values via ``decrypt_value``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from django.db import models

from ._encryption import decrypt_value, encrypt_value

# Django model fields are generic to django-stubs but not subscriptable at
# runtime, so parametrize the base classes only under type checking.
if TYPE_CHECKING:
    _TextBase = models.TextField[str, str]
    _CharBase = models.CharField[str, str]
    _JSONBase = models.TextField[dict[str, str], dict[str, str]]
else:
    _TextBase = models.TextField
    _CharBase = models.CharField
    _JSONBase = models.TextField


class EncryptedTextField(_TextBase):
    """A ``TextField`` whose value is Fernet-encrypted in the database."""

    def from_db_value(self, value: str | None, expression: Any, connection: Any) -> str | None:
        if value is None:
            return value
        return decrypt_value(value)

    def get_prep_value(self, value: Any) -> str | None:
        prepped: str | None = super().get_prep_value(value)
        if prepped is None or prepped == "":
            return prepped
        return encrypt_value(prepped)


class EncryptedCharField(_CharBase):
    """A ``CharField`` whose value is Fernet-encrypted in the database.

    ``max_length`` bounds the *encrypted* ciphertext, so keep it generous
    relative to the plaintext you expect to store.
    """

    def from_db_value(self, value: str | None, expression: Any, connection: Any) -> str | None:
        if value is None:
            return value
        return decrypt_value(value)

    def get_prep_value(self, value: Any) -> str | None:
        prepped: str | None = super().get_prep_value(value)
        if prepped is None or prepped == "":
            return prepped
        return encrypt_value(prepped)


class EncryptedJSONField(_JSONBase):
    """A dict-valued field stored as Fernet-encrypted JSON text.

    The Python value is a ``dict[str, str]``; the column holds encrypted JSON.
    Malformed or empty stored values decode to an empty dict.
    """

    def from_db_value(self, value: str | None, expression: Any, connection: Any) -> dict[str, str]:
        if not value:
            return {}
        raw = decrypt_value(value)
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
        if not isinstance(parsed, dict):
            return {}
        return {str(k): str(v) for k, v in parsed.items()}

    def to_python(self, value: Any) -> dict[str, str]:
        if value is None or value == "":
            return {}
        if isinstance(value, dict):
            return {str(k): str(v) for k, v in value.items()}
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}
        return {str(k): str(v) for k, v in parsed.items()} if isinstance(parsed, dict) else {}

    def get_prep_value(self, value: Any) -> str:
        if not value:
            return ""
        return encrypt_value(json.dumps(value))
