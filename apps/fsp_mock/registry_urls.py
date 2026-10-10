"""FSP Registry Mock URLs."""

from django.urls import path

from fsp_mock import views

urlpatterns = [
    path(
        "v1/participants/<str:participant_id>/achievements",
        views.RegistryAchievementsView.as_view(),
        name="registry-achievements",
    ),
]
