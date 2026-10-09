from rest_framework.permissions import BasePermission


class IsHR(BasePermission):
    """Allows access only to HR/Admin users."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_hr)


class IsCandidate(BasePermission):
    """Allows access only to Candidate users."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_candidate_role)
