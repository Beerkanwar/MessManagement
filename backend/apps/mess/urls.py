"""
URL patterns for mess, managers, meal occurrences, rates, and extras — Phase 5.
Enforces SPEC SDD §64, Appendix A, and ImplementationGuide Phase 5.
"""
from django.urls import path
from apps.mess import views

urlpatterns = [
    # Mess Master [SPEC SDD §64, ImplementationGuide Phase 5]
    path("messes", views.mess_list_create_view, name="messes_list_create"),
    path("messes/<int:mess_id>", views.mess_detail_update_view, name="mess_detail_update"),
    path("messes/<int:mess_id>/deactivate", views.mess_deactivate_view, name="mess_deactivate"),
    path("messes/<int:mess_id>/meal-rates", views.meal_rates_list_create_view, name="meal_rates_list_create"),

    # Mess Managers (Super Admin) [SPEC SDD §64, ImplementationGuide Phase 5]
    path("admin/mess-managers", views.mess_manager_list_create_view, name="mess_manager_list_create"),
    path("admin/mess-managers/<int:user_id>/reassign", views.mess_manager_reassign_view, name="mess_manager_reassign"),
    path("admin/mess-managers/<int:user_id>/deactivate", views.mess_manager_deactivate_view, name="mess_manager_deactivate"),

    # Meals [SPEC SDD §64, ImplementationGuide Phase 5]
    path("meals/types", views.meal_types_view, name="meals_types_list"),
    path("meals/occurrences", views.meal_occurrences_list_view, name="meal_occurrences_list"),
    path("meals/occurrences/<int:occurrence_id>/cancel", views.meal_occurrence_cancel_view, name="meal_occurrence_cancel"),

    # Extras [SPEC SDD §64, ImplementationGuide Phase 5]
    path("extras/items", views.extra_items_list_create_view, name="extras_items_list_create"),
    path("extras/items/<int:item_id>", views.extra_item_detail_update_view, name="extra_item_detail_update"),
    path("extras/items/<int:item_id>/deactivate", views.extra_item_deactivate_view, name="extra_item_deactivate"),
    path("extras/items/<int:item_id>/prices", views.extra_prices_list_create_view, name="extra_prices_list_create"),
]
