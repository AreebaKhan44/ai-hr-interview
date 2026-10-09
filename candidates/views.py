from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.permissions import IsCandidate, IsHR
from jobs.models import Job
from matching.services import match_candidate_to_job

from .models import Application, Candidate
from .resume_parser import parse_resume
from .serializers import ApplicationSerializer, CandidateSerializer


class CandidateViewSet(viewsets.ModelViewSet):
    """
    Feature 4: CV Upload & Resume Parsing.
    Candidates manage their own profile; HR can view all candidates
    (Feature 14/15: Candidate Management).
    """
    serializer_class = CandidateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_hr:
            return Candidate.objects.all()
        return Candidate.objects.filter(user=user)

    def create(self, request, *args, **kwargs):
        """Create the profile once; if it already exists, update it instead of
        raising SQLite/PostgreSQL UNIQUE constraint errors on user_id."""
        existing = Candidate.objects.filter(user=request.user).first()
        if existing:
            serializer = self.get_serializer(existing, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def upload_resume(self, request, pk=None):
        """
        Feature 4: Candidate uploads PDF/DOCX -> system extracts structured
        info (name, email, phone, education, experience, skills, projects,
        certifications, previous companies) and stores it in the database.
        """
        candidate = self.get_object()
        if candidate.user != request.user and not request.user.is_hr:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        resume_file = request.FILES.get("resume")
        if not resume_file:
            return Response({"detail": "No resume file provided."}, status=status.HTTP_400_BAD_REQUEST)

        candidate.resume = resume_file
        candidate.save()

        try:
            raw_text, structured = parse_resume(candidate.resume.path, resume_file.name)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        candidate.raw_resume_text = raw_text
        candidate.parsed_resume = structured
        candidate.name = structured.get("name") or candidate.name
        candidate.email = structured.get("email") or candidate.email
        candidate.phone = structured.get("phone") or candidate.phone
        candidate.save()

        return Response(CandidateSerializer(candidate).data, status=status.HTTP_200_OK)


class ApplicationViewSet(viewsets.ModelViewSet):
    """
    Handles a candidate applying to a job. Automatically runs CV-Job Matching
    (Feature 5) as soon as an application is created.
    """
    serializer_class = ApplicationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_hr:
            qs = Application.objects.all()
            job_id = self.request.query_params.get("job")
            if job_id:
                qs = qs.filter(job_id=job_id)
            return qs
        return Application.objects.filter(candidate__user=user)

    def create(self, request, *args, **kwargs):
        if not request.user.is_candidate_role:
            return Response({"detail": "Only candidates can apply to jobs."}, status=status.HTTP_403_FORBIDDEN)

        candidate = getattr(request.user, "candidate_profile", None)
        if not candidate:
            return Response({"detail": "Create your candidate profile and upload a resume first."},
                             status=status.HTTP_400_BAD_REQUEST)

        job_id = request.data.get("job")
        job = Job.objects.filter(id=job_id).first()
        if not job:
            return Response({"detail": "Job not found."}, status=status.HTTP_404_NOT_FOUND)

        application, _ = Application.objects.get_or_create(candidate=candidate, job=job)

        # Feature 5: CV-Job Matching — runs automatically on application.
        match_result = match_candidate_to_job(candidate, job)
        application.cv_score = match_result["score"]
        application.cv_match_explanation = match_result["explanation"]
        application.matched_skills = match_result["matched_skills"]
        application.missing_skills = match_result["missing_skills"]
        application.score_breakdown = match_result.get("breakdown", {})
        application.save()

        return Response(ApplicationSerializer(application).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated, IsHR])
    def decide(self, request, pk=None):
        """
        Feature 1/14/16: HR review & final hiring decision.
        The AI only recommends (CV score + Interview status_label); HR
        reviews the evidence here and can shortlist/reject with comments,
        overriding the AI recommendation if needed.
        """
        application = self.get_object()
        new_status = request.data.get("status")
        valid_statuses = [Application.Status.SHORTLISTED, Application.Status.REJECTED, Application.Status.INTERVIEWING]
        if new_status not in valid_statuses:
            return Response(
                {"detail": f"status must be one of {', '.join(valid_statuses)}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        application.status = new_status
        application.hr_comments = request.data.get("comments", application.hr_comments)
        application.decided_by = request.user
        application.decided_at = timezone.now()
        application.save()

        return Response(ApplicationSerializer(application).data)
