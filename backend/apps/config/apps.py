from django.apps import AppConfig


class SystemConfig(AppConfig):
    default_auto_field = "django.db.models.AutoField"
    name = "apps.config"
    verbose_name = "System Configuration"
