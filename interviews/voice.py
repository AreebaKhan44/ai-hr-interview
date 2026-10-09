"""
Feature 9: Voice Interview — Advanced Requirement.

Pipeline (per Section 9 of the spec):
    Candidate Voice -> Speech-to-Text -> LLM/AI Interviewer -> Text Response -> Text-to-Speech

This project implements voice on **two tracks** so it works with or without
an API key:

  1. Zero-cost track (default): the frontend uses the browser's built-in
     Web Speech API (SpeechRecognition for STT, speechSynthesis for TTS).
     No backend involvement, no API key, works out of the box in Chrome/Edge.

  2. Server-side track (optional, used automatically when OPENAI_API_KEY is
     set): the candidate can instead upload a short audio recording of their
     answer, which is transcribed here with OpenAI's Whisper API before
     being scored by the normal evaluation pipeline (Feature 11). This is
     the "STT" step from the spec's suggested pipeline.

Either path produces a normal text answer, which then flows through the same
AI Evaluation System (Feature 11) as a typed answer - so scoring stays
consistent regardless of how the candidate answered.
"""
from django.conf import settings


def transcribe_audio(audio_file):
    """
    Transcribes an uploaded audio file using OpenAI Whisper.
    Returns the transcribed text, or raises if no API key is configured /
    the call fails - callers should catch and fall back to instructing the
    candidate to use the browser's built-in voice input instead.
    """
    if not settings.OPENAI_API_KEY:
        raise RuntimeError(
            "Server-side voice transcription requires OPENAI_API_KEY to be set. "
            "Use the in-browser microphone button instead (works with no API key)."
        )

    from openai import OpenAI

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    transcript = client.audio.transcriptions.create(
        model="whisper-1",
        file=(getattr(audio_file, "name", "answer.webm"), audio_file.read()),
    )
    return (transcript.text or "").strip()
