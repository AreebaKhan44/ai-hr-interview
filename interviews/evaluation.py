"""
Feature 11: AI Evaluation System.

Evaluates a single candidate answer against a simple rubric and returns:
    {score (0-10), strengths [..], weaknesses [..], recommendation "..."}

Same two-strategy approach as question_generator.py:
  1. LLM-based (OpenAI) when settings.OPENAI_API_KEY is configured.
  2. Rule-based fallback (keyword overlap + answer depth) otherwise, so the
     feature works fully offline with zero external dependencies.
"""
import json
import re

from django.conf import settings

MIN_MEANINGFUL_WORDS = 8


def _keywords_for(question, job):
    """Pull the skills/terms an answer to this question should ideally mention."""
    text = (question.question or "").lower()
    skills = [s for s in (list(job.required_skills or []) + list(job.preferred_skills or [])) if s]
    mentioned = [s for s in skills if s.lower() in text]
    return mentioned or skills[:3]


def _fallback_evaluate(question, answer_text, job):
    """Rule/heuristic based evaluator (no external API required)."""
    answer_text = (answer_text or "").strip()
    words = re.findall(r"[a-zA-Z']+", answer_text)
    word_count = len(words)

    if word_count == 0:
        return {
            "score": 0.0,
            "strengths": [],
            "weaknesses": ["No answer was provided."],
            "recommendation": "No evidence to evaluate; ask this question again.",
        }

    keywords = _keywords_for(question, job)
    lower_answer = answer_text.lower()
    matched_keywords = [k for k in keywords if k.lower() in lower_answer]

    # Base score from depth/detail of the answer.
    if word_count < MIN_MEANINGFUL_WORDS:
        score = 3.0
    elif word_count < 25:
        score = 5.5
    elif word_count < 60:
        score = 7.0
    else:
        score = 8.0

    # Reward mentioning job-relevant keywords, cap at 10.
    score = min(10.0, score + len(matched_keywords) * 0.7)

    strengths, weaknesses = [], []
    if matched_keywords:
        strengths.append(f"Answer shows relevant knowledge of {', '.join(matched_keywords)}.")
    if word_count >= 25:
        strengths.append("Provided a reasonably detailed explanation.")
    if not strengths:
        strengths.append("Attempted the question with a relevant response.")

    if word_count < MIN_MEANINGFUL_WORDS:
        weaknesses.append("Answer is too brief to fully judge depth of understanding.")
    if keywords and not matched_keywords:
        weaknesses.append(f"Did not clearly reference expected concepts such as {', '.join(keywords[:2])}.")
    if not weaknesses:
        weaknesses.append("Could go into more depth with a concrete example.")

    if score >= 8:
        recommendation = "Strong understanding with minor gaps."
    elif score >= 5.5:
        recommendation = "Solid answer overall; probe further on weaker areas in a follow-up round."
    else:
        recommendation = "Limited evidence of understanding; recommend a targeted follow-up question."

    return {
        "score": round(score, 1),
        "strengths": strengths,
        "weaknesses": weaknesses,
        "recommendation": recommendation,
    }


def _llm_evaluate(question, answer_text, job):
    from openai import OpenAI

    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    prompt = f"""You are an AI HR interviewer evaluating one candidate answer against a rubric.

Job Title: {job.title}
Required Skills: {', '.join(job.required_skills or [])}
Question ({question.category}): {question.question}
Candidate Answer: {answer_text}

Score the answer from 0 to 10 based on correctness, depth and relevance.
Return ONLY valid JSON shaped exactly like:
{{"score": 8.0, "strengths": ["..."], "weaknesses": ["..."], "recommendation": "..."}}
"""
    response = client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    content = response.choices[0].message.content.strip()
    content = re.sub(r"^```json|```$", "", content, flags=re.MULTILINE).strip()
    data = json.loads(content)
    data["score"] = max(0.0, min(10.0, float(data.get("score", 0))))
    return data


