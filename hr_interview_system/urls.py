"""
URL configuration for hr_interview_system project.

/admin/                  Django admin
/api/accounts/           Feature 2: register/login/me
/api/jobs/                Feature 3: Job Creation Module + Feature 16 ranking
/api/candidates/         Feature 4: Candidate profile + resume upload
/api/applications/       Feature 4/5: Job applications + CV-Job matching + HR decide
/api/matching/           Feature 5: CV-Job Matching (recompute)
/api/interviews/         Feature 6-13: Questions, text interview, AI evaluation, report
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from .home_views import home

urlpatterns = [
    path("", home, name="home"),
    path("admin/", admin.site.urls),
    path("api/accounts/", include("accounts.urls")),
    path("api/jobs/", include("jobs.urls")),
    path("api/", include("candidates.urls")),
    path("api/matching/", include("matching.urls")),
    path("api/interviews/", include("interviews.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
