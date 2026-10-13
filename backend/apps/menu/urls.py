from django.urls import path
from apps.menu.views import menu_list_stub_view

urlpatterns = [
    path("menus", menu_list_stub_view, name="menus_list"),
]
