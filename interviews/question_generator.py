"""
Feature 6: AI Interview Question Generation.

Generates interview questions based on:
    Job Description + Required Skills + Candidate CV
(exactly as described in Section 6 of the spec), split into categories:
    Technical, Scenario Based, Behavioral, Project Based
(and additionally Introduction / Role-Specific to match the fuller
category list in Section 7 - Structured Interview).

Two generation strategies:
  1. LLM-based (OpenAI) — used when settings.OPENAI_API_KEY is configured.
     Produces tailored, high-quality questions referencing the specific job
     and the candidate's actual projects/skills.
  2. Template/rule-based fallback — guarantees the feature works with zero
     external dependencies/API keys, using a bank of question templates
     keyed by skill, plus generic scenario/behavioral/project templates.
"""
import json
import re

from django.conf import settings

# ---------------------------------------------------------------------------
# Template bank for the rule-based fallback generator
# ---------------------------------------------------------------------------
SKILL_TECHNICAL_QUESTIONS = {
    "python": [
        "What is the difference between a list and a tuple in Python?",
        "Explain how Python's garbage collection works.",
        "What are Python decorators and when would you use one?",
        "Explain the difference between deep copy and shallow copy in Python.",
    ],
    "django": [
        "How does Django ORM work under the hood?",
        "Explain the request/response lifecycle in a Django application.",
        "What is Django middleware and how have you used it?",
        "How do Django signals work, and what are the risks of overusing them?",
    ],
    "django rest framework": [
        "How would you design serializers for nested resources in DRF?",
        "Explain the difference between ModelViewSet and APIView in DRF.",
    ],
    "postgresql": [
        "How would you optimize a slow query in PostgreSQL?",
        "Explain the difference between a clustered and non-clustered index, and how PostgreSQL indexing works.",
        "How do you handle database migrations safely in production?",
    ],
    "rest apis": [
        "What is a REST API, and what makes an API RESTful?",
        "How do you handle versioning in a REST API?",
    ],
    "git": [
        "Walk me through your typical Git branching workflow.",
        "How would you resolve a complex merge conflict?",
    ],
    "docker": [
        "How would you containerize a Django application with PostgreSQL using Docker?",
    ],
    "oop": [
        "Explain the four pillars of object-oriented programming with examples.",
    ],
}

GENERIC_TECHNICAL_QUESTIONS = [
    "Can you describe your experience working with {skill}?",
    "What challenges have you faced while using {skill}, and how did you solve them?",
]

SCENARIO_TEMPLATES = [
    "You have a Django API receiving 10,000 requests per minute and response time "
    "has increased significantly. How would you investigate and solve the problem?",
    "You discover a critical bug in production affecting live users. Walk me "
    "through how you would triage and resolve it.",
    "You're asked to design a database schema for a new feature under a tight "
    "deadline. How do you balance speed with good design?",
]

BEHAVIORAL_TEMPLATES = [
    "Tell us about a challenging software development problem you faced and how you solved it.",
    "Describe a time you disagreed with a teammate about a technical decision. How did you handle it?",
    "Tell us about a time you had to learn a new technology quickly for a project.",
]

COMMUNICATION_TEMPLATES = [
    "How do you explain a complex technical concept to a non-technical stakeholder?",
    "Describe how you document your code and communicate progress to your team.",
]

ROLE_SPECIFIC_TEMPLATE = "For the {title} role, what do you think are the most important skills, and why?"

INTRO_TEMPLATE = (
    "Hello {name}, welcome to the {company} interview. I'll be conducting your "
    "initial technical interview for the {title} position. To start, can you "
    "briefly introduce yourself and walk me through your background?"
)


def _match_skill_bank(skill: str):
    key = skill.strip().lower()
    if key in SKILL_TECHNICAL_QUESTIONS:
        return SKILL_TECHNICAL_QUESTIONS[key]
    for bank_key, questions in SKILL_TECHNICAL_QUESTIONS.items():
        if bank_key in key or key in bank_key:
            return questions
    return None


