"""
Feature 5: CV-Job Matching (Advanced).

Compares the Candidate Profile (parsed_resume) against the Job Requirements
and produces:
  - An overall CV Match / Eligibility Score (0-100)
  - A category breakdown: Skills, Experience, Education — so a candidate can
    see exactly *why* they are (or aren't) a strong match for a specific
    vacancy, not just a single opaque number.
  - A human-readable explanation of the score, so "AI screening is based on
    job-relevant evidence rather than vague impressions" (Section 5 of spec).

No external/paid API is used here — this is pure Python (regex + keyword
matching), so it always works, instantly and for free.
"""
import re

# Weights for the overall eligibility score.
SKILLS_WEIGHT = 70
EXPERIENCE_WEIGHT = 15
EDUCATION_WEIGHT = 15

YEARS_RE = re.compile(r"(\d{1,2})\s*\+?\s*(?:years?|yrs?)", re.IGNORECASE)


def _normalize(skill: str) -> str:
    return re.sub(r"[^a-z0-9]", "", skill.lower())


def _skills_match(candidate, job):
    candidate_skills = candidate.parsed_resume.get("skills", []) or []
    candidate_text = (candidate.raw_resume_text or "") + " " + " ".join(candidate_skills)
    candidate_norm = {_normalize(s) for s in candidate_skills}

    required = job.required_skills or []
    preferred = job.preferred_skills or []

    matched, missing = [], []
    for skill in required:
        norm = _normalize(skill)
        if norm in candidate_norm or re.search(rf"\b{re.escape(skill)}\b", candidate_text, re.IGNORECASE):
            matched.append(skill)
        else:
            missing.append(skill)

    matched_preferred = [
        s for s in preferred
        if _normalize(s) in candidate_norm or re.search(rf"\b{re.escape(s)}\b", candidate_text, re.IGNORECASE)
    ]

    required_pct = (len(matched) / len(required) * 100) if required else 100
    preferred_pct = (len(matched_preferred) / len(preferred) * 100) if preferred else 100
    # Required skills count for 80% of the skills sub-score, preferred for 20%.
    skills_pct = round(required_pct * 0.8 + preferred_pct * 0.2, 1)

    return skills_pct, matched, missing, matched_preferred


def _years_from_text(text: str) -> int:
    years = [int(m) for m in YEARS_RE.findall(text or "")]
    return max(years) if years else 0


def _experience_match(candidate, job):
    required_years = _years_from_text(job.experience_required or "")
    if required_years == 0:
        # No specific/numeric experience requirement stated (e.g. "Entry
        # level" or left blank) — treat as satisfied.
        return 100.0, 0, 0

    exp_lines = " ".join(candidate.parsed_resume.get("experience", []) or [])
    candidate_years = _years_from_text(exp_lines) or _years_from_text(candidate.raw_resume_text or "")

    if candidate_years >= required_years:
        pct = 100.0
    else:
        pct = round((candidate_years / required_years) * 100, 1)
    return pct, candidate_years, required_years


def _education_match(candidate, job):
    required_edu = (job.education or "").strip()
    if not required_edu:
        return 100.0, True

    candidate_edu_entries = candidate.parsed_resume.get("education", []) or []
    candidate_edu_text = (" ".join(candidate_edu_entries) + " " + (candidate.raw_resume_text or "")).lower()

    required_words = [w for w in re.findall(r"[a-zA-Z]+", required_edu.lower()) if len(w) > 2]
    hit = any(w in candidate_edu_text for w in required_words)
    if hit:
        return 100.0, True
    if candidate_edu_entries:
        # Candidate has *some* education listed, just not a clear match — partial credit.
        return 40.0, False
    return 0.0, False


def match_candidate_to_job(candidate, job) -> dict:
    skills_pct, matched, missing, matched_preferred = _skills_match(candidate, job)
    exp_pct, candidate_years, required_years = _experience_match(candidate, job)
    edu_pct, edu_hit = _education_match(candidate, job)

    score = round(
        skills_pct * SKILLS_WEIGHT / 100
        + exp_pct * EXPERIENCE_WEIGHT / 100
        + edu_pct * EDUCATION_WEIGHT / 100,
        1,
    )
    score = max(0.0, min(100.0, score))

    explanation_parts = []
    if matched:
        explanation_parts.append(f"Candidate has demonstrated experience in {', '.join(matched)}.")
    if missing:
        explanation_parts.append(f"Limited or no evidence of {', '.join(missing)}.")
    if matched_preferred:
        explanation_parts.append(f"Also shows preferred skills: {', '.join(matched_preferred)}.")
    if required_years:
        if candidate_years >= required_years:
            explanation_parts.append(f"Meets the {required_years}+ year experience requirement ({candidate_years} yrs found).")
        else:
            explanation_parts.append(f"Job asks for {required_years}+ years; resume shows about {candidate_years} yrs.")
    if job.education:
        explanation_parts.append(
            f"Education requirement ({job.education}) {'appears met' if edu_hit else 'is not clearly evidenced in the resume'}."
        )
    if not explanation_parts:
        explanation_parts.append("No resume data available to evaluate against job requirements.")

    return {
        "score": score,
        "explanation": " ".join(explanation_parts),
        "matched_skills": matched + matched_preferred,
        "missing_skills": missing,
        "breakdown": {
            "skills": round(skills_pct, 1),
            "experience": round(exp_pct, 1),
            "education": round(edu_pct, 1),
        },
    }
