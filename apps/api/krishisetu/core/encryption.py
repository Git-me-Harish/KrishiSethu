"""Field-level encryption for PII at rest.

Provides AES-256-GCM authenticated encryption for sensitive database columns.
This is the second layer of defense beyond database-level encryption at rest
(EBS volume encryption, pgcrypto for column-level encryption at the DB layer).

What gets encrypted:
- Aadhaar number references (we already store SHA-256 hashes; the raw value
  is encrypted during the brief window between UIDAI e-KYC response and
  hash computation, if it must be persisted for any reason — e.g. audit log)
- Bank account numbers (insurance payout, supplier payouts)
- IFSC codes (when paired with bank account)
- GSTIN (suppliers) — though we hash for lookup, the full value is encrypted
  for display to authorized users only
- Phone numbers in audit logs (for contextual display)

Design:
- AES-256-GCM via the `cryptography` library (FIPS-validated on FIPS-mode
  OpenSSL builds).
- Each ciphertext carries: 12-byte nonce || ciphertext || 16-byte GCM tag.
- Nonce is cryptographically random per encryption (never reused with same key).
- Key is loaded from settings.ENCRYPTION_KEY (32 bytes, base64-encoded).
- Key rotation is supported via settings.ENCRYPTION_KEY_PREVIOUS — old keys
  are tried for decryption when the primary key fails.

Usage:
    from krishisetu.core.encryption import encrypt_field, decrypt_field

    # In a service:
    bank_account_encrypted = encrypt_field(raw_account_number)
    # store bank_account_encrypted in DB

    # When reading back:
    raw_account_number = decrypt_field(bank_account_encrypted)

For SQLAlchemy columns, prefer the EncryptedType pattern (custom TypeDecorator)
rather than calling these helpers inline — see EncryptedString in this module.
"""

from __future__ import annotations

import base64
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import String, TypeDecorator
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from krishisetu.core.config import settings
from krishisetu.core.exceptions import KrishiSetuError
from krishisetu.core.logging import get_logger

logger = get_logger(__name__)

# Nonce size for AES-GCM (96 bits is the recommended length per NIST SP 800-38D)
_NONCE_SIZE = 12
# AES-256 key size in bytes
_KEY_SIZE = 32


class EncryptionError(KrishiSetuError):
    """Raised when encryption/decryption fails."""

    def __init__(self, message: str = "Encryption operation failed") -> None:
        super().__init__(code="ENCRYPTION_ERROR", message=message, status_code=500)


def _load_key(secret: str) -> bytes:
    """Load a base64-encoded 32-byte AES key from a secret string.

    Accepts:
    - base64-encoded 32 raw bytes (standard)
    - 32-byte UTF-8 string (less secure but useful for dev)

    Raises EncryptionError if the key is not the correct length.
    """
    try:
        decoded = base64.b64decode(secret, validate=True)
        if len(decoded) == _KEY_SIZE:
            return decoded
    except Exception as exc:
        logger.debug("encryption.key_not_base64", error=str(exc))

    raw_bytes = secret.encode("utf-8")
    if len(raw_bytes) != _KEY_SIZE:
        raise EncryptionError(
            f"ENCRYPTION_KEY must decode to {_KEY_SIZE} bytes, got {len(raw_bytes)}"
        )
    return raw_bytes


def _get_primary_key() -> bytes:
    """Get the primary encryption key (cached)."""
    s = settings()
    if not s.ENCRYPTION_KEY:
        raise EncryptionError("ENCRYPTION_KEY not configured")
    return _load_key(s.ENCRYPTION_KEY.get_secret_value())


def _get_previous_keys() -> list[bytes]:
    """Get previous encryption keys for rotation support (cached)."""
    s = settings()
    keys: list[bytes] = []
    if s.ENCRYPTION_KEY_PREVIOUS:
        for k in s.ENCRYPTION_KEY_PREVIOUS:
            try:
                keys.append(_load_key(k.get_secret_value()))
            except EncryptionError as e:
                logger.warning("encryption.previous_key_invalid", error=str(e))
    return keys