def _fallback_generate(job, candidate, num_questions: int, company_name: str = "Synergy Integrated Solutions"):
    """Rule/template based question generator (no external API required)."""
    skills = list(job.required_skills or []) + list(job.preferred_skills or [])
    projects = (candidate.parsed_resume or {}).get("projects", []) if candidate else []
    candidate_name = (candidate.name if candidate else "") or "Candidate"

    questions = []

    # 1. Introduction
    questions.append({
        "category": "INTRODUCTION",
        "difficulty": "EASY",
        "source": "static",
        "question": INTRO_TEMPLATE.format(name=candidate_name, company=company_name, title=job.title),
    })

    # 2. Technical — pulled from the skill bank, one per required/preferred skill
    for skill in skills:
        bank = _match_skill_bank(skill)
        if bank:
            questions.append({
                "category": "TECHNICAL", "difficulty": "MEDIUM",
                "source": "job_skills", "question": bank[0],
            })
        else:
            questions.append({
                "category": "TECHNICAL", "difficulty": "MEDIUM", "source": "job_skills",
                "question": GENERIC_TECHNICAL_QUESTIONS[0].format(skill=skill),
            })

    # 3. Scenario based
    questions.append({
        "category": "SCENARIO", "difficulty": job.difficulty_level, "source": "template",
        "question": SCENARIO_TEMPLATES[0],
    })

    # 4. Behavioral
    questions.append({
        "category": "BEHAVIORAL", "difficulty": "EASY", "source": "template",
        "question": BEHAVIORAL_TEMPLATES[0],
    })

    # 5. Communication
    questions.append({
        "category": "COMMUNICATION", "difficulty": "EASY", "source": "template",
        "question": COMMUNICATION_TEMPLATES[0],
    })

    # 6. Project based — from the candidate's actual CV projects (Section 6: Project Based)
    if projects:
        proj = projects[0]
        questions.append({
            "category": "PROJECT", "difficulty": "MEDIUM", "source": "candidate_cv",
            "question": f"You mentioned {proj}. Can you explain the architecture and "
                        f"technologies you used, and what challenges you faced?",
        })
    else:
        questions.append({
            "category": "PROJECT", "difficulty": "MEDIUM", "source": "candidate_cv",
            "question": "Tell us about a project from your experience that best "
                        "demonstrates your skills relevant to this role.",
        })

    # 7. Role-specific
    questions.append({
        "category": "ROLE_SPECIFIC", "difficulty": "MEDIUM", "source": "job_skills",
        "question": ROLE_SPECIFIC_TEMPLATE.format(title=job.title),
    })

    # Pad with more technical questions from the skill bank if we still need more.
    idx = 1
    while len(questions) < num_questions:
        added = False
        for skill in skills:
            bank = _match_skill_bank(skill)
            if bank and idx < len(bank):
                questions.append({
                    "category": "TECHNICAL", "difficulty": job.difficulty_level, "source": "job_skills",
                    "question": bank[idx],
                })
                added = True
                if len(questions) >= num_questions:
                    break
        idx += 1
        if not added:
            break

    return questions[:num_questions]


def _llm_generate(job, candidate, num_questions: int):
    """LLM-based question generation using the job description + skills + candidate CV."""
    from openai import OpenAI

    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    candidate_summary = ""
    if candidate:
        candidate_summary = json.dumps(candidate.parsed_resume or {})

    prompt = f"""You are an AI HR interviewer generating structured interview questions.

Job Title: {job.title}
Department: {job.department}
Job Description: {job.description}
Required Skills: {', '.join(job.required_skills or [])}
Preferred Skills: {', '.join(job.preferred_skills or [])}
Difficulty Level: {job.difficulty_level}
Candidate CV summary (JSON): {candidate_summary}

Generate exactly {num_questions} interview questions covering these categories:
INTRODUCTION, TECHNICAL, PROBLEM_SOLVING, PROJECT, SCENARIO, BEHAVIORAL, COMMUNICATION, ROLE_SPECIFIC.
Include at least one PROJECT question referencing something specific from the candidate's CV if available.

Return ONLY a valid JSON array, each item shaped like:
{{"category": "TECHNICAL", "difficulty": "MEDIUM", "source": "job_skills", "question": "..."}}
"""
    response = client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
    )
    content = response.choices[0].message.content.strip()
    content = re.sub(r"^```json|```$", "", content, flags=re.MULTILINE).strip()
    return json.loads(content)


def generate_questions(job, candidate=None, num_questions=None):
    """
    Main entry point for Feature 6.
    Returns a list of dicts: {category, difficulty, source, question}
    """
    num_questions = num_questions or job.number_of_interview_questions or 10

    if settings.OPENAI_API_KEY:
        try:
            return _llm_generate(job, candidate, num_questions)
        except Exception:
            # Gracefully fall back if the LLM call fails (e.g. no network/quota).
            pass

    return _fallback_generate(job, candidate, num_questions)


# ---------------------------------------------------------------------------
# Feature 8: AI Interviewer - adaptive follow-up questions.
# After a candidate answers, the AI decides whether a follow-up is needed
# (see Section 8 example: "Good. Can you explain how you would optimize a
# Django ORM query involving multiple related models?"), making the
# interview adaptive rather than a static questionnaire.
# ---------------------------------------------------------------------------
FOLLOWUP_FALLBACK_TEMPLATES = [
    "Can you go a bit deeper on that — walk me through a concrete example from your own experience?",
    "What would you do differently if you had to solve that same problem at a much larger scale?",
    "What trade-offs did you consider there, and why did you choose that approach over the alternatives?",
]


def needs_followup(evaluation_score: float) -> bool:
    """A partial/borderline answer (neither clearly strong nor clearly weak) is
    the case where a human interviewer would naturally probe further."""
    return 4.0 <= (evaluation_score or 0) < 7.5


def _fallback_followup(question, answer_text):
    import random
    return random.choice(FOLLOWUP_FALLBACK_TEMPLATES)


def _llm_followup(question, answer_text, job):
    from openai import OpenAI

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    prompt = f"""You are an AI interviewer conducting a live, adaptive interview for a {job.title} role.

You just asked: "{question.question}"
The candidate answered: "{answer_text}"

Their answer was only partially complete. Ask ONE short, natural follow-up
question that digs deeper into the same topic to clarify their depth of
understanding (like a human interviewer would). Return ONLY the follow-up
question text, nothing else - no quotes, no preamble.
"""
    response = client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=100,
    )
    return response.choices[0].message.content.strip().strip('"')


def generate_followup_question(question, answer_text, job):
    """Returns a single follow-up question string, or None."""
    if settings.OPENAI_API_KEY:
        try:
            return _llm_followup(question, answer_text, job)
        except Exception:
            pass
    return _fallback_followup(question, answer_text)
