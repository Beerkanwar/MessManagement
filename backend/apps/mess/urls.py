from django.urls import path
from apps.mess.views import mess_list_stub_view, meal_types_stub_view, extras_list_stub_view

urlpatterns = [
    path("messes", mess_list_stub_view, name="messes_list"),
    path("meals/types", meal_types_stub_view, name="meals_types_list"),
    path("extras/items", extras_list_stub_view, name="extras_items_list"),
]
