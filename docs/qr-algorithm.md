# QR Attendance Protocol Specification (v1.0)

> **Authority:** SPEC SDD §19–22, SRS §9, ImplementationGuide Phase 6  
> **Status:** APPROVED & LOCKED BY TEST VECTORS (`docs/test-vectors/qr-v1.json`)  
> **Target Audience:** Backend API, Student Mobile App (React Native), Mess Manager Mobile App (React Native)

---

## 1. Protocol Definition

| Step | Rule | Specification Reference |
| :--- | :--- | :--- |
| **Time step** | 30 seconds (parameter `qr.step_seconds`) | SDD §20.1, SRS §9.1 |
| **Counter** | `floor(unix seconds ÷ 30)`, encoded as an 8-byte unsigned integer, big-endian (`>Q`) | SDD §20.1 |
| **MAC** | HMAC-SHA256 with the student's secret (32 bytes) as key and the 8 counter bytes as message (32 bytes output) | SDD §20.2, SRS §9.1 |
| **Offset** | Low 4 bits of the last MAC byte (`mac[-1] & 0x0F`), resulting in an integer from 0 to 15 | SDD §20.3 |
| **Truncate** | 4 bytes starting at offset, top bit cleared (`& 0x7FFFFFFF`), read as an unsigned 31-bit integer | SDD §20.3 |
| **Code** | `truncated % 1,000,000`, formatted as a string left-padded with zeros to 6 digits (`000000`–`999999`) | SDD §20.3 |
| **Payload** | `RollNumber\|Code` (single ASCII pipe delimiter, no spaces, no names, no email, no secrets) | SDD §20.4, SRS §9 |
| **Verify** | Manager computes the code for counters $c-1$, $c$, and $c+1$ from its trusted time anchor (setting `qr.window_steps = 1`) and accepts if any matches; comparison performed in constant time | SDD §20.4, SDD §22 |

---

## 2. Trust Model & Clock Skew (SDD §22)

1. **Student Clock is Untrusted**: The student phone clock only determines which dynamic code is rendered on screen. Changing the device clock on a student phone does not grant access.
2. **Manager Trusted Time Authority**: The Mess Manager verifies codes against its server-anchored trusted time (monotonic elapsed clock + synchronization anchor).
3. **Tolerance Window**: A tolerance of $\pm 1$ step (30 seconds before and 30 seconds after current time step) accommodates reasonable drift and scan delay. Codes outside this window ($c \pm 2$) are rejected.
4. **Delimiter Invariant**: Roll numbers containing a pipe character (`|`) are rejected at student creation and import (Phase 4 normalization), guaranteeing unambiguous parsing.

---

## 3. Cryptographic Storage & Decryption Points

1. **At Rest**: Secrets are stored only as ciphertext in `StudentSecret.encrypted_secret` using AES-256-GCM.
2. **Single Decryption Points**: Plain secrets exist in memory in exactly two server code paths:
   - Student's own secret fetch: `GET /api/v1/qr/secret` (authenticated student on active device session, throttled, HTTP `Cache-Control: no-store`).
   - Manager synchronization download: `GET /api/v1/sync/bootstrap` or `/api/v1/sync/changes` (authorized active manager for assigned mess).
3. **Sanitization Invariant**: Plain secrets and encrypted ciphertexts never appear in logs, error messages, audit event values, admin views, or model `__str__` methods.

---

## 4. Secret Rotation (DEC-13)

- **Initiator**: Super Admin via `POST /api/v1/qr/rotate` (targets single student, mess, or hostel).
- **Atomic Transition**: Current active secret is set to `status="RETIRED"`, `effective_to=now`, `rotated_by`, and `rotated_at`. New secret is generated with version $n+1$ and set to `status="ACTIVE"`.
- **Change Signalling**: The change cursor `mess:<id>:secrets` is incremented for all affected messes.
- **Audit**: `SECRET_ROTATED` audit event is emitted with student ID and version numbers only (`{"version": old_v}` and `{"version": new_v}`).
- **Sync Propagation**: Managers receive the new secret on their next sync; students receive it on next app launch.

---

## 5. Reference Implementation (Python)

```python
import hashlib
import hmac
import struct

def compute_qr_code(secret_bytes: bytes, unix_time: int, step: int = 30) -> str:
    counter = int(unix_time) // step
    counter_bytes = struct.pack(">Q", counter)
    mac = hmac.new(secret_bytes, counter_bytes, hashlib.sha256).digest()
    offset = mac[-1] & 0x0F
    truncated = struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{truncated % 1_000_000:06d}"

def verify_qr_payload(
    payload: str,
    secret_bytes: bytes,
    trusted_unix_time: int,
    window: int = 1,
    step: int = 30
) -> bool:
    parts = payload.split("|")
    if len(parts) != 2:
        return False
    roll_number, code = parts[0].strip(), parts[1].strip()
    if not roll_number or len(code) != 6 or not code.isdigit():
        return False

    center = int(trusted_unix_time) // step
    for offset in range(-window, window + 1):
        expected = compute_qr_code(secret_bytes, (center + offset) * step, step)
        if hmac.compare_digest(expected, code):
            return True
    return False
```

---

## 6. Test Vectors Contract

All mobile and server implementations must validate against `docs/test-vectors/qr-v1.json`, which contains:
- RFC 4231 HMAC-SHA256 test cases 1 through 7.
- Awkward case TOTP vectors (offset 0, offset 15, MSB set before 31-bit clearing, leading zeros, step boundaries, 32-bit boundary counter).
- Window verification cases ($c, c \pm 1$ accepted; $c \pm 2$ rejected; malformed payloads).

