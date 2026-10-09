from django.conf import settings
from django.db import models


class Job(models.Model):
    """
    Feature 3: Job Creation Module.
    Fields mirror the spec (Section 3) exactly:
    Job Title, Department, Job Description, Responsibilities, Required Skills,
    Preferred Skills, Experience Required, Education, Employment Type, Location,
    Salary Range (optional), Interview Duration, Number of Interview Questions,
    Difficulty Level.
    """

    class EmploymentType(models.TextChoices):
        FULL_TIME = "FULL_TIME", "Full-time"
        PART_TIME = "PART_TIME", "Part-time"
        CONTRACT = "CONTRACT", "Contract"
        INTERNSHIP = "INTERNSHIP", "Internship"

    class DifficultyLevel(models.TextChoices):
        EASY = "EASY", "Easy"
        MEDIUM = "MEDIUM", "Medium"
        HARD = "HARD", "Hard"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        CLOSED = "CLOSED", "Closed"
        DRAFT = "DRAFT", "Draft"

    title = models.CharField(max_length=255)
    department = models.CharField(max_length=255, blank=True)
    description = models.TextField()
    responsibilities = models.TextField(blank=True)

    # Stored as JSON lists so they can be used directly by matching & question generation.
    required_skills = models.JSONField(default=list, help_text="e.g. ['Python','Django','PostgreSQL']")
    preferred_skills = models.JSONField(default=list, blank=True)

    experience_required = models.CharField(max_length=100, blank=True, help_text="e.g. '2-4 years'")
    education = models.CharField(max_length=255, blank=True)
    employment_type = models.CharField(max_length=20, choices=EmploymentType.choices, default=EmploymentType.FULL_TIME)
    location = models.CharField(max_length=255, blank=True)
    salary_range = models.CharField(max_length=100, blank=True, null=True)

    interview_duration_minutes = models.PositiveIntegerField(default=30)
    number_of_interview_questions = models.PositiveIntegerField(default=10)
    difficulty_level = models.CharField(max_length=10, choices=DifficultyLevel.choices, default=DifficultyLevel.MEDIUM)

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="jobs_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.department})"
