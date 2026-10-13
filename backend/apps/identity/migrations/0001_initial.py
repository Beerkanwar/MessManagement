"""
Initial migration creating custom User model [SPEC DBDD §3].
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="User",
            fields=[
                ("password", models.CharField(max_length=128, verbose_name="password")),
                (
                    "is_superuser",
                    models.BooleanField(
                        default=False,
                        help_text="Designates that this user has all permissions without explicitly assigning them.",
                        verbose_name="superuser status",
                    ),
                ),
                (
                    "user_id",
                    models.AutoField(
                        help_text="Surrogate primary key matching DBDD §3 UserId",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "email",
                    models.EmailField(
                        help_text="Raw institutional email address",
                        max_length=255,
                    ),
                ),
                (
                    "normalized_email",
                    models.EmailField(
                        db_index=True,
                        help_text="Trimmed and lowercased email for lookups and uniqueness",
                        max_length=255,
                        unique=True,
                    ),
                ),
                (
                    "full_name",
                    models.CharField(
                        help_text="User's full display name",
                        max_length=150,
                    ),
                ),
                (
                    "phone_number",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Contact telephone number",
                        max_length=20,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("ACTIVE", "Active"),
                            ("INACTIVE", "Inactive"),
                            ("LOCKED", "Locked"),
                        ],
                        default="ACTIVE",
                        help_text="Account lifecycle state (DEC-02)",
                        max_length=20,
                    ),
                ),
                (
                    "last_login",
                    models.DateTimeField(
                        blank=True,
                        db_column="last_login_at",
                        help_text="Timestamp of most recent successful login (UTC)",
                        null=True,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="Account creation timestamp (UTC)",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        help_text="Account last update timestamp (UTC)",
                    ),
                ),
                (
                    "version",
                    models.BigIntegerField(
                        default=1,
                        help_text="Optimistic concurrency control version counter [DBDD §18.3]",
                    ),
                ),
                (
                    "is_staff",
                    models.BooleanField(
                        default=False,
                        help_text="Designates whether the user can log into the Django admin site.",
                    ),
                ),
                (
                    "groups",
                    models.ManyToManyField(
                        blank=True,
                        help_text="The groups this user belongs to. A user will get all permissions granted to each of their groups.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.group",
                        verbose_name="groups",
                    ),
                ),
                (
                    "user_permissions",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Specific permissions for this user.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.permission",
                        verbose_name="user permissions",
                    ),
                ),
            ],
            options={
                "verbose_name": "User",
                "verbose_name_plural": "Users",
                "db_table": "identity_user",
            },
        ),
        migrations.AddIndex(
            model_name="user",
            index=models.Index(fields=["normalized_email"], name="idx_identity_user_norm_email"),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.CheckConstraint(
                condition=models.Q(status__in=["ACTIVE", "INACTIVE", "LOCKED"]),
                name="identity_user_status_check",
            ),
        ),
    ]
