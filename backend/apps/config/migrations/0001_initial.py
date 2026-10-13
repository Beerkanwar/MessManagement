"""
Initial migration for config app [SPEC DBDD §12].
Creates SystemSetting and ApplicationVersionPolicy.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("core", "0001_btree_gist"),
    ]

    operations = [
        migrations.CreateModel(
            name="ApplicationVersionPolicy",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when row was last updated (UTC)")),
                ("version", models.BigIntegerField(default=1, help_text="Optimistic concurrency control version counter")),
                ("policy_id", models.AutoField(primary_key=True, serialize=False)),
                ("platform", models.CharField(choices=[("ANDROID", "Android"), ("IOS", "iOS"), ("WEB", "Web")], help_text="Target platform", max_length=20)),
                ("app_version", models.CharField(help_text="Semantic version string (e.g. '1.0.0')", max_length=50)),
                ("status", models.CharField(choices=[("SUPPORTED", "Supported"), ("DEPRECATED", "Deprecated"), ("BLOCKED", "Blocked")], help_text="Enforcement status", max_length=20)),
                ("force_update_message", models.TextField(blank=True, default="", help_text="Message shown to users when update is required")),
            ],
            options={
                "verbose_name": "Application Version Policy",
                "verbose_name_plural": "Application Version Policies",
                "db_table": "config_application_version_policy",
            },
        ),
        migrations.CreateModel(
            name="SystemSetting",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when row was last updated (UTC)")),
                ("version", models.BigIntegerField(default=1, help_text="Optimistic concurrency control version counter")),
                ("setting_id", models.AutoField(primary_key=True, serialize=False)),
                ("key", models.CharField(help_text="Setting identifier (dot-notation, e.g. 'meal.BREAKFAST.end_time')", max_length=255)),
                ("value", models.TextField(help_text="Setting value as string (interpreted per data_type)")),
                ("data_type", models.CharField(help_text="Type hint for value interpretation: STRING, INTEGER, BOOLEAN, DECIMAL, DURATION, TIME", max_length=50)),
                ("description", models.TextField(blank=True, default="", help_text="Human-readable description")),
                ("is_sensitive", models.BooleanField(default=False, help_text="If true, value is masked in logs and API responses")),
                ("effective_from", models.DateTimeField(help_text="When this setting value becomes active (UTC)")),
            ],
            options={
                "verbose_name": "System Setting",
                "verbose_name_plural": "System Settings",
                "db_table": "config_system_setting",
                "ordering": ["key", "-effective_from"],
            },
        ),
        migrations.AddIndex(
            model_name="systemsetting",
            index=models.Index(fields=["key", "-effective_from"], name="idx_config_setting_key_eff"),
        ),
        migrations.AddConstraint(
            model_name="systemsetting",
            constraint=models.UniqueConstraint(fields=["key", "effective_from"], name="uq_config_system_setting_key_effective"),
        ),
        migrations.AddConstraint(
            model_name="applicationversionpolicy",
            constraint=models.UniqueConstraint(fields=["platform", "app_version"], name="uq_config_app_version_platform_version"),
        ),
        migrations.AddConstraint(
            model_name="applicationversionpolicy",
            constraint=models.CheckConstraint(condition=models.Q(status__in=["SUPPORTED", "DEPRECATED", "BLOCKED"]), name="config_app_version_status_check"),
        ),
    ]
