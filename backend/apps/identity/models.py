"""
Custom User model and identity-related models for Hostel Mess Management System.
Implements SPEC DBDD §3 and §13 columns.
User model set as AUTH_USER_MODEL prior to initial migrations (Phase 1).
Phase 2 additions: Role, UserRole, DeviceRegistration, RefreshToken,
PasswordResetToken, StudentSecret.
"""
from typing import Any
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from apps.core.models import TimeStampedModel, VersionedModel


class UserManager(BaseUserManager):
    """Custom user manager handling email normalization and User creation."""

    def create_user(self, email: str, password: str | None = None, **extra_fields: Any) -> "User":
        if not email:
            raise ValueError("The Email field must be provided.")
        email = self.normalize_email(email)
        normalized_email = email.strip().lower()
        extra_fields.setdefault("status", "ACTIVE")

        user = self.model(
            email=email,
            normalized_email=normalized_email,
            **extra_fields,
        )
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str | None = None, **extra_fields: Any) -> "User":
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("status", "ACTIVE")

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Primary User model matching SPEC DBDD §3:
    user_id (AutoField PK), email, normalized_email, password, full_name,
    phone_number, status, last_login_at, created_at, updated_at, version.
    """
    user_id = models.AutoField(
        primary_key=True,
        help_text="Surrogate primary key matching DBDD §3 UserId"
    )
    email = models.EmailField(
        max_length=255,
        help_text="Raw institutional email address"
    )
    normalized_email = models.EmailField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Trimmed and lowercased email for lookups and uniqueness"
    )
    full_name = models.CharField(
        max_length=150,
        help_text="User's full display name"
    )
    phone_number = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Contact telephone number"
    )

    STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("INACTIVE", "Inactive"),
        ("LOCKED", "Locked"),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="ACTIVE",
        help_text="Account lifecycle state (DEC-02)"
    )

    # last_login maps to LastLoginAt in database [DBDD §3, ImplementationGuide Phase 1]
    last_login = models.DateTimeField(
        null=True,
        blank=True,
        db_column="last_login_at",
        help_text="Timestamp of most recent successful login (UTC)"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Account creation timestamp (UTC)"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Account last update timestamp (UTC)"
    )
    version = models.BigIntegerField(
        default=1,
        help_text="Optimistic concurrency control version counter [DBDD §18.3]"
    )

    # Django administrative access flags
    is_staff = models.BooleanField(
        default=False,
        help_text="Designates whether the user can log into the Django admin site."
    )

    # Note: groups and user_permissions are provided by PermissionsMixin if needed
    objects = UserManager()

    USERNAME_FIELD = "normalized_email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["email", "full_name"]

    class Meta:
        db_table = "identity_user"
        verbose_name = "User"
        verbose_name_plural = "Users"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["ACTIVE", "INACTIVE", "LOCKED"]),
                name="identity_user_status_check",
            ),
        ]
        indexes = [
            models.Index(fields=["normalized_email"], name="idx_identity_user_norm_email"),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} <{self.normalized_email}>"

    @property
    def is_active(self) -> bool:
        """Integration with Django auth: active when status == ACTIVE."""
        return self.status == "ACTIVE"

    @property
    def last_login_at(self):
        return self.last_login

    @last_login_at.setter
    def last_login_at(self, value):
        self.last_login = value


# ---------------------------------------------------------------------------
# Phase 2 models below — Role, UserRole, DeviceRegistration, RefreshToken,
# PasswordResetToken, StudentSecret
# ---------------------------------------------------------------------------


class Role(TimeStampedModel):
    """
    Predefined application roles [SPEC DBDD §3].
    Seeded: STUDENT, MESS_MANAGER, HOSTEL_CLERK, SUPER_ADMIN.
    """
    role_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50, unique=True, help_text="Role code (e.g. SUPER_ADMIN)")
    description = models.TextField(blank=True, default="")

    class Meta:
        db_table = "identity_role"
        verbose_name = "Role"
        verbose_name_plural = "Roles"

    def __str__(self):
        return self.name


class UserRole(models.Model):
    """
    User-role assignment [SPEC DBDD §3].
    Surrogate key [REC] for Django admin compatibility with composite keys.
    DEC-20: v1 enforces exactly one role per user in the service layer.
    """
    user_role_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="user_roles")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="user_roles")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "identity_user_role"
        verbose_name = "User Role"
        verbose_name_plural = "User Roles"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "role"],
                name="uq_identity_user_role",
            ),
        ]

    def __str__(self):
        return f"{self.user} -> {self.role}"


class DeviceRegistration(VersionedModel):
    """
    Device registration and session tracking [SPEC DBDD §3].
    Single active device per user enforced by partial unique constraint.
    SessionStatus flow: ACTIVE -> REPLACED|REVOKE_PENDING_SYNC|REVOKED|LOGGED_OUT.
    """
    SESSION_STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("REPLACED", "Replaced"),
        ("REVOKE_PENDING_SYNC", "Revoke Pending Sync"),
        ("REVOKED", "Revoked"),
        ("LOGGED_OUT", "Logged Out"),
    ]
    PLATFORM_CHOICES = [
        ("ANDROID", "Android"),
        ("IOS", "iOS"),
        ("WEB", "Web"),
    ]

    device_registration_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="device_registrations")
    device_id = models.CharField(max_length=255, help_text="Client-generated device identifier")
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    device_name = models.CharField(max_length=255, blank=True, default="")
    app_version = models.CharField(max_length=50, blank=True, default="")
    session_status = models.CharField(
        max_length=30, choices=SESSION_STATUS_CHOICES, default="ACTIVE"
    )
    registered_at = models.DateTimeField(help_text="When device was first registered")
    last_active_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoke_reason = models.TextField(blank=True, default="")

    class Meta:
        db_table = "identity_device_registration"
        verbose_name = "Device Registration"
        verbose_name_plural = "Device Registrations"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(session_status__in=[
                    "ACTIVE", "REPLACED", "REVOKE_PENDING_SYNC", "REVOKED", "LOGGED_OUT"
                ]),
                name="identity_device_session_status_check",
            ),
            # Partial unique: at most one ACTIVE device per user [CONFLICT-08]
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(session_status="ACTIVE"),
                name="uq_identity_device_one_active_per_user",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "session_status"], name="idx_ident_dev_user_stat"),
        ]

    def __str__(self):
        return f"{self.user} / {self.platform} ({self.session_status})"


class RefreshToken(models.Model):
    """
    Refresh token tracking [SPEC DBDD §3].
    Only the SHA-256 hash is stored; never the raw token [SPEC SDD §63].
    Rotation with replaced_by chaining; replay detection revokes the chain.
    """
    refresh_token_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="refresh_tokens")
    device_registration = models.ForeignKey(
        DeviceRegistration, on_delete=models.PROTECT, related_name="refresh_tokens"
    )
    token_hash = models.CharField(max_length=512, unique=True, help_text="SHA-256 hash of the token")
    replaced_by = models.ForeignKey(
        "self", on_delete=models.PROTECT,
        null=True, blank=True, related_name="replaces",
        help_text="Points to the successor token in rotation chain"
    )
    expires_at = models.DateTimeField()
    is_revoked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "identity_refresh_token"
        verbose_name = "Refresh Token"
        verbose_name_plural = "Refresh Tokens"
        indexes = [
            models.Index(fields=["token_hash"], name="idx_ident_refr_token_hash"),
            models.Index(fields=["user", "is_revoked"], name="idx_identity_refresh_user_rev"),
        ]


class PasswordResetToken(models.Model):
    """
    Password reset token with OTP [SPEC DBDD §3, DEC-03, DEC-11].
    OTP: 6 digits, 10 min expiry, 5 attempts, resend after 60s, 5 per hour per email.
    """
    password_reset_token_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="password_reset_tokens")
    token_hash = models.CharField(max_length=512, unique=True)
    otp_hash = models.CharField(max_length=512, help_text="Hashed OTP code")
    email = models.EmailField(max_length=255)
    attempts = models.IntegerField(default=0)
    max_attempts = models.IntegerField(default=5)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "identity_password_reset_token"
        verbose_name = "Password Reset Token"
        verbose_name_plural = "Password Reset Tokens"
        indexes = [
            models.Index(fields=["token_hash"], name="idx_identity_prt_token_hash"),
            models.Index(fields=["user", "-created_at"], name="idx_identity_prt_user_time"),
        ]


class StudentSecret(TimeStampedModel):
    """
    Student QR secret for HMAC verification [SPEC DBDD §13, CONFLICT-09].
    Ciphertext column only; plaintext never stored [SPEC SDD §63].
    At most one ACTIVE secret per student; rotation retires the old one (DEC-13).
    """
    STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("RETIRED", "Retired"),
    ]

    student_secret_id = models.AutoField(primary_key=True)
    student = models.ForeignKey(
        "hostel.Student", on_delete=models.PROTECT, related_name="secrets"
    )
    secret_version = models.IntegerField(
        help_text="Monotonically increasing version for rotation"
    )
    encrypted_secret = models.BinaryField(
        help_text="AES-GCM encrypted secret key material"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ACTIVE")

    class Meta:
        db_table = "identity_student_secret"
        verbose_name = "Student Secret"
        verbose_name_plural = "Student Secrets"
        constraints = [
            models.UniqueConstraint(
                fields=["student", "secret_version"],
                name="uq_identity_student_secret_version",
            ),
            # At most one ACTIVE secret per student
            models.UniqueConstraint(
                fields=["student"],
                condition=models.Q(status="ACTIVE"),
                name="uq_identity_student_secret_one_active",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["ACTIVE", "RETIRED"]),
                name="identity_student_secret_status_check",
            ),
        ]

    def __str__(self):
        return f"Secret v{self.secret_version} for student {self.student_id} ({self.status})"
