"""
Serializers for QR endpoints [SPEC SDD §19-21, ImplementationGuide Phase 6].
"""
from rest_framework import serializers


class StudentSecretResponseSerializer(serializers.Serializer):
    """
    Response payload for GET /api/v1/qr/secret [SPEC SDD §21].
    Contains secret material delivered exclusively to the student over HTTPS.
    """
    secret_version = serializers.IntegerField(
        help_text="Active secret version number"
    )
    secret = serializers.CharField(
        help_text="Base64-encoded 32-byte secret key material"
    )
    effective_from = serializers.DateTimeField(
        help_text="Timestamp when secret version became effective (UTC)"
    )


class RotateSecretRequestSerializer(serializers.Serializer):
    """
    Request payload for POST /api/v1/qr/rotate (Super Admin only).
    """
    student_id = serializers.IntegerField(
        required=False, allow_null=True,
        help_text="ID of single student to rotate"
    )
    hostel_id = serializers.IntegerField(
        required=False, allow_null=True,
        help_text="ID of hostel whose students to rotate"
    )
    mess_id = serializers.IntegerField(
        required=False, allow_null=True,
        help_text="ID of mess whose students to rotate"
    )
    reason = serializers.CharField(
        required=True, min_length=1, max_length=500,
        help_text="Mandatory operational reason for rotation"
    )

    def validate(self, attrs):
        s_id = attrs.get("student_id")
        h_id = attrs.get("hostel_id")
        m_id = attrs.get("mess_id")
        if s_id is None and h_id is None and m_id is None:
            raise serializers.ValidationError(
                "At least one target must be provided: student_id, hostel_id, or mess_id."
            )
        return attrs


class SecretRotationItemSerializer(serializers.Serializer):
    student_id = serializers.IntegerField()
    roll_number = serializers.CharField()
    old_version = serializers.IntegerField(allow_null=True)
    new_version = serializers.IntegerField()


class RotateSecretResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    affected_count = serializers.IntegerField()
    rotations = SecretRotationItemSerializer(many=True)

