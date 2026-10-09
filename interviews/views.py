from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from candidates.models import Application, Candidate
from jobs.models import Job

from .evaluation import compute_integrity_flags, compute_report, evaluate_answer, recommended_hr_questions
from .models import Answer, Interview, Question
from .question_generator import generate_followup_question, generate_questions, needs_followup
from .serializers import InterviewSerializer
from .voice import transcribe_audio

INTERVIEW_LINK_EXPIRY_DAYS = getattr(settings, "INTERVIEW_LINK_EXPIRY_DAYS", 7)
MAX_FOLLOWUPS_PER_INTERVIEW = 2


class InterviewViewSet(viewsets.ModelViewSet):
    """
    Feature 6: AI Interview Question Generation.
    Creating an interview (or calling `generate_questions`) triggers automatic,
    role-specific question generation based on Job Description + Required
    Skills + Candidate CV.
    """
    serializer_class = InterviewSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_hr:
            return Interview.objects.all()
        return Interview.objects.filter(candidate__user=user)

    def create(self, request, *args, **kwargs):
        job_id = request.data.get("job")
        candidate_id = request.data.get("candidate")

        job = Job.objects.filter(id=job_id).first()
        if not job:
            return Response({"detail": "Job not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.user.is_candidate_role:
            candidate = getattr(request.user, "candidate_profile", None)
        else:
            candidate = Candidate.objects.filter(id=candidate_id).first()

        if not candidate:
            return Response({"detail": "Candidate not found."}, status=status.HTTP_404_NOT_FOUND)

        # Link to the matching Application (if one exists) so the CV match
        # score/status can be shown next to the interview score everywhere
        # (Feature 13 report, Feature 16 ranking).
        application = Application.objects.filter(candidate=candidate, job=job).first()

        # Feature 17: Interview Security - every interview gets a unique
        # token (set by the model default) plus an expiration time and a
        # one-attempt limit, right from creation.
        interview = Interview.objects.create(
            candidate=candidate,
            job=job,
            application=application,
            token_expires_at=timezone.now() + timedelta(days=INTERVIEW_LINK_EXPIRY_DAYS),
        )
        self._generate_and_save_questions(interview)

        return Response(InterviewSerializer(interview).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def generate_questions(self, request, pk=None):
        """
        Explicit endpoint to (re)generate AI interview questions for an
        existing interview — Feature 6 core action.
        """
        interview = self.get_object()
        interview.questions.all().delete()
        self._generate_and_save_questions(interview)
        return Response(InterviewSerializer(interview).data)

    @action(detail=True, methods=["get"], url_path="secure_link")
    def secure_link(self, request, pk=None):
        """
        Feature 17: Interview Security. Returns the unique, expiring,
        one-time-use link HR can send the candidate directly, without them
        needing to log in and browse to find it.
        """
        interview = self.get_object()
        if request.user.is_candidate_role and interview.candidate.user != request.user:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        valid, reason = interview.is_token_valid()
        return Response({
            "token": str(interview.access_token),
            "path": f"/?token={interview.access_token}",
            "expires_at": interview.token_expires_at,
            "attempt_count": interview.attempt_count,
            "max_attempts": interview.max_attempts,
            "is_locked": interview.is_locked,
            "valid": valid,
            "reason": reason,
        })

    @action(detail=True, methods=["post"], url_path="regenerate_link")
    def regenerate_link(self, request, pk=None):
        """Feature 17: HR can issue a fresh link/token (e.g. after expiry)."""
        interview = self.get_object()
        if not request.user.is_hr:
            return Response({"detail": "Only HR can regenerate interview links."}, status=status.HTTP_403_FORBIDDEN)
        import uuid
        interview.access_token = uuid.uuid4()
        interview.token_expires_at = timezone.now() + timedelta(days=INTERVIEW_LINK_EXPIRY_DAYS)
        interview.attempt_count = 0
        interview.is_locked = interview.status == Interview.Status.COMPLETED
        interview.save()
        return self.secure_link(request, pk=pk)

    @action(detail=False, methods=["get", "post"], url_path=r"by_token/(?P<token>[0-9a-f-]+)",
            permission_classes=[permissions.IsAuthenticated])
    def by_token(self, request, token=None):
        """
        Feature 17: Interview Security - candidate authentication + secure
        link access. The candidate must still be logged in (this project
        keeps accounts, per Feature 2), but this endpoint is what a shared
        `/?token=<uuid>` link resolves to: it validates the token, checks
        it belongs to this candidate, checks expiry/attempt/lock state, and
        only then hands back the interview + questions.
        """
        interview = Interview.objects.filter(access_token=token).first()
        if not interview:
            return Response({"detail": "Invalid interview link."}, status=status.HTTP_404_NOT_FOUND)
        if request.user.is_candidate_role and interview.candidate.user != request.user:
            return Response({"detail": "This interview link does not belong to your account."},
                             status=status.HTTP_403_FORBIDDEN)

        valid, reason = interview.is_token_valid()
        if not valid and interview.status != Interview.Status.COMPLETED:
            return Response({"detail": reason}, status=status.HTTP_403_FORBIDDEN)

        if interview.status in [Interview.Status.PENDING, Interview.Status.QUESTIONS_GENERATED]:
            interview.attempt_count += 1
            interview.save()

        return Response(InterviewSerializer(interview).data)

    @action(detail=True, methods=["post"])
    def submit_answer(self, request, pk=None):
        """
        Feature 10/11: Text Interview (MVP) + AI Evaluation System.
        Candidate submits a text answer for one question of this interview;
        the answer is immediately evaluated (score, strengths, weaknesses,
        recommendation) against a simple rubric.

        Feature 8: if the answer is only partially strong, the AI appends
        ONE adaptive follow-up question to the interview.
        Feature 18: optionally records how long the answer took and whether
        it was pasted, as integrity signals for HR (never a hard block).
        """
        interview = self.get_object()

        if request.user.is_candidate_role and interview.candidate.user != request.user:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        valid, reason = interview.is_token_valid()
        if not valid:
            return Response({"detail": reason}, status=status.HTTP_403_FORBIDDEN)

        question_id = request.data.get("question")
        answer_text = (request.data.get("answer") or "").strip()
        question = interview.questions.filter(id=question_id).first()
        if not question:
            return Response({"detail": "Question not found on this interview."}, status=status.HTTP_404_NOT_FOUND)
        if not answer_text:
            return Response({"detail": "Answer cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)

        self._save_answer(
            interview, question, answer_text,
            time_taken_seconds=request.data.get("time_taken_seconds") or None,
            was_pasted=bool(request.data.get("pasted")),
            was_voice_input=bool(request.data.get("voice_input")),
        )

        return Response(InterviewSerializer(interview).data)

    @action(detail=True, methods=["post"])
    def submit_voice_answer(self, request, pk=None):
        """
        Feature 9: Voice Interview (server-side track). Accepts an uploaded
        audio recording, transcribes it (OpenAI Whisper if OPENAI_API_KEY is
        set), then evaluates the transcript exactly like a typed answer.
        If no API key is configured, returns a clear message telling the
        candidate to use the free in-browser microphone button instead.
        """
        interview = self.get_object()
        if request.user.is_candidate_role and interview.candidate.user != request.user:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        valid, reason = interview.is_token_valid()
        if not valid:
            return Response({"detail": reason}, status=status.HTTP_403_FORBIDDEN)

        audio_file = request.FILES.get("audio")
        question_id = request.data.get("question")
        if not audio_file:
            return Response({"detail": "No audio file uploaded."}, status=status.HTTP_400_BAD_REQUEST)
        question = interview.questions.filter(id=question_id).first()
        if not question:
            return Response({"detail": "Question not found on this interview."}, status=status.HTTP_404_NOT_FOUND)

        try:
            transcript = transcribe_audio(audio_file)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        if not transcript:
            return Response({"detail": "Could not transcribe audio; please try again or type your answer."},
                             status=status.HTTP_400_BAD_REQUEST)

        self._save_answer(interview, question, transcript, was_voice_input=True)
        data = InterviewSerializer(interview).data
        data["transcript"] = transcript
        return Response(data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        """
        Feature 10/11/12: Submit the interview -> compute the overall score,
        the per-category breakdown, and an AI recommendation label
        (🟢 Strong / 🟡 Consider / 🔴 Weak). This label is a recommendation
        only; HR always makes the final hiring decision (see Application).

        Feature 17: locks the interview so it can never be reopened/resubmitted.
        Feature 18: computes integrity signals from tab-switch count + timing.
        """
        interview = self.get_object()

        if request.user.is_candidate_role and interview.candidate.user != request.user:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        valid, reason = interview.is_token_valid()
        if not valid:
            return Response({"detail": reason}, status=status.HTTP_403_FORBIDDEN)

        overall_score, category_scores, status_label = compute_report(interview)
        if overall_score is None:
            return Response({"detail": "Answer at least one question before finishing the interview."},
                             status=status.HTTP_400_BAD_REQUEST)

        interview.overall_score = overall_score
        interview.category_scores = category_scores
        interview.status_label = status_label
        interview.status = Interview.Status.COMPLETED
        interview.end_time = timezone.now()
        interview.tab_switch_count = int(request.data.get("tab_switches") or interview.tab_switch_count or 0)
        interview.is_locked = True  # Feature 17: prevent duplicate submissions
        interview.integrity_flags = compute_integrity_flags(interview)
        interview.save()

        if interview.application:
            interview.application.status = interview.application.Status.SCREENED
            interview.application.save()

        return Response(InterviewSerializer(interview).data)

    @action(detail=True, methods=["get"])
    def report(self, request, pk=None):
        """
        Feature 13: AI Interview Report - full breakdown for HR, including
        recommended follow-up questions for the next round and (Feature 18)
        integrity signals for human review.
        """
        interview = self.get_object()

        if request.user.is_candidate_role and interview.candidate.user != request.user:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        data = InterviewSerializer(interview).data
        data["recommended_hr_questions"] = (
            recommended_hr_questions(interview) if interview.status == Interview.Status.COMPLETED else []
        )
        return Response(data)

    @staticmethod
    def _save_answer(interview, question, answer_text, time_taken_seconds=None, was_pasted=False, was_voice_input=False):
        """
        Shared by submit_answer (typed) and submit_voice_answer (transcribed):
        evaluates the answer (Feature 11), stores it, advances interview
        status, and triggers an adaptive follow-up question if warranted
        (Feature 8).
        """
        evaluation = evaluate_answer(question, answer_text, interview.job)
        Answer.objects.update_or_create(
            question=question,
            defaults={
                "candidate_answer": answer_text,
                "score": evaluation.get("score"),
                "strengths": evaluation.get("strengths", []),
                "weaknesses": evaluation.get("weaknesses", []),
                "recommendation": evaluation.get("recommendation", ""),
                "time_taken_seconds": time_taken_seconds,
                "was_pasted": was_pasted,
                "was_voice_input": was_voice_input,
            },
        )

        if interview.status in [Interview.Status.PENDING, Interview.Status.QUESTIONS_GENERATED]:
            interview.status = Interview.Status.IN_PROGRESS
            interview.start_time = interview.start_time or timezone.now()
            interview.attempt_count = interview.attempt_count or 1
            interview.save()

        # Feature 8: adaptive follow-up, capped so interviews don't grow unbounded.
        existing_followups = interview.questions.filter(is_followup=True).count()
        if (not question.is_followup and needs_followup(evaluation.get("score"))
                and existing_followups < MAX_FOLLOWUPS_PER_INTERVIEW):
            followup_text = generate_followup_question(question, answer_text, interview.job)
            if followup_text:
                last_order = interview.questions.order_by("-order").first().order
                Question.objects.create(
                    interview=interview,
                    question=followup_text,
                    category=question.category,
                    difficulty=question.difficulty,
                    source="adaptive_followup",
                    order=last_order + 1,
                    is_followup=True,
                    parent_question=question,
                )
        return evaluation

    @staticmethod
    def _generate_and_save_questions(interview: Interview):
        generated = generate_questions(interview.job, interview.candidate)
        objs = [
            Question(
                interview=interview,
                question=q["question"],
                category=q.get("category", "TECHNICAL"),
                difficulty=q.get("difficulty", "MEDIUM"),
                source=q.get("source", "job_skills"),
                order=i,
            )
            for i, q in enumerate(generated)
        ]
        Question.objects.bulk_create(objs)
        interview.status = Interview.Status.QUESTIONS_GENERATED
        interview.save()
