from django.urls import include, path, re_path

from planner.views import spa_index

urlpatterns = [
    path("api/", include("planner.urls")),
    # Everything else is the React single-page app (static assets are served by WhiteNoise).
    re_path(r"^(?!api/).*$", spa_index),
]
