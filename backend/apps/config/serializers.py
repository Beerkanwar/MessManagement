"""
Serializers for SystemSetting and ApplicationVersionPolicy — Phase 5.
"""
from rest_framework import serializers
from apps.config.models import ApplicationVersionPolicy, SystemSetting


class SystemSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemSetting
        fields = [
            "setting_id",
            "key",
            "value",
            "data_type",
            "description",
            "is_sensitive",
            "effective_from",
            "version",
        ]


class SystemSettingUpdateSerializer(serializers.Serializer):
    key = serializers.CharField(max_length=255, help_text="Dot-notated setting key")
    value = serializers.CharField(help_text="New string value for setting")
    reason = serializers.CharField(
        max_length=500, required=False, allow_blank=True, default="",
        help_text="Audit explanation for change",
    )


class ApplicationVersionPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = ApplicationVersionPolicy
        fields = [
            "policy_id",
            "platform",
            "app_version",
            "status",
            "force_update_message",
            "version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["policy_id", "created_at", "updated_at"]


class ApplicationVersionPolicyCreateSerializer(serializers.Serializer):
    platform = serializers.ChoiceField(choices=["ANDROID", "IOS", "WEB"])
    app_version = serializers.CharField(max_length=50)
    status = serializers.ChoiceField(choices=["SUPPORTED", "DEPRECATED", "BLOCKED"])
    force_update_message = serializers.CharField(required=False, allow_blank=True, default="")


class ApplicationVersionPolicyUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["SUPPORTED", "DEPRECATED", "BLOCKED"])
    force_update_message = serializers.CharField(required=False, allow_blank=True, default="")
    version = serializers.IntegerField(help_text="Optimistic concurrency control version")

