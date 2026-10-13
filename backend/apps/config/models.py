"""
System configuration models matching SPEC DBDD §12.
SystemSetting stores all configurable parameters (DEC-11 defaults, meal times, etc.).
ApplicationVersionPolicy controls mobile app version enforcement.
"""
from django.db import models
from apps.core.models import VersionedModel


class SystemSetting(VersionedModel):
    """
    Key-value configuration store with effective dating [SPEC DBDD §12].
    Each setting change creates a new effective-dated row; history is never edited.
    Seeds: DEC-11 parameters, DEC-06 meal end times, DEC-07 rollover time.
    """
    setting_id = models.AutoField(primary_key=True)
    key = models.CharField(
        max_length=255,
        help_text="Setting identifier (dot-notation, e.g. 'meal.BREAKFAST.end_time')"
    )
    value = models.TextField(help_text="Setting value as string (interpreted per data_type)")
    data_type = models.CharField(
        max_length=50,
        help_text="Type hint for value interpretation: STRING, INTEGER, BOOLEAN, DECIMAL, DURATION, TIME"
    )
    description = models.TextField(blank=True, default="", help_text="Human-readable description")
    is_sensitive = models.BooleanField(
        default=False,
        help_text="If true, value is masked in logs and API responses"
    )
    effective_from = models.DateTimeField(help_text="When this setting value becomes active (UTC)")

    class Meta:
        db_table = "config_system_setting"
        verbose_name = "System Setting"
        verbose_name_plural = "System Settings"
        ordering = ["key", "-effective_from"]
        constraints = [
            models.UniqueConstraint(
                fields=["key", "effective_from"],
                name="uq_config_system_setting_key_effective",
            ),
        ]
        indexes = [
            models.Index(fields=["key", "-effective_from"], name="idx_config_setting_key_eff"),
        ]

    def __str__(self):
        return f"{self.key} = {self.value} (from {self.effective_from})"


class ApplicationVersionPolicy(VersionedModel):
    """
    Mobile application version enforcement policy [SPEC DBDD §12].
    Status controls client behavior: SUPPORTED (normal), DEPRECATED (update banner),
    BLOCKED (refuses sync and manager login) [DEC-18].
    """
    PLATFORM_CHOICES = [
        ("ANDROID", "Android"),
        ("IOS", "iOS"),
        ("WEB", "Web"),
    ]
    STATUS_CHOICES = [
        ("SUPPORTED", "Supported"),
        ("DEPRECATED", "Deprecated"),
        ("BLOCKED", "Blocked"),
    ]

    policy_id = models.AutoField(primary_key=True)
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, help_text="Target platform")
    app_version = models.CharField(
        max_length=50,
        help_text="Semantic version string (e.g. '1.0.0')"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, help_text="Enforcement status")
    force_update_message = models.TextField(
        blank=True, default="",
        help_text="Message shown to users when update is required"
    )

    class Meta:
        db_table = "config_application_version_policy"
        verbose_name = "Application Version Policy"
        verbose_name_plural = "Application Version Policies"
        constraints = [
            models.UniqueConstraint(
                fields=["platform", "app_version"],
                name="uq_config_app_version_platform_version",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["SUPPORTED", "DEPRECATED", "BLOCKED"]),
                name="config_app_version_status_check",
            ),
        ]

    def __str__(self):
        return f"{self.platform} v{self.app_version} ({self.status})"
