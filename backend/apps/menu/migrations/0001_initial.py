"""
Initial migration for menu app: FoodItem, Menu, MenuMeal, MenuItem [SPEC DBDD §9].
Enforces:
- UniqueConstraint: (hostel, menu_year, menu_month) on Menu
- UniqueConstraint: (menu, menu_date, meal_type) on MenuMeal
- UniqueConstraint: (menu_meal, food_item) on MenuItem [Invariant 10]
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("core", "0001_btree_gist"),
        ("identity", "0001_initial"),
        ("hostel", "0001_initial"),
        ("mess", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="FoodItem",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when row was last updated (UTC)")),
                ("version", models.BigIntegerField(default=1, help_text="Optimistic concurrency control version counter")),
                ("food_item_id", models.AutoField(primary_key=True, serialize=False)),
                ("name", models.CharField(help_text="Item name", max_length=255)),
                ("normalized_name", models.CharField(help_text="Trimmed and uppercase for uniqueness [DBDD §9]", max_length=255, unique=True)),
                ("description", models.TextField(blank=True, default="")),
                ("status", models.CharField(choices=[("ACTIVE", "Active"), ("INACTIVE", "Inactive")], default="ACTIVE", max_length=20)),
            ],
            options={
                "verbose_name": "Food Item",
                "verbose_name_plural": "Food Items",
                "db_table": "menu_food_item",
            },
        ),
        migrations.CreateModel(
            name="Menu",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when row was last updated (UTC)")),
                ("version", models.BigIntegerField(default=1, help_text="Optimistic concurrency control version counter")),
                ("menu_id", models.AutoField(primary_key=True, serialize=False)),
                ("menu_year", models.IntegerField(help_text="Calendar year")),
                ("menu_month", models.IntegerField(help_text="Calendar month (1-12)")),
                ("status", models.CharField(choices=[("DRAFT", "Draft"), ("PUBLISHED", "Published")], default="DRAFT", max_length=20)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("hostel", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="menus", to="hostel.hostel")),
                ("published_by_user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="published_menus", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Menu",
                "verbose_name_plural": "Menus",
                "db_table": "menu_menu",
            },
        ),
        migrations.CreateModel(
            name="MenuMeal",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when row was created (UTC)")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when row was last updated (UTC)")),
                ("menu_meal_id", models.AutoField(primary_key=True, serialize=False)),
                ("menu_date", models.DateField(help_text="Scheduled date")),
                ("status", models.CharField(choices=[("DRAFT", "Draft"), ("PUBLISHED", "Published")], default="DRAFT", max_length=20)),
                ("meal_type", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="menu_meals", to="mess.mealtype")),
                ("menu", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="meals", to="menu.menu")),
            ],
            options={
                "verbose_name": "Menu Meal",
                "verbose_name_plural": "Menu Meals",
                "db_table": "menu_menu_meal",
            },
        ),
        migrations.CreateModel(
            name="MenuItem",
            fields=[
                ("menu_item_id", models.AutoField(primary_key=True, serialize=False)),
                ("display_order", models.IntegerField(default=1)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("food_item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="menu_items", to="menu.fooditem")),
                ("menu_meal", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="items", to="menu.menumeal")),
            ],
            options={
                "verbose_name": "Menu Item",
                "verbose_name_plural": "Menu Items",
                "db_table": "menu_menu_item",
                "ordering": ["menu_meal", "display_order"],
            },
        ),
        migrations.AddConstraint(
            model_name="fooditem",
            constraint=models.CheckConstraint(condition=models.Q(status__in=["ACTIVE", "INACTIVE"]), name="menu_food_item_status_check"),
        ),
        migrations.AddConstraint(
            model_name="menu",
            constraint=models.UniqueConstraint(fields=["hostel", "menu_year", "menu_month"], name="uq_menu_hostel_year_month"),
        ),
        migrations.AddConstraint(
            model_name="menu",
            constraint=models.CheckConstraint(condition=models.Q(menu_month__gte=1, menu_month__lte=12), name="menu_month_check"),
        ),
        migrations.AddConstraint(
            model_name="menu",
            constraint=models.CheckConstraint(condition=models.Q(status__in=["DRAFT", "PUBLISHED"]), name="menu_status_check"),
        ),
        migrations.AddConstraint(
            model_name="menumeal",
            constraint=models.UniqueConstraint(fields=["menu", "menu_date", "meal_type"], name="uq_menu_meal_menu_date_type"),
        ),
        migrations.AddConstraint(
            model_name="menuitem",
            constraint=models.UniqueConstraint(fields=["menu_meal", "food_item"], name="uq_menu_item_meal_food"),
        ),
    ]
