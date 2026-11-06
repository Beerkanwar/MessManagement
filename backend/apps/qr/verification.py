"""
Verification abstraction layer for meal attendance [SPEC SRS §38, DBDD §6.2].
Decouples meal attendance recording and billing from specific physical/cryptographic verification methods.
Provides:
- VerificationMethod: Supported identification methods (QR_HMAC_SHA256, MANUAL_CORRECTION, RFID, BIOMETRIC).
- VerificationStatus: Granular verification outcome status.
- VerificationResult: Standard immutable verification outcome dataclass.
- BaseAttendanceVerifier: Abstract interface for attendance verifiers.
- QRHMACVerifier: Concrete verifier for dynamic QR HMAC-SHA256 protocol.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

from apps.qr.crypto import parse_payload, verify_qr_payload


class VerificationMethod(str, Enum):
    """Supported meal verification methods [SPEC DBDD §6.2, SRS §38]."""
    QR_HMAC_SHA256 = "QR_HMAC_SHA256"
    MANUAL_CORRECTION = "MANUAL_CORRECTION"
    RFID = "RFID"
    BIOMETRIC = "BIOMETRIC"


class VerificationStatus(str, Enum):
    """Detailed outcome status for verification attempts."""
    SUCCESS = "SUCCESS"
    REJECTED = "REJECTED"
    MALFORMED_PAYLOAD = "MALFORMED_PAYLOAD"
    STUDENT_NOT_FOUND = "STUDENT_NOT_FOUND"
    NO_ACTIVE_SECRET = "NO_ACTIVE_SECRET"
    EXPIRED_WINDOW = "EXPIRED_WINDOW"


@dataclass(frozen=True)
class VerificationResult:
    """Standard result returned by any attendance verifier."""
    is_valid: bool
    method: str
    status: str
    roll_number: str
    counter: int | None = None
    student_id: int | None = None
    message: str = ""


class BaseAttendanceVerifier(ABC):
    """
    Abstract interface for meal verification [SPEC SRS §38].
    Allows future extensions (RFID, NFC, biometric, facial recognition) without altering billing logic.
    """

    @property
    @abstractmethod
    def method_name(self) -> str:
        """Returns the canonical VerificationMethod code."""
        ...

    @abstractmethod
    def verify(self, payload: Any, context: dict[str, Any] | None = None) -> VerificationResult:
        """
        Verifies student credential payload against the given verification context.
        context may provide: trusted_time, secret_bytes, student_lookup, window, etc.
        """
        ...


class QRHMACVerifier(BaseAttendanceVerifier):
    """
    Concrete attendance verifier for dynamic QR codes [SPEC SDD §19-21, SRS §9].
    Accepts QR payload 'RollNumber|TimeCode' and verifies it against student's secret
    using trusted manager time and configurable window tolerance.
    """

    def __init__(self, secret_bytes: bytes | None = None):
        self._secret_bytes = secret_bytes

    @property
    def method_name(self) -> str:
        return VerificationMethod.QR_HMAC_SHA256.value

    def verify(self, payload: Any, context: dict[str, Any] | None = None) -> VerificationResult:
        context = context or {}
        if not isinstance(payload, str):
            return VerificationResult(
                is_valid=False,
                method=self.method_name,
                status=VerificationStatus.MALFORMED_PAYLOAD.value,
                roll_number="",
                message="Payload must be a string",
            )

        try:
            roll_number, code = parse_payload(payload)
        except ValueError as err:
            return VerificationResult(
                is_valid=False,
                method=self.method_name,
                status=VerificationStatus.MALFORMED_PAYLOAD.value,
                roll_number="",
                message=str(err),
            )

        secret_bytes = self._secret_bytes or context.get("secret_bytes")
        if not secret_bytes:
            return VerificationResult(
                is_valid=False,
                method=self.method_name,
                status=VerificationStatus.NO_ACTIVE_SECRET.value,
                roll_number=roll_number,
                message="No student secret key provided for verification",
            )

        unix_time = context.get("unix_time")
        if unix_time is None:
            return VerificationResult(
                is_valid=False,
                method=self.method_name,
                status=VerificationStatus.REJECTED.value,
                roll_number=roll_number,
                message="Trusted verification time (unix_time) is required",
            )

        window = context.get("window", 1)
        step = context.get("step", 30)

        is_valid, matched_counter = verify_qr_payload(
            roll_number=roll_number,
            code=code,
            secret_bytes=secret_bytes,
            unix_time=int(unix_time),
            window=int(window),
            step=int(step),
        )

        if is_valid:
            return VerificationResult(
                is_valid=True,
                method=self.method_name,
                status=VerificationStatus.SUCCESS.value,
                roll_number=roll_number,
                counter=matched_counter,
                student_id=context.get("student_id"),
                message="QR code verified successfully",
            )
        else:
            return VerificationResult(
                is_valid=False,
                method=self.method_name,
                status=VerificationStatus.REJECTED.value,
                roll_number=roll_number,
                student_id=context.get("student_id"),
                message="Time code does not match trusted verification window",
            )

