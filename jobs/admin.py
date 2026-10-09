from django.contrib import admin

from .models import Job


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ["title", "department", "employment_type", "difficulty_level", "status", "created_at"]
    list_filter = ["status", "employment_type", "difficulty_level"]
    search_fields = ["title", "department"]
