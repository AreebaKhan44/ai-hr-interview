import uuid

from django.db import models
from django.utils import timezone

from candidates.models import Application, Candidate
from jobs.models import Job


class Interview(models.Model):
    """An interview session for a candidate against a specific job."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        QUESTIONS_GENERATED = "QUESTIONS_GENERATED", "Questions Generated"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        COMPLETED = "COMPLETED", "Completed"

    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="interviews")
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="interviews")
    application = models.ForeignKey(
        Application, on_delete=models.SET_NULL, null=True, blank=True, related_name="interviews"
    )

    class StatusLabel(models.TextChoices):
        STRONG = "STRONG", "🟢 Strong Candidate"
        CONSIDER = "CONSIDER", "🟡 Consider"
        WEAK = "WEAK", "🔴 Weak Candidate"

    status = models.CharField(max_length=25, choices=Status.choices, default=Status.PENDING)
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    overall_score = models.FloatField(null=True, blank=True)

    # Feature 12: Overall Candidate Score -> AI recommendation label.
    # This is a recommendation only; HR always makes the final call (see
    # Application.status / HR review fields).
    status_label = models.CharField(max_length=10, choices=StatusLabel.choices, blank=True)

    # Feature 13: AI Interview Report - score broken down per category
    # (technical_skills, problem_solving, communication, experience), 0-100.
    category_scores = models.JSONField(default=dict, blank=True)

    # ------------------------------------------------------------------
    # Feature 17: Interview Security
    # Every interview gets a unique secure token, an expiration time,
    # attempt tracking and a lock-after-completion flag so a submitted
    # interview can never be silently reopened/duplicated.
    # ------------------------------------------------------------------
    access_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=1)
    is_locked = models.BooleanField(default=False)

    # ------------------------------------------------------------------
    # Feature 18: AI Anti-Cheating / Integrity (Optional Advanced).
    # These are *signals* for HR to review, never a "cheating: yes/no"
    # verdict - see evaluation.compute_integrity_flags().
    # ------------------------------------------------------------------
    tab_switch_count = models.PositiveIntegerField(default=0)
    integrity_flags = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def is_token_valid(self):
        """Feature 17: validate the secure link before allowing access.
        Attempt count is tracked for HR visibility/integrity signals (see
        Feature 18) but does not block an in-progress session from
        continuing - only a locked (completed) or expired link is rejected.
        """
        if self.is_locked:
            return False, "This interview has already been completed and is locked."
        if self.token_expires_at and timezone.now() > self.token_expires_at:
            return False, "This interview link has expired. Ask HR to issue a new one."
        return True, ""

    def __str__(self):
        return f"Interview: {self.candidate} - {self.job}"


class Question(models.Model):
    """
    Feature 6: AI Interview Question Generation.
    Each question generated for an interview, categorized as per Section 7
    (Introduction, Technical Skills, Problem Solving, Project Experience,
    Scenario Based, Behavioral, Communication, Role-Specific).
    """

    class Category(models.TextChoices):
        INTRODUCTION = "INTRODUCTION", "Introduction"
        TECHNICAL = "TECHNICAL", "Technical Skills"
        PROBLEM_SOLVING = "PROBLEM_SOLVING", "Problem Solving"
        PROJECT = "PROJECT", "Project Experience"
        SCENARIO = "SCENARIO", "Scenario Based"
        BEHAVIORAL = "BEHAVIORAL", "Behavioral"
        COMMUNICATION = "COMMUNICATION", "Communication"
        ROLE_SPECIFIC = "ROLE_SPECIFIC", "Role-Specific"

    class Difficulty(models.TextChoices):
        EASY = "EASY", "Easy"
        MEDIUM = "MEDIUM", "Medium"
        HARD = "HARD", "Hard"

    interview = models.ForeignKey(Interview, on_delete=models.CASCADE, related_name="questions")
    question = models.TextField()
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.TECHNICAL)
    difficulty = models.CharField(max_length=10, choices=Difficulty.choices, default=Difficulty.MEDIUM)
    order = models.PositiveIntegerField(default=0)

    # Tracks whether the question was generated from the job, from the CV
    # (project-based), or is a static introduction/behavioral question.
    source = models.CharField(max_length=20, default="job_skills")

    # Feature 8: AI Interviewer - adaptive follow-up questions. When a
    # candidate's answer is only partially strong, the AI generates one
    # follow-up question that digs deeper into that same topic, mirroring
    # the spec's example ("Can you explain how you would optimize...").
    is_followup = models.BooleanField(default=False)
    parent_question = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="followups"
    )

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"[{self.category}] {self.question[:60]}"


class Answer(models.Model):
    """
    Feature 10/11: Text Interview (MVP) + AI Evaluation System.
    Stores the candidate's text answer to a question plus the AI evaluation
    of that answer: a 0-10 score, strengths, weaknesses and a short
    recommendation, evaluated against a simple rubric (Section 11).
    """

    question = models.OneToOneField(Question, on_delete=models.CASCADE, related_name="answer")
    candidate_answer = models.TextField()

    score = models.FloatField(null=True, blank=True, help_text="0-10 score for this answer")
    strengths = models.JSONField(default=list, blank=True)
    weaknesses = models.JSONField(default=list, blank=True)
    recommendation = models.CharField(max_length=255, blank=True)

    # Feature 18: Anti-Cheating / Integrity signals (optional, informational
    # only - see evaluation.compute_integrity_flags).
    time_taken_seconds = models.FloatField(null=True, blank=True)
    was_pasted = models.BooleanField(default=False)
    was_voice_input = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Answer to Q{self.question_id} (score={self.score})"
