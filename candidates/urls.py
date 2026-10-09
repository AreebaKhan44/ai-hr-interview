from rest_framework.routers import DefaultRouter

from .views import ApplicationViewSet, CandidateViewSet

router = DefaultRouter()
router.register("candidates", CandidateViewSet, basename="candidate")
router.register("applications", ApplicationViewSet, basename="application")

urlpatterns = router.urls
