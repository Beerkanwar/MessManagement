"""
Serializers for identity, authentication, and device management endpoints.
"""
from rest_framework import serializers


class LoginRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(help_text="Institutional college email address")
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    device_id = serializers.CharField(max_length=255, help_text="Client-generated unique device identifier")
    platform = serializers.ChoiceField(choices=["ANDROID", "IOS", "WEB"], help_text="Client platform")
    app_version = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    device_name = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class RefreshTokenRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField(help_text="256-bit opaque refresh token")


class ChangePasswordRequestSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    new_password = serializers.CharField(write_only=True, style={"input_type": "password"}, min_length=10)


class ForgotPasswordRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(help_text="Account email address")


class VerifyOtpRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(min_length=6, max_length=6, help_text="6-digit numerical OTP code")


class ResetPasswordRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(min_length=6, max_length=6, help_text="6-digit numerical OTP code")
    new_password = serializers.CharField(write_only=True, style={"input_type": "password"}, min_length=10)


class UpdateDeviceMetadataSerializer(serializers.Serializer):
    app_version = serializers.CharField(max_length=50, required=False, allow_blank=True)
    device_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    platform = serializers.ChoiceField(choices=["ANDROID", "IOS", "WEB"], required=False)


class AdminRevokeDeviceSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=5, help_text="Mandatory business reason for device revocation")
