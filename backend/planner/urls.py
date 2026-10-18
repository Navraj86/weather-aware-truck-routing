from django.urls import path

from . import views

urlpatterns = [
    path("health", views.health),
    path("geocode", views.GeocodeView.as_view()),
    path("plan", views.PlanView.as_view()),
    path("heatmap", views.HeatmapView.as_view()),
]
