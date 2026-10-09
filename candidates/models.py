from django.conf import settings
from django.db import models

from jobs.models import Job


def resume_upload_path(instance, filename):
    return f"resumes/{instance.user_id}/{filename}"


class Candidate(models.Model):
    """
    Feature 4: CV Upload & Resume Parsing.
    Stores the raw resume file plus the structured data extracted from it
    (Name, Email, Phone, Education, Experience, Skills, Projects,
    Certifications, Previous companies) as per Section 4 & Section 19.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="candidate_profile"
    )
    name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)

    resume = models.FileField(upload_to=resume_upload_path, blank=True, null=True)

    # Structured data extracted from the CV (Section 4 & 19: 'parsed_resume').
    parsed_resume = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured JSON: education, experience, skills, projects, certifications, previous_companies",
    )
    raw_resume_text = models.TextField(blank=True, help_text="Raw text extracted from the uploaded CV file")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name or self.user.username


class Application(models.Model):
    """
    Links a Candidate to a Job they applied for and stores the CV-Job match score
    (Feature 5: CV-Job Matching, Section 19: Application entity).
    """

    class Status(models.TextChoices):
        APPLIED = "APPLIED", "Applied"
        SCREENED = "SCREENED", "Screened"
        INTERVIEWING = "INTERVIEWING", "Interviewing"
        SHORTLISTED = "SHORTLISTED", "Shortlisted"
        REJECTED = "REJECTED", "Rejected"

    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="applications")
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="applications")

    cv_score = models.FloatField(null=True, blank=True, help_text="CV-Job match / eligibility score, 0-100")
    cv_match_explanation = models.TextField(blank=True)
    matched_skills = models.JSONField(default=list, blank=True)
    missing_skills = models.JSONField(default=list, blank=True)
    # Feature 5 (Advanced): eligibility score broken down by Skills/Experience/Education.
    score_breakdown = models.JSONField(default=dict, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.APPLIED)

    # Feature 14/16: HR review - final decision & comments. AI only
    # recommends (Interview.status_label); HR always makes the final call.
    hr_comments = models.TextField(blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="application_decisions"
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["candidate", "job"]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.candidate} -> {self.job}"
