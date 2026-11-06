"""
Authoritative cryptographic implementation for the dynamic QR meal verification protocol.
Implements:
- AES-256-GCM authenticated encryption at rest for StudentSecret with key rotation support [SPEC SDD §63, ImplementationGuide Phase 6].
- TOTP-like HMAC-SHA256 protocol [SPEC SDD §19-21, SRS §9, ImplementationGuide Phase 6].
- Constant-time window verification [SPEC SDD §22, SRS §9.1].
"""
import hashlib
import hmac
import os
import struct
from typing import Any
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings


class DecryptionError(Exception):
    """Raised when ciphertext cannot be authenticated or decrypted."""
    pass


class SecretEncryptionService:
    """
    Encrypts and decrypts student secret keys at rest using AES-256-GCM.
    Supports key rotation: keys are configured in settings.SECRET_ENCRYPTION_KEYS.
    Ciphertext format:
      - 1 byte: Key ID (unsigned uint8, 1..255)
      - 12 bytes: Random GCM Nonce
      - Remainder: Ciphertext + 16-byte GCM Authentication Tag
    """

    @classmethod
    def get_keys(cls) -> dict[int, bytes]:
        """
        Loads and parses encryption keys from Django settings.
        Returns an ordered dictionary mapping key_id (int) -> 32-byte key (bytes).
        """
        raw_keys = getattr(settings, "SECRET_ENCRYPTION_KEYS", None)
        if not raw_keys:
            # Fallback key derived from settings.SECRET_KEY if not explicitly configured
            derived = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
            return {1: derived}

        keys: dict[int, bytes] = {}
        if isinstance(raw_keys, dict):
            for k, v in raw_keys.items():
                key_id = int(k)
                if isinstance(v, str):
                    key_bytes = bytes.fromhex(v) if len(v) == 64 else v.encode("utf-8")
                elif isinstance(v, (bytes, bytearray)):
                    key_bytes = bytes(v)
                else:
                    raise ValueError(f"Invalid key value type for key_id {key_id}")

                if len(key_bytes) != 32:
                    # Enforce 256-bit key requirement for AES-256
                    key_bytes = hashlib.sha256(key_bytes).digest()
                keys[key_id] = key_bytes
        elif isinstance(raw_keys, (list, tuple)):
            for idx, item in enumerate(raw_keys, start=1):
                if isinstance(item, str):
                    key_bytes = bytes.fromhex(item) if len(item) == 64 else item.encode("utf-8")
                elif isinstance(item, (bytes, bytearray)):
                    key_bytes = bytes(item)
                else:
                    raise ValueError(f"Invalid key value type at index {idx}")

                if len(key_bytes) != 32:
                    key_bytes = hashlib.sha256(key_bytes).digest()
                keys[idx] = key_bytes
        else:
            raise ValueError("SECRET_ENCRYPTION_KEYS must be a dict or list/tuple")

        if not keys:
            raise ValueError("No encryption keys available in SECRET_ENCRYPTION_KEYS")
        return keys

    @classmethod
    def encrypt_secret(cls, plain_bytes: bytes, key_id: int | None = None) -> bytes:
        """
        Encrypts plaintext secret bytes using AES-256-GCM.
        Uses primary key (first key in settings.SECRET_ENCRYPTION_KEYS) unless key_id is specified.
        Returns packed bytes: [key_id (1B)] + [nonce (12B)] + [ciphertext + tag].
        """
        keys = cls.get_keys()
        if key_id is None:
            # First key encrypts [REC]
            key_id, key = next(iter(keys.items()))
        else:
            if key_id not in keys:
                raise ValueError(f"Encryption key id {key_id} not found in configured keys")
            key = keys[key_id]

        if not (1 <= key_id <= 255):
            raise ValueError(f"Key ID must fit in a single byte (1..255), got {key_id}")

        nonce = os.urandom(12)
        aesgcm = AESGCM(key)
        ciphertext_and_tag = aesgcm.encrypt(nonce, plain_bytes, None)
        return struct.pack(">B", key_id) + nonce + ciphertext_and_tag

    @classmethod
    def decrypt_secret(cls, encrypted_bytes: bytes) -> bytes:
        """
        Decrypts AES-256-GCM encrypted secret bytes using the matching key ID prefix.
        Validates GCM authentication tag. Raises DecryptionError on tampering or unknown key.
        """
        if not encrypted_bytes or len(encrypted_bytes) < 29:
            # 1B key_id + 12B nonce + 16B tag = 29B minimum
            raise DecryptionError("Ciphertext payload is too short or malformed")

        key_id = encrypted_bytes[0]
        keys = cls.get_keys()
        key = keys.get(key_id)
        if key is None:
            raise DecryptionError(f"No decryption key available for key id {key_id}")

        nonce = encrypted_bytes[1:13]
        ciphertext_and_tag = encrypted_bytes[13:]

        try:
            aesgcm = AESGCM(key)
            return aesgcm.decrypt(nonce, ciphertext_and_tag, None)
        except Exception as exc:
            raise DecryptionError(f"Authentication/decryption failed: {exc}") from exc


