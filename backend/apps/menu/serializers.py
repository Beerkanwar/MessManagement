"""
Serializers for the menu endpoint group [SPEC DBDD §9, SRS §22, App Flow §3.4].
"""
from rest_framework import serializers

from apps.menu.models import FoodItem, Menu, MenuItem, MenuMeal


class FoodItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = FoodItem
        fields = [
            "food_item_id",
            "name",
            "normalized_name",
            "description",
            "status",
            "version",
        ]


class FoodItemCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, allow_blank=False, trim_whitespace=True)
    description = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=2000
    )


class FoodItemUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    name = serializers.CharField(
        required=False, allow_blank=False, max_length=255, trim_whitespace=True
    )
    description = serializers.CharField(
        required=False, allow_blank=True, max_length=2000
    )

    def validate(self, attrs):
        if attrs.get("name") is None and attrs.get("description") is None:
            raise serializers.ValidationError(
                "At least one of 'name' or 'description' is required."
            )
        return attrs


class FoodItemDeactivateSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)


class MenuSerializer(serializers.ModelSerializer):
    hostel_code = serializers.CharField(source="hostel.code", read_only=True)

    class Meta:
        model = Menu
        fields = [
            "menu_id",
            "hostel_id",
            "hostel_code",
            "menu_year",
            "menu_month",
            "status",
            "published_at",
            "published_by_user_id",
            "version",
        ]


class MenuCreateSerializer(serializers.Serializer):
    hostel_id = serializers.IntegerField(min_value=1)
    year = serializers.IntegerField(min_value=2000, max_value=2100)
    month = serializers.IntegerField(min_value=1, max_value=12)


class MenuItemInputSerializer(serializers.Serializer):
    food_item_id = serializers.IntegerField(min_value=1)
    display_order = serializers.IntegerField(min_value=1, required=False)
    notes = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=1000
    )


class MenuMealSetSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    menu_date = serializers.DateField()
    meal_type_code = serializers.ChoiceField(
        choices=["BREAKFAST", "LUNCH", "EVENING_SNACKS", "DINNER"]
    )
    items = MenuItemInputSerializer(many=True, allow_empty=True)


class MenuPublishSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)


class MenuCopyPreviousSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)


class MenuItemOutputSerializer(serializers.Serializer):
    menu_item_id = serializers.IntegerField(read_only=True)
    food_item_id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    display_order = serializers.IntegerField(read_only=True)
    notes = serializers.CharField(read_only=True)


class MenuMealOutputSerializer(serializers.Serializer):
    menu_meal_id = serializers.IntegerField(read_only=True)
    meal_type_id = serializers.IntegerField(read_only=True)
    meal_type_code = serializers.CharField(read_only=True)
    meal_type_name = serializers.CharField(read_only=True)
    sequence_no = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    items = MenuItemOutputSerializer(many=True, read_only=True)


class MenuDayOutputSerializer(serializers.Serializer):
    date = serializers.DateField(read_only=True)
    meals = MenuMealOutputSerializer(many=True, read_only=True)


class MenuStructureSerializer(serializers.Serializer):
    """Month -> Date -> Meal -> Items response shape [App Flow §3.4]."""

    menu_id = serializers.IntegerField(read_only=True)
    hostel_id = serializers.IntegerField(read_only=True)
    hostel_code = serializers.CharField(read_only=True)
    hostel_name = serializers.CharField(read_only=True)
    year = serializers.IntegerField(read_only=True)
    month = serializers.IntegerField(read_only=True)
    month_label = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    published_at = serializers.DateTimeField(read_only=True, allow_null=True)
    published_by_user_id = serializers.IntegerField(read_only=True, allow_null=True)
    version = serializers.IntegerField(read_only=True)
    days = MenuDayOutputSerializer(many=True, read_only=True)


class HostelSummarySerializer(serializers.Serializer):
    hostel_id = serializers.IntegerField(read_only=True)
    code = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)


class MenuPublishResultSerializer(serializers.Serializer):
    menu = MenuStructureSerializer(read_only=True)
    warnings = serializers.ListField(child=serializers.CharField(), read_only=True)


class CurrentMenuSerializer(serializers.Serializer):
    student_id = serializers.IntegerField(read_only=True)
    hostel = HostelSummarySerializer(read_only=True)
    months = MenuStructureSerializer(many=True, read_only=True)
