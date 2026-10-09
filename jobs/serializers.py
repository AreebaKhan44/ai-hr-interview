from rest_framework import serializers

from .models import Job


class JobSerializer(serializers.ModelSerializer):
    created_by = serializers.ReadOnlyField(source="created_by.username")

    class Meta:
        model = Job
        fields = [
            "id", "title", "department", "description", "responsibilities",
            "required_skills", "preferred_skills", "experience_required",
            "education", "employment_type", "location", "salary_range",
            "interview_duration_minutes", "number_of_interview_questions",
            "difficulty_level", "status", "created_by", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]
