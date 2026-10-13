"""
Custom User model for Hostel Mess Management System.
Implements SPEC DBDD §3 columns and Phase 1 conventions.
Set as AUTH_USER_MODEL prior to initial migrations.
"""
from typing import Any
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models


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
