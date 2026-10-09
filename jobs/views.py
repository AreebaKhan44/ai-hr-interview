from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.permissions import IsHR
from matching.services import match_candidate_to_job

from .models import Job
from .serializers import JobSerializer


class JobViewSet(viewsets.ModelViewSet):
    """
    Feature 3: Job Creation Module.
    HR can create/manage jobs. Everyone authenticated can view active jobs
    (so candidates can see job info, per Feature 2: 'View job information').
    """
    queryset = Job.objects.all()
    serializer_class = JobSerializer

    def get_permissions(self):
        if self.action in ["create", "update", "partial_update", "destroy"]:
            return [permissions.IsAuthenticated(), IsHR()]
        return [permissions.IsAuthenticated()]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        qs = Job.objects.all()
        if self.request.user.is_authenticated and self.request.user.is_candidate_role:
            qs = qs.filter(status=Job.Status.ACTIVE)
        return qs

    @action(detail=True, methods=["get"], permission_classes=[permissions.IsAuthenticated, IsHR])
    def ranking(self, request, pk=None):
        """
        Feature 16: Candidate Ranking.
        For this job, ranks every candidate who has completed an interview,
        highest overall AI score first, together with the CV match score and
        the AI status label - so HR can see *why* each candidate is ranked
        where they are rather than a single black-box number.
        """
        job = self.get_object()
        interviews = (
            job.interviews.select_related("candidate", "application")
            .filter(status="COMPLETED")
            .order_by("-overall_score")
        )
        ranking = [
            {
                "candidate_id": iv.candidate_id,
                "candidate_name": iv.candidate.name or iv.candidate.user.username,
                "interview_score": iv.overall_score,
                "status_label": iv.status_label,
                "category_scores": iv.category_scores,
                "cv_score": iv.application.cv_score if iv.application else None,
                "application_status": iv.application.status if iv.application else None,
            }
            for iv in interviews
        ]
        return Response({"job": job.title, "ranking": ranking})

    @action(detail=True, methods=["get"], permission_classes=[permissions.IsAuthenticated])
    def my_match(self, request, pk=None):
        """
        Feature 5 (Advanced): lets a candidate check their eligibility % for
        this specific vacancy *before* applying, based on their uploaded CV —
        with a Skills/Experience/Education breakdown, not just one number.
        Free/local computation, no paid API involved.
        """
        if not request.user.is_candidate_role:
            return Response({"detail": "Only candidates can check their own match."}, status=403)

        candidate = getattr(request.user, "candidate_profile", None)
        if not candidate:
            return Response({"detail": "Create your candidate profile and upload a resume first."}, status=400)
        if not candidate.parsed_resume:
            return Response({"detail": "Upload your resume first so we can check your eligibility."}, status=400)

        job = self.get_object()
        result = match_candidate_to_job(candidate, job)
        return Response({
            "job": job.title,
            "eligibility_score": result["score"],
            "breakdown": result["breakdown"],
            "explanation": result["explanation"],
            "matched_skills": result["matched_skills"],
            "missing_skills": result["missing_skills"],
        })