def encrypt_field(plaintext: str | None) -> str | None:
    """Encrypt a string field using AES-256-GCM.

    Returns a base64-encoded string of: nonce || ciphertext || tag.
    Returns None if input is None (preserves NULL semantics).

    Raises EncryptionError if the key is missing or invalid.
    """
    if plaintext is None:
        return None

    if not isinstance(plaintext, str):
        raise EncryptionError(
            f"encrypt_field expects str or None, got {type(plaintext).__name__}"
        )

    key = _get_primary_key()
    nonce = os.urandom(_NONCE_SIZE)
    aesgcm = AESGCM(key)

    try:
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    except Exception as e:
        logger.error("encryption.encrypt_failed", error=str(e))
        raise EncryptionError("Failed to encrypt field") from e

    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt_field(ciphertext_b64: str | None) -> str | None:
    """Decrypt a string field previously encrypted with encrypt_field().

    Tries the primary key first, then any previous keys (for rotation).
    Returns None if input is None.

    Raises EncryptionError if decryption fails with all available keys.
    """
    if ciphertext_b64 is None:
        return None

    if not isinstance(ciphertext_b64, str):
        raise EncryptionError(
            f"decrypt_field expects str or None, got {type(ciphertext_b64).__name__}"
        )

    try:
        raw = base64.b64decode(ciphertext_b64, validate=True)
    except Exception as e:
        raise EncryptionError("Invalid ciphertext encoding") from e

    if len(raw) < _NONCE_SIZE + 16:  # nonce + minimum GCM tag
        raise EncryptionError("Ciphertext too short")

    nonce = raw[:_NONCE_SIZE]
    ct = raw[_NONCE_SIZE:]

    # Try primary key, then previous keys (for rotation)
    keys_to_try = [_get_primary_key(), *_get_previous_keys()]
    last_error: Exception | None = None

    for key in keys_to_try:
        aesgcm = AESGCM(key)
        try:
            plaintext = aesgcm.decrypt(nonce, ct, None)
            return plaintext.decode("utf-8")
        except Exception as e:
            last_error = e
            continue

    logger.error("encryption.decrypt_failed", error=str(last_error))
    raise EncryptionError("Failed to decrypt field with any available key")


def is_encrypted(value: Any) -> bool:
    """Heuristic check: does this value look like an encrypted blob?

    Used by data-export code to decide whether to decrypt a column before
    including it in the export. Not foolproof — a value that happens to be
    valid base64 of length >= 28 will match.
    """
    if not isinstance(value, str) or len(value) < 40:
        return False
    try:
        base64.b64decode(value, validate=True)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# SQLAlchemy custom type — transparent encryption at the ORM layer
# ---------------------------------------------------------------------------


class EncryptedString(TypeDecorator[str | None]):
    """SQLAlchemy column type that transparently encrypts on write and
    decrypts on read.

    Usage:
        from krishisetu.core.encryption import EncryptedString

        class SupplierProfile(Base):
            __tablename__ = "supplier_profiles"
            ...
            gstin_encrypted: Mapped[str | None] = mapped_column(
                EncryptedString(512), nullable=True
            )

    The underlying DB column is VARCHAR(512) to accommodate the base64-encoded
    ciphertext (which is ~33% larger than the plaintext plus 28 bytes for
    nonce+tag).

    Limitations:
    - Cannot be indexed (encrypted values are not deterministic).
      For lookups, use a separate hashed column (e.g. gstin_hash).
    - Equality queries must be done in Python after decryption.
    """

    impl = String
    cache_ok = True

    def __init__(self, length: int = 512, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, length=length, **kwargs)

    def process_bind_param(self, value: str | None, dialect: Any) -> str | None:
        """Encrypt on write."""
        return encrypt_field(value)

    def process_result_value(self, value: str | None, dialect: Any) -> str | None:
        """Decrypt on read."""
        if value is None:
            return None
        try:
            return decrypt_field(value)
        except EncryptionError:
            # Return raw value if decryption fails — better than crashing the
            # entire query. Log it loudly so we can investigate.
            logger.error("encryption.orm_decrypt_failed", value_preview=value[:10])
            return None


# Convenience: a UUID type that is encrypted at rest (rarely needed, but used
# for highly sensitive identifier references in audit logs).
class EncryptedUUID(TypeDecorator[str | None]):
    """Like EncryptedString but for UUID columns (stored as encrypted base64)."""

    impl = String
    cache_ok = True

    def __init__(self, length: int = 256, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, length=length, **kwargs)

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        return encrypt_field(str(value))

    def process_result_value(self, value: str | None, dialect: Any) -> str | None:
        if value is None:
            return None
        try:
            return decrypt_field(value)
        except EncryptionError:
            return None


# Re-export PGUUID so callers don't accidentally import the wrong UUID
__all__ = [
    "PGUUID",
    "EncryptedString",
    "EncryptedUUID",
    "EncryptionError",
    "decrypt_field",
    "encrypt_field",
    "is_encrypted",
]
