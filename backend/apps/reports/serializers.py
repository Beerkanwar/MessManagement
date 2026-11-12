"""Serializers documenting the reports catalog contract [Phase 12]."""
from rest_framework import serializers


class ReportColumnSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    type = serializers.CharField()
    money = serializers.BooleanField()


class ReportCatalogEntrySerializer(serializers.Serializer):
    id = serializers.CharField()
    title = serializers.CharField()
    roles = serializers.ListField(child=serializers.CharField())
    filters = serializers.ListField(child=serializers.CharField())
    formats = serializers.ListField(child=serializers.CharField())
    columns = ReportColumnSerializer(many=True)


class ReportCatalogResponseSerializer(serializers.Serializer):
    reports = ReportCatalogEntrySerializer(many=True)


class ReportJsonResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    report = serializers.CharField()
    title = serializers.CharField()
    from_date = serializers.DateField(source="from")
    to_date = serializers.DateField(source="to")
    results = serializers.ListField(child=serializers.DictField())
    totals = serializers.DictField()
    groups = serializers.ListField(child=serializers.DictField())
