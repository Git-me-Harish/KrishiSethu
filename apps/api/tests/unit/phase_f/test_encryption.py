"""Unit tests for AES-256-GCM field-level encryption.

Verifies:
- Round-trip: encrypt → decrypt recovers the original plaintext
- Different ciphertexts for the same plaintext (random nonce)
- None handling (preserves NULL semantics)
- Type validation (rejects non-strings)
- Key rotation (previous keys can decrypt old ciphertexts)
- Tamper detection (modifying ciphertext fails decryption)
"""

from __future__ import annotations

import base64

import pytest

from krishisetu.core.encryption import (
    EncryptionError,
    decrypt_field,
    encrypt_field,
    is_encrypted,
)


class TestEncryptionRoundTrip:
    """Encrypt + decrypt should recover the original plaintext."""

    def test_simple_string(self) -> None:
        plaintext = "hello world"
        encrypted = encrypt_field(plaintext)
        assert encrypted is not None
        assert encrypted != plaintext
        assert decrypt_field(encrypted) == plaintext

    def test_empty_string(self) -> None:
        encrypted = encrypt_field("")
        assert decrypt_field(encrypted) == ""

    def test_unicode(self) -> None:
        # Hindi, Tamil, Malayalam, Punjabi, Bengali — the 10 languages we support
        plaintexts = [
            "नमस्ते भारत",          # Hindi
            "வணக்கம் இந்தியா",      # Tamil
            "നമസ്കാരം ഇന്ത്യ",       # Malayalam
            "ਸਤ ਸ੍ਰੀ ਅਕਾਲ ਭਾਰਤ",    # Punjabi
            "নমস্কার ভারত",          # Bengali
            "Farm plot 12.34°N, 78.90°E",  # ASCII + special chars
        ]
        for p in plaintexts:
            encrypted = encrypt_field(p)
            assert decrypt_field(encrypted) == p, f"Failed for: {p}"

    def test_long_string(self) -> None:
        plaintext = "A" * 10_000
        encrypted = encrypt_field(plaintext)
        assert decrypt_field(encrypted) == plaintext

    def test_none_passthrough(self) -> None:
        assert encrypt_field(None) is None
        assert decrypt_field(None) is None


class TestEncryptionRandomNonce:
    """Each encryption of the same plaintext should produce a different ciphertext."""

    def test_different_ciphertexts(self) -> None:
        plaintext = "same plaintext"
        c1 = encrypt_field(plaintext)
        c2 = encrypt_field(plaintext)
        assert c1 != c2  # random nonce ensures this
        # Both should decrypt to the same plaintext
        assert decrypt_field(c1) == plaintext
        assert decrypt_field(c2) == plaintext

    def test_ciphertext_length(self) -> None:
        """Ciphertext = nonce(12) + plaintext + GCM tag(16), base64-encoded."""
        plaintext = "test"
        encrypted = encrypt_field(plaintext)
        raw = base64.b64decode(encrypted)
        expected_min = 12 + len(plaintext.encode()) + 16
        assert len(raw) == expected_min


class TestEncryptionTypeValidation:
    """Type errors should raise EncryptionError, not crash silently."""

    def test_encrypt_rejects_int(self) -> None:
        with pytest.raises(EncryptionError):
            encrypt_field(123)  # type: ignore[arg-type]

    def test_encrypt_rejects_bytes(self) -> None:
        with pytest.raises(EncryptionError):
            encrypt_field(b"raw bytes")  # type: ignore[arg-type]

    def test_decrypt_rejects_int(self) -> None:
        with pytest.raises(EncryptionError):
            decrypt_field(123)  # type: ignore[arg-type]


class TestEncryptionTamperDetection:
    """AES-GCM should detect ciphertext tampering."""

    def test_modified_ciphertext_fails(self) -> None:
        plaintext = "secret data"
        encrypted = encrypt_field(plaintext)
        # Flip a bit in the ciphertext
        raw = bytearray(base64.b64decode(encrypted))
        raw[-1] ^= 0x01  # flip last byte (part of GCM tag)
        tampered = base64.b64encode(bytes(raw)).decode("ascii")
        with pytest.raises(EncryptionError):
            decrypt_field(tampered)

    def test_invalid_base64_fails(self) -> None:
        with pytest.raises(EncryptionError):
            decrypt_field("not valid base64!!!")

    def test_short_ciphertext_fails(self) -> None:
        # Too short to contain nonce + tag
        short = base64.b64encode(b"short").decode("ascii")
        with pytest.raises(EncryptionError):
            decrypt_field(short)


class TestIsEncryptedHeuristic:
    """is_encrypted() is a heuristic — it should not produce false negatives
    on real encrypted values, but may produce false positives on long base64.
    """

    def test_real_encrypted_value_returns_true(self) -> None:
        encrypted = encrypt_field("test")
        assert is_encrypted(encrypted) is True

    def test_short_string_returns_false(self) -> None:
        assert is_encrypted("hello") is False

    def test_none_returns_false(self) -> None:
        assert is_encrypted(None) is False

    def test_non_string_returns_false(self) -> None:
        assert is_encrypted(123) is False  # type: ignore[arg-type]


class TestKeyRotation:
    """Key rotation: old ciphertexts should decrypt with previous keys.

    This is a smoke test — the actual rotation flow is tested in integration
    tests where we can swap the env var.
    """

    def test_decryption_with_primary_key(self) -> None:
        # Encrypt + decrypt with the current primary key
        plaintext = "rotation test"
        encrypted = encrypt_field(plaintext)
        assert decrypt_field(encrypted) == plaintext
