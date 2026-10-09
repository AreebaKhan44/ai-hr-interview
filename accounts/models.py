from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom user model supporting the two roles required by the spec (Section 2):
      - HR / Admin
      - Candidate
    """

    class Role(models.TextChoices):
        HR = "HR", "HR / Admin"
        CANDIDATE = "CANDIDATE", "Candidate"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CANDIDATE)
    phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_hr(self):
        return self.role == self.Role.HR

    @property
    def is_candidate_role(self):
        return self.role == self.Role.CANDIDATE

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
