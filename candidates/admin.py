from django.contrib import admin

from .models import Application, Candidate


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ["name", "email", "phone", "created_at"]
    search_fields = ["name", "email"]


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ["candidate", "job", "cv_score", "status", "decided_by", "decided_at", "created_at"]
    list_filter = ["status"]
