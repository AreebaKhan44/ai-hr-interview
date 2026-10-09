from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from candidates.models import Application
from candidates.serializers import ApplicationSerializer

from .services import match_candidate_to_job


class RecomputeMatchView(APIView):
    """
    Feature 5: CV-Job Matching.
    Recomputes and returns the CV match score/explanation for a given application
    (e.g. after a candidate updates their resume).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, application_id):
        application = Application.objects.filter(id=application_id).first()
        if not application:
            return Response({"detail": "Application not found."}, status=404)

        result = match_candidate_to_job(application.candidate, application.job)
        application.cv_score = result["score"]
        application.cv_match_explanation = result["explanation"]
        application.matched_skills = result["matched_skills"]
        application.missing_skills = result["missing_skills"]
        application.save()

        return Response(ApplicationSerializer(application).data)
