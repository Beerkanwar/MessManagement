"""
Data migration seeding fixed meal types [SPEC DBDD §5, §21].
Idempotent: uses update_or_create.
"""
from django.db import migrations


MEAL_TYPES = [
    ("BREAKFAST", "Breakfast", 1, True, True),
    ("LUNCH", "Lunch", 2, True, True),
    ("EVENING_SNACKS", "Evening Snacks", 3, True, True),
    ("DINNER", "Dinner", 4, True, True),
]


def seed_meal_types(apps, schema_editor):
    MealType = apps.get_model("mess", "MealType")
    for code, name, sequence_no, is_fixed, is_active in MEAL_TYPES:
        MealType.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "sequence_no": sequence_no,
                "is_fixed": is_fixed,
                "is_active": is_active,
            },
        )


def reverse_meal_types(apps, schema_editor):
    table_name = apps.get_model("mess", "MealType")._meta.db_table
    codes = [m[0] for m in MEAL_TYPES]
    placeholders = ", ".join(["%s"] * len(codes))
    schema_editor.execute(
        f'DELETE FROM "{table_name}" WHERE "code" IN ({placeholders})',
        params=codes,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("mess", "0002_extraitem_extraprice"),
    ]

    operations = [
        migrations.RunPython(seed_meal_types, reverse_code=reverse_meal_types),
    ]