def evaluate_answer(question, answer_text, job):
    """Main entry point for Feature 11. Returns a dict (see above)."""
    if settings.OPENAI_API_KEY:
        try:
            return _llm_evaluate(question, answer_text, job)
        except Exception:
            pass
    return _fallback_evaluate(question, answer_text, job)


# ---------------------------------------------------------------------------
# Feature 12/13: aggregate per-category scores + overall status label
# ---------------------------------------------------------------------------
CATEGORY_BUCKETS = {
    "technical_skills": ["TECHNICAL", "ROLE_SPECIFIC"],
    "problem_solving": ["PROBLEM_SOLVING", "SCENARIO"],
    "communication": ["COMMUNICATION", "INTRODUCTION"],
    "experience": ["PROJECT", "BEHAVIORAL"],
}


def compute_report(interview):
    """
    Feature 12: Overall Candidate Score + Feature 13: AI Interview Report.
    Aggregates all answered questions into category scores (0-100), an
    overall score (0-100) and a recommendation label. Returns
    (overall_score, category_scores, status_label).
    """
    answers = [q.answer for q in interview.questions.all() if hasattr(q, "answer")]
    if not answers:
        return None, {}, ""

    overall_score = round(sum(a.score or 0 for a in answers) / len(answers) * 10, 1)

    category_scores = {}
    for bucket, categories in CATEGORY_BUCKETS.items():
        bucket_answers = [a for a in answers if a.question.category in categories]
        if bucket_answers:
            category_scores[bucket] = round(
                sum(a.score or 0 for a in bucket_answers) / len(bucket_answers) * 10, 1
            )

    if overall_score >= 75:
        status_label = "STRONG"
    elif overall_score >= 50:
        status_label = "CONSIDER"
    else:
        status_label = "WEAK"

    return overall_score, category_scores, status_label


def recommended_hr_questions(interview):
    """
    Feature 13: 'Recommended Interview Questions for HR' - suggests follow-up
    questions for the next round, focused on the candidate's weaker areas.
    """
    answers = [q.answer for q in interview.questions.all() if hasattr(q, "answer")]
    weak_answers = sorted([a for a in answers if (a.score or 0) < 6], key=lambda a: a.score or 0)
    suggestions = []
    for a in weak_answers[:3]:
        suggestions.append(
            f"Follow up on '{a.question.question[:80]}' — ask for a concrete example to confirm real-world experience."
        )
    if not suggestions:
        suggestions.append("No major weak areas found; focus the next round on culture fit and role expectations.")
    return suggestions


# ---------------------------------------------------------------------------
# Feature 18: AI Anti-Cheating / Integrity (Optional Advanced Feature).
# These are *signals* only, surfaced to HR for human review - never a
# "cheating: yes/no" verdict, per the spec's explicit caution against
# over-claiming detection accuracy (Section 18).
# ---------------------------------------------------------------------------
RAPID_ANSWER_SECONDS = 5
RAPID_ANSWER_MIN_WORDS = 15
TAB_SWITCH_FLAG_THRESHOLD = 3


def compute_integrity_flags(interview):
    """Returns a list of short, human-readable integrity notes for HR."""
    answers = [q.answer for q in interview.questions.all() if hasattr(q, "answer")]
    flags = []

    rapid = [
        a for a in answers
        if a.time_taken_seconds is not None
        and a.time_taken_seconds < RAPID_ANSWER_SECONDS
        and len((a.candidate_answer or "").split()) >= RAPID_ANSWER_MIN_WORDS
    ]
    if rapid:
        flags.append(
            f"{len(rapid)} answer(s) were submitted unusually fast for their length "
            f"(under {RAPID_ANSWER_SECONDS}s for a detailed answer)."
        )

    pasted = [a for a in answers if a.was_pasted]
    if pasted:
        flags.append(f"{len(pasted)} answer(s) appear to have been pasted rather than typed.")

    if interview.tab_switch_count >= TAB_SWITCH_FLAG_THRESHOLD:
        flags.append(f"Candidate switched away from the interview tab {interview.tab_switch_count} times.")

    if interview.attempt_count > 1:
        flags.append(f"This interview link was opened/started {interview.attempt_count} times.")

    return flags
