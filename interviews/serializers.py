from rest_framework import serializers

from .models import Answer, Interview, Question


class AnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Answer
        fields = [
            "id", "candidate_answer", "score", "strengths", "weaknesses", "recommendation",
            "time_taken_seconds", "was_pasted", "was_voice_input", "created_at",
        ]


class QuestionSerializer(serializers.ModelSerializer):
    answer = AnswerSerializer(read_only=True)

    class Meta:
        model = Question
        fields = ["id", "question", "category", "difficulty", "order", "source", "is_followup", "answer"]


class InterviewSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)
    candidate_name = serializers.ReadOnlyField(source="candidate.name")
    job_title = serializers.ReadOnlyField(source="job.title")

    class Meta:
        model = Interview
        fields = [
            "id", "candidate", "candidate_name", "job", "job_title", "application",
            "status", "start_time", "end_time", "overall_score", "status_label",
            "category_scores", "created_at", "questions",
            "access_token", "token_expires_at", "attempt_count", "max_attempts", "is_locked",
            "tab_switch_count", "integrity_flags",
        ]
        read_only_fields = [
            "id", "status", "overall_score", "status_label", "category_scores", "created_at",
            "access_token", "token_expires_at", "attempt_count", "max_attempts", "is_locked",
            "tab_switch_count", "integrity_flags",
        ]
