from rest_framework.routers import DefaultRouter

from .views import InterviewViewSet

router = DefaultRouter()
router.register("", InterviewViewSet, basename="interview")

urlpatterns = router.urls
