"""
Menu management models matching SPEC DBDD §9.
Implements:
- FoodItem (normalized name unique)
- Menu (hostel-scoped, monthly, status DRAFT/PUBLISHED)
- MenuMeal (menu date and meal type unique)
- MenuItem (no duplicate food item per menu meal [Invariant 10])
"""
from django.conf import settings
from django.db import models
from apps.core.models import TimeStampedModel, VersionedModel


class FoodItem(VersionedModel):
    """Reusable food item master record [SPEC DBDD §9]."""
    STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("INACTIVE", "Inactive"),
    ]

    food_item_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255, help_text="Item name")
    normalized_name = models.CharField(
        max_length=255, unique=True,
        help_text="Trimmed and uppercase for uniqueness [DBDD §9]"
    )
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ACTIVE")

    class Meta:
        db_table = "menu_food_item"
        verbose_name = "Food Item"
        verbose_name_plural = "Food Items"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["ACTIVE", "INACTIVE"]),
                name="menu_food_item_status_check",
            ),
        ]

    def __str__(self):
        return self.name


class Menu(VersionedModel):
    """
    Hostel-scoped monthly menu [SPEC DBDD §9].
    Students see the current published menu for their applicable hostel.
    """
    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("PUBLISHED", "Published"),
    ]

    menu_id = models.AutoField(primary_key=True)
    hostel = models.ForeignKey(
        "hostel.Hostel", on_delete=models.PROTECT, related_name="menus"
    )
    menu_year = models.IntegerField(help_text="Calendar year")
    menu_month = models.IntegerField(help_text="Calendar month (1-12)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="DRAFT")
    published_at = models.DateTimeField(null=True, blank=True)
    published_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="published_menus"
    )

    class Meta:
        db_table = "menu_menu"
        verbose_name = "Menu"
        verbose_name_plural = "Menus"
        constraints = [
            models.UniqueConstraint(
                fields=["hostel", "menu_year", "menu_month"],
                name="uq_menu_hostel_year_month",
            ),
            models.CheckConstraint(
                condition=models.Q(menu_month__gte=1, menu_month__lte=12),
                name="menu_month_check",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["DRAFT", "PUBLISHED"]),
                name="menu_status_check",
            ),
        ]

    def __str__(self):
        return f"Menu Hostel {self.hostel_id} - {self.menu_year}/{self.menu_month:02d} ({self.status})"


class MenuMeal(TimeStampedModel):
    """Meal slot within a monthly menu [SPEC DBDD §9]."""
    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("PUBLISHED", "Published"),
    ]

    menu_meal_id = models.AutoField(primary_key=True)
    menu = models.ForeignKey(Menu, on_delete=models.PROTECT, related_name="meals")
    menu_date = models.DateField(help_text="Scheduled date")
    meal_type = models.ForeignKey(
        "mess.MealType", on_delete=models.PROTECT, related_name="menu_meals"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="DRAFT")

    class Meta:
        db_table = "menu_menu_meal"
        verbose_name = "Menu Meal"
        verbose_name_plural = "Menu Meals"
        constraints = [
            models.UniqueConstraint(
                fields=["menu", "menu_date", "meal_type"],
                name="uq_menu_meal_menu_date_type",
            ),
        ]

    def __str__(self):
        return f"{self.menu_date} {self.meal_type_id} (Menu {self.menu_id})"


class MenuItem(models.Model):
    """
    Food items assigned to a specific menu meal [SPEC DBDD §9, Invariant 10].
    No duplicate FoodItem within the same MenuMeal.
    """
    menu_item_id = models.AutoField(primary_key=True)
    menu_meal = models.ForeignKey(MenuMeal, on_delete=models.PROTECT, related_name="items")
    food_item = models.ForeignKey(FoodItem, on_delete=models.PROTECT, related_name="menu_items")
    display_order = models.IntegerField(default=1)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "menu_menu_item"
        verbose_name = "Menu Item"
        verbose_name_plural = "Menu Items"
        ordering = ["menu_meal", "display_order"]
        constraints = [
            # Invariant 10: A menu cannot contain the same FoodItem twice under one MenuMeal
            models.UniqueConstraint(
                fields=["menu_meal", "food_item"],
                name="uq_menu_item_meal_food",
            ),
        ]

    def __str__(self):
        return f"Item {self.food_item_id} in MenuMeal {self.menu_meal_id}"
