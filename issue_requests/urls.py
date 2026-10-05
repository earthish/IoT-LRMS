from django.urls import path

from . import views

app_name = "issue_requests"

urlpatterns = [
    path("", views.my_requests, name="list"),
    path("basket/", views.basket_view, name="basket"),
    path("basket/add/<int:instrument_id>/", views.basket_add, name="basket_add"),
    path("basket/update/<int:instrument_id>/", views.basket_update, name="basket_update"),
    path("basket/remove/<int:instrument_id>/", views.basket_remove, name="basket_remove"),
]
