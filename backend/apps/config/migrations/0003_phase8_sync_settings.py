"""
Phase 8: seed the synchronization settings added by the guide.

Idempotent ``update_or_create`` keyed on (key, effective_from) so environments
that already run keep their configured values.
"""
from django.db import migrations
from django.utils import timezone

SYSTEM_SETTINGS = [
    (
        "sync.overlap_minutes",
        "2",
        "INTEGER",
        "Overlap window before the cursor issue time for late commits",
        False,
    ),
    (
        "sync.student_page_size",
        "500",
        "INTEGER",
        "Students per bootstrap sync page",
        False,
    ),
    (
        "sync.attendance_window_days",
        "3",
        "INTEGER",
        "Days of effective attendance returned in the sync download",
        False,
    ),
    (
        "sync.rate_limit_per_minute",
        "6",
        "INTEGER",
        "Maximum sync calls per device per minute",
        False,
    ),
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
    SystemSetting.objects.filter(
        key__in=[item[0] for item in SYSTEM_SETTINGS]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("config", "0002_seed_system_settings"),
    ]

    operations = [
        migrations.RunPython(seed_settings, reverse_code=reverse_seed),
    ]