# ---------------------------------------------------------------------------
# TOTP QR Protocol Functions [SPEC SDD §19-21, SRS §9]
# ---------------------------------------------------------------------------

def compute_counter(unix_time: int, step: int = 30) -> int:
    """
    Counter = floor(unix seconds ÷ step).
    Default step is 30 seconds [SPEC SDD §20.1].
    """
    if step <= 0:
        raise ValueError("Time step must be positive")
    return int(unix_time) // step


def counter_to_bytes(counter: int) -> bytes:
    """
    Encodes counter as an 8-byte unsigned integer in big-endian network byte order [SPEC SDD §20.1].
    """
    if counter < 0:
        raise ValueError("Counter cannot be negative")
    return struct.pack(">Q", counter)


def compute_hmac(secret_bytes: bytes, counter_bytes: bytes) -> bytes:
    """
    HMAC-SHA256 with the student's secret key and 8-byte counter message [SPEC SDD §20.2].
    Produces 32-byte digest.
    """
    return hmac.new(secret_bytes, counter_bytes, hashlib.sha256).digest()


def truncate_mac(mac_bytes: bytes) -> tuple[int, int, bool]:
    """
    Dynamic truncation per SPEC SDD §20.3:
    1. Low 4 bits of final MAC byte as offset (0..15).
    2. Extract 4 bytes starting at offset.
    3. Clear most significant bit (interpret as unsigned 31-bit integer).
    Returns (offset, truncated_integer, top_bit_was_set).
    """
    if len(mac_bytes) != 32:
        raise ValueError("MAC digest must be 32 bytes for HMAC-SHA256")

    offset = mac_bytes[-1] & 0x0F
    raw_int = struct.unpack(">I", mac_bytes[offset : offset + 4])[0]
    top_bit_was_set = bool(raw_int & 0x80000000)
    truncated = raw_int & 0x7FFFFFFF
    return offset, truncated, top_bit_was_set


def compute_code(secret_bytes: bytes, counter: int) -> str:
    """
    Computes the deterministic 6-digit TOTP code for a given secret and counter [SPEC SDD §20.3].
    Formula: (truncated_integer % 1,000,000), left-padded with zeros to 6 digits.
    """
    counter_bytes = counter_to_bytes(counter)
    mac = compute_hmac(secret_bytes, counter_bytes)
    _, truncated, _ = truncate_mac(mac)
    code_int = truncated % 1_000_000
    return f"{code_int:06d}"


def compute_code_for_time(secret_bytes: bytes, unix_time: int, step: int = 30) -> str:
    """Computes the 6-digit code for a given timestamp."""
    counter = compute_counter(unix_time, step)
    return compute_code(secret_bytes, counter)


def generate_payload(roll_number: str, secret_bytes: bytes, unix_time: int, step: int = 30) -> str:
    """
    Builds the canonical QR payload: RollNumber|TimeCode [SPEC SDD §20.4, SRS §9].
    Contains no spaces, names, or secret keys.
    """
    code = compute_code_for_time(secret_bytes, unix_time, step)
    return f"{roll_number}|{code}"


def parse_payload(payload: str) -> tuple[str, str]:
    """
    Parses canonical QR payload into (roll_number, code).
    Strictly validates single pipe separator and 6-digit format.
    Raises ValueError on any malformed input.
    """
    if not isinstance(payload, str):
        raise ValueError("QR payload must be a string")

    parts = payload.split("|")
    if len(parts) != 2:
        raise ValueError("Invalid QR payload format: must contain exactly one pipe delimiter")

    roll_number = parts[0].strip()
    code = parts[1].strip()

    if not roll_number:
        raise ValueError("Invalid QR payload: roll number cannot be empty")

    if len(code) != 6 or not code.isdigit():
        raise ValueError("Invalid QR payload: code must be exactly 6 digits")

    return roll_number, code


def verify_qr_payload(
    roll_number: str,
    code: str,
    secret_bytes: bytes,
    unix_time: int,
    window: int = 1,
    step: int = 30,
) -> tuple[bool, int | None]:
    """
    Verifies a 6-digit time code against trusted unix_time within tolerance window (default ±1 step)
    [SPEC SDD §20, ImplementationGuide Phase 6].
    Uses constant-time comparison to prevent timing attacks.
    Returns (is_valid, matched_counter).
    """
    if len(code) != 6 or not code.isdigit():
        return False, None

    center_counter = compute_counter(unix_time, step)
    matched_counter: int | None = None
    is_valid = False

    # Check counters in window: c - window, ..., c + window
    for offset in range(-window, window + 1):
        test_counter = center_counter + offset
        if test_counter < 0:
            continue
        expected_code = compute_code(secret_bytes, test_counter)
        if hmac.compare_digest(expected_code, code):
            is_valid = True
            if matched_counter is None:
                matched_counter = test_counter

    return is_valid, matched_counter

