from rest_framework import serializers

from .models import Application, Candidate


class CandidateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Candidate
        fields = [
            "id", "user", "name", "email", "phone", "resume",
            "parsed_resume", "raw_resume_text", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "user", "parsed_resume", "raw_resume_text", "created_at", "updated_at"]


class ApplicationSerializer(serializers.ModelSerializer):
    candidate_name = serializers.ReadOnlyField(source="candidate.name")
    job_title = serializers.ReadOnlyField(source="job.title")

    class Meta:
        model = Application
        fields = [
            "id", "candidate", "candidate_name", "job", "job_title",
            "cv_score", "cv_match_explanation", "matched_skills",
            "missing_skills", "score_breakdown", "status", "hr_comments", "decided_at", "created_at",
        ]
        read_only_fields = [
            "id", "cv_score", "cv_match_explanation", "matched_skills",
            "missing_skills", "score_breakdown", "status", "hr_comments", "decided_at", "created_at",
        ]
