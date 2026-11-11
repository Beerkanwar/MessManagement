"""
URL patterns for menu authoring and the student current menu
[SPEC SDD §64, ImplementationGuide Phase 11].
"""
from django.urls import path

from apps.menu import views

urlpatterns = [
    # Student view (must not collide with the integer menu detail route).
    path("menus/current", views.current_menu_view, name="menus_current"),

    # Food item master (global, reusable).
    path("menus/food-items", views.food_item_collection_view, name="menu_food_items"),
    path(
        "menus/food-items/<int:food_item_id>",
        views.food_item_detail_view,
        name="menu_food_item_detail",
    ),
    path(
        "menus/food-items/<int:food_item_id>/deactivate",
        views.food_item_deactivate_view,
        name="menu_food_item_deactivate",
    ),

    # Monthly menus.
    path("menus", views.menu_collection_view, name="menus_list"),
    path("menus/<int:menu_id>", views.menu_detail_view, name="menus_detail"),
    path("menus/<int:menu_id>/meals", views.menu_meal_view, name="menus_meal_set"),
    path("menus/<int:menu_id>/publish", views.menu_publish_view, name="menus_publish"),
    path(
        "menus/<int:menu_id>/copy-previous",
        views.menu_copy_previous_view,
        name="menus_copy_previous",
    ),
]
