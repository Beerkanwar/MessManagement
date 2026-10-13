"""
Phase 2 migration for identity app: Role, UserRole, DeviceRegistration, RefreshToken, PasswordResetToken.
StudentSecret is split into 0003_studentsecret to resolve circular dependency with hostel [DBDD §27].
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("identity", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Role",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when row was last updated (UTC)")),
                ("role_id", models.AutoField(primary_key=True, serialize=False)),
                ("name", models.CharField(help_text="Role code (e.g. SUPER_ADMIN)", max_length=50, unique=True)),
                ("description", models.TextField(blank=True, default="")),
            ],
            options={
                "verbose_name": "Role",
                "verbose_name_plural": "Roles",
                "db_table": "identity_role",
            },
        ),
        migrations.CreateModel(
            name="DeviceRegistration",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when row was last updated (UTC)")),
                ("version", models.BigIntegerField(default=1, help_text="Optimistic concurrency control version counter")),
                ("device_registration_id", models.AutoField(primary_key=True, serialize=False)),
                ("device_id", models.CharField(help_text="Client-generated device identifier", max_length=255)),
                ("platform", models.CharField(choices=[("ANDROID", "Android"), ("IOS", "iOS"), ("WEB", "Web")], max_length=20)),
                ("device_name", models.CharField(blank=True, default="", max_length=255)),
                ("app_version", models.CharField(blank=True, default="", max_length=50)),
                ("session_status", models.CharField(choices=[("ACTIVE", "Active"), ("REPLACED", "Replaced"), ("REVOKE_PENDING_SYNC", "Revoke Pending Sync"), ("REVOKED", "Revoked"), ("LOGGED_OUT", "Logged Out")], default="ACTIVE", max_length=30)),
                ("registered_at", models.DateTimeField(help_text="When device was first registered")),
                ("last_active_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("revoke_reason", models.TextField(blank=True, default="")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="device_registrations", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Device Registration",
                "verbose_name_plural": "Device Registrations",
                "db_table": "identity_device_registration",
            },
        ),
        migrations.CreateModel(
            name="PasswordResetToken",
            fields=[
                ("password_reset_token_id", models.AutoField(primary_key=True, serialize=False)),
                ("token_hash", models.CharField(max_length=512, unique=True)),
                ("otp_hash", models.CharField(help_text="Hashed OTP code", max_length=512)),
                ("email", models.EmailField(max_length=255)),
                ("attempts", models.IntegerField(default=0)),
                ("max_attempts", models.IntegerField(default=5)),
                ("expires_at", models.DateTimeField()),
                ("is_used", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="password_reset_tokens", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Password Reset Token",
                "verbose_name_plural": "Password Reset Tokens",
                "db_table": "identity_password_reset_token",
            },
        ),
        migrations.CreateModel(
            name="RefreshToken",
            fields=[
                ("refresh_token_id", models.AutoField(primary_key=True, serialize=False)),
                ("token_hash", models.CharField(help_text="SHA-256 hash of the token", max_length=512, unique=True)),
                ("expires_at", models.DateTimeField()),
                ("is_revoked", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("device_registration", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="refresh_tokens", to="identity.deviceregistration")),
                ("replaced_by", models.ForeignKey(blank=True, help_text="Points to the successor token in rotation chain", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="replaces", to="identity.refreshtoken")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="refresh_tokens", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Refresh Token",
                "verbose_name_plural": "Refresh Tokens",
                "db_table": "identity_refresh_token",
            },
        ),
        migrations.CreateModel(
            name="UserRole",
            fields=[
                ("user_role_id", models.AutoField(primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("role", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="user_roles", to="identity.role")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="user_roles", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "User Role",
                "verbose_name_plural": "User Roles",
                "db_table": "identity_user_role",
            },
        ),
        migrations.AddIndex(
            model_name="deviceregistration",
            index=models.Index(fields=["user", "session_status"], name="idx_ident_dev_user_stat"),
        ),
        migrations.AddConstraint(
            model_name="deviceregistration",
            constraint=models.CheckConstraint(condition=models.Q(session_status__in=["ACTIVE", "REPLACED", "REVOKE_PENDING_SYNC", "REVOKED", "LOGGED_OUT"]), name="identity_device_session_status_check"),
        ),
        migrations.AddConstraint(
            model_name="deviceregistration",
            constraint=models.UniqueConstraint(condition=models.Q(session_status="ACTIVE"), fields=["user"], name="uq_identity_device_one_active_per_user"),
        ),
        migrations.AddIndex(
            model_name="passwordresettoken",
            index=models.Index(fields=["token_hash"], name="idx_identity_prt_token_hash"),
        ),
        migrations.AddIndex(
            model_name="passwordresettoken",
            index=models.Index(fields=["user", "-created_at"], name="idx_identity_prt_user_time"),
        ),
        migrations.AddIndex(
            model_name="refreshtoken",
            index=models.Index(fields=["token_hash"], name="idx_ident_refr_token_hash"),
        ),
        migrations.AddIndex(
            model_name="refreshtoken",
            index=models.Index(fields=["user", "is_revoked"], name="idx_identity_refresh_user_rev"),
        ),
        migrations.AddConstraint(
            model_name="userrole",
            constraint=models.UniqueConstraint(fields=["user", "role"], name="uq_identity_user_role"),
        ),
    ]
