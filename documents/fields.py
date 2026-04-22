"""
Encrypted model fields for sensitive HR data.

Both fields use the same DOCUMENT_ENCRYPTION_KEY (Fernet / AES-256) as the
PDF and upload storage layer, so the entire system shares one key.

Behaviour when DOCUMENT_ENCRYPTION_KEY is NOT set (dev / test):
  - Values are stored as plain JSON / decimal strings — zero behaviour change.

Behaviour when the key IS set:
  - get_prep_value()  → encrypts before writing to DB
  - from_db_value()   → decrypts after reading from DB
  - Fallback: if decryption fails the raw string is returned as-is so that
    rows written before the key was set can still be read (migration window).

Fields intentionally avoid DB-level querying (ORDER BY, filter) on encrypted
columns — that's the expected trade-off for encryption at rest.
"""
import json
from decimal import Decimal, InvalidOperation

from django.db import models


# ---------------------------------------------------------------------------
# Shared Fernet helper
# ---------------------------------------------------------------------------

def _get_fernet():
    """Return a Fernet instance if DOCUMENT_ENCRYPTION_KEY is configured, else None."""
    try:
        from decouple import config
        key = config("DOCUMENT_ENCRYPTION_KEY", default="")
    except Exception:
        key = ""
    if not key:
        return None
    from cryptography.fernet import Fernet
    return Fernet(key.encode() if isinstance(key, str) else key)


def _decrypt_or_raw(fernet, value: str) -> str:
    """
    Attempt Fernet decryption. Return the decrypted string on success,
    or the original value on failure (plaintext fallback during migration).
    """
    try:
        from cryptography.fernet import InvalidToken
        return fernet.decrypt(value.encode()).decode()
    except (Exception,):
        return value


# ---------------------------------------------------------------------------
# EncryptedJSONField
# ---------------------------------------------------------------------------

class EncryptedJSONField(models.TextField):
    """
    Drop-in replacement for JSONField that encrypts the serialised JSON
    blob before writing to the database.

    The Python-side interface is identical to JSONField: reads return dicts/lists,
    writes accept dicts/lists (or JSON strings).
    """

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        fernet = _get_fernet()
        raw = _decrypt_or_raw(fernet, value) if fernet else value
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return value  # Unexpected format — return as-is rather than crash

    def to_python(self, value):
        if isinstance(value, (dict, list)):
            return value
        if value is None:
            return value
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    def get_prep_value(self, value):
        if value is None:
            return value
        json_str = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        fernet = _get_fernet()
        if fernet:
            return fernet.encrypt(json_str.encode()).decode()
        return json_str


# ---------------------------------------------------------------------------
# EncryptedDecimalField
# ---------------------------------------------------------------------------

class EncryptedDecimalField(models.TextField):
    """
    Drop-in replacement for DecimalField that encrypts the string
    representation of the decimal before writing to the database.

    The Python-side interface returns Decimal objects on read.
    Note: DB-level ordering/filtering on this field is not possible when
    encryption is enabled (ciphertext ordering is meaningless).
    """

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        fernet = _get_fernet()
        raw = _decrypt_or_raw(fernet, value) if fernet else str(value)
        try:
            return Decimal(raw.strip())
        except (InvalidOperation, AttributeError, ValueError):
            return None

    def to_python(self, value):
        if isinstance(value, Decimal):
            return value
        if value is None:
            return value
        try:
            return Decimal(str(value).strip())
        except (InvalidOperation, TypeError):
            return None

    def get_prep_value(self, value):
        if value is None:
            return value
        str_val = str(value)
        fernet = _get_fernet()
        if fernet:
            return fernet.encrypt(str_val.encode()).decode()
        return str_val
