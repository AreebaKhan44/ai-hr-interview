from django.urls import path

from .views import RecomputeMatchView

urlpatterns = [
    path("recompute/<int:application_id>/", RecomputeMatchView.as_view(), name="recompute-match"),
]
