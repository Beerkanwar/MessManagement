"""
Serializers for the audit read API [ImplementationGuide Phase 13].
Output is intentionally read-only and never accepts write payloads.
"""
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.audit.models import AuditLog
from apps.audit.services import redact_audit_payload_for_output


class AuditActorSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    email = serializers.EmailField()
    full_name = serializers.CharField()


class AuditEventSerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField()
    device_id = serializers.SerializerMethodField()
    old_values = serializers.SerializerMethodField()
    new_values = serializers.SerializerMethodField()
    metadata = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "audit_id",
            "event_type",
            "occurred_at",
            "actor",
            "device_id",
            "entity_type",
            "entity_id",
            "reason",
            "correlation_id",
            "old_values",
            "new_values",
            "metadata",
        ]
        read_only_fields = fields

    @extend_schema_field(AuditActorSerializer(allow_null=True))
    def get_actor(self, obj):
        if obj.actor_user_id is None:
            return None
        return {
            "user_id": obj.actor_user.user_id,
            "email": obj.actor_user.email,
            "full_name": obj.actor_user.full_name,
        }

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_device_id(self, obj):
        if obj.device_registration_id is None:
            return None
        return obj.device_registration.device_id

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_old_values(self, obj):
        return redact_audit_payload_for_output(obj.old_values_json)

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_new_values(self, obj):
        return redact_audit_payload_for_output(obj.new_values_json)

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_metadata(self, obj):
        return redact_audit_payload_for_output(obj.metadata_json)


class AuditEventPageSerializer(serializers.Serializer):
    """Envelope returned by ``GET /audit/events`` (keyset paging)."""

    count = serializers.IntegerField()
    results = AuditEventSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)
    has_more = serializers.BooleanField()
    limit = serializers.IntegerField()
