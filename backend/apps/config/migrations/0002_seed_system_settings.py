"""
Data migration seeding institutional SystemSetting parameters [DBDD §21, DEC-11, DEC-06, DEC-07].
Idempotent: uses update_or_create.
"""
from django.db import migrations
from django.utils import timezone


SYSTEM_SETTINGS = [
    # DEC-11 Institutional Parameters
    ("auth.password.min_length", "10", "INTEGER", "Minimum length for user passwords", False),
    ("auth.otp.length", "6", "INTEGER", "Number of digits in password reset OTP", False),
    ("auth.otp.validity_minutes", "10", "INTEGER", "Validity duration of password reset OTP in minutes", False),
    ("auth.otp.max_attempts", "5", "INTEGER", "Maximum failed OTP attempts before invalidation", False),
    ("auth.otp.resend_cooldown_seconds", "60", "INTEGER", "Cooldown period between OTP resend requests in seconds", False),
    ("auth.otp.max_per_hour_per_email", "5", "INTEGER", "Maximum OTP requests per email per hour", False),
    ("auth.login.max_failures", "5", "INTEGER", "Failed login attempts before temporary lockout", False),
    ("auth.login.lockout_minutes", "15", "INTEGER", "Lockout duration after repeated failed logins in minutes", False),
    ("attendance.correction_window_hours", "48", "INTEGER", "Window after MealDate within which corrections may be submitted", False),
    ("time.trusted_anchor_max_age_hours", "48", "INTEGER", "Maximum age of trusted-time server anchor before expiry", False),
    ("time.trusted_anchor_expiring_hours", "6", "INTEGER", "Window before expiry when trusted-time enters EXPIRING state", False),
    ("qr.step_seconds", "30", "INTEGER", "Time-step interval for dynamic QR HMAC counter in seconds", False),
    ("qr.window_steps", "1", "INTEGER", "Verification step window tolerance (±1 step)", False),
    ("offline.normal_hours", "24", "INTEGER", "Normal allowed offline operational duration in hours", False),
    ("offline.grace_hours", "24", "INTEGER", "Additional grace period for offline operation in hours", False),
    ("sync.batch_max_transactions", "500", "INTEGER", "Maximum transactions accepted per sync batch [D11]", False),
    ("billing.period_lock_window_days", "2", "INTEGER", "Days after month end when billing period moves to LOCKED", False),

    # DEC-06 Meal End Times (IST)
    ("meal.BREAKFAST.end_time", "10:00", "TIME", "Breakfast service end time in IST", False),
    ("meal.LUNCH.end_time", "14:30", "TIME", "Lunch service end time in IST", False),
    ("meal.EVENING_SNACKS.end_time", "18:30", "TIME", "Evening snacks service end time in IST", False),
    ("meal.DINNER.end_time", "22:00", "TIME", "Dinner service end time in IST", False),

    # DEC-07 Rollover Time
    ("meal.rollover_time", "03:00", "TIME", "Midnight shift rollover time in IST", False),
]


def seed_settings(apps, schema_editor):
    SystemSetting = apps.get_model("config", "SystemSetting")
    now = timezone.now()
    for key, value, data_type, description, is_sensitive in SYSTEM_SETTINGS:
        SystemSetting.objects.update_or_create(
            key=key,
            effective_from=now,
            defaults={
                "value": value,
                "data_type": data_type,
                "description": description,
                "is_sensitive": is_sensitive,
                "version": 1,
            },
        )


def reverse_seed(apps, schema_editor):
    SystemSetting = apps.get_model("config", "SystemSetting")
    keys = [item[0] for item in SYSTEM_SETTINGS]
    SystemSetting.objects.filter(key__in=keys).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("config", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_settings, reverse_code=reverse_seed),
    ]
