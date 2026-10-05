from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    path("", views.instrument_list, name="list"),
    path("<int:pk>/", views.instrument_detail, name="detail"),
]
