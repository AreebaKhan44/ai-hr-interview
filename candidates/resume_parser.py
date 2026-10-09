"""
Feature 4: CV Upload & Resume Parsing.

Extracts raw text from an uploaded PDF/DOCX resume, then structures it into
JSON (Name, Email, Phone, Education, Experience, Skills, Projects,
Certifications, Previous companies) as described in Section 4 of the spec:

    "The CV parser should preferably use Python libraries such as:
     PyMuPDF / pdfplumber, python-docx
     Then an LLM can structure the extracted information into JSON."

If no LLM API key is configured, a regex/keyword-based fallback extractor is
used instead, so the feature works fully offline out of the box.
"""
import json
import re

import pymupdf as fitz  # PyMuPDF
import pdfplumber
from docx import Document

from django.conf import settings

COMMON_SKILLS = [
    "Python", "Django", "Django REST Framework", "REST APIs", "PostgreSQL",
    "MySQL", "Git", "OOP", "JavaScript", "React", "HTML", "CSS", "Docker",
    "Kubernetes", "AWS", "Azure", "GCP", "Flask", "FastAPI", "SQL", "NoSQL",
    "MongoDB", "Redis", "Celery", "Linux", "CI/CD", "Machine Learning",
    "Data Analysis", "Pandas", "NumPy", "TensorFlow", "PyTorch", "Java",
    "C++", "Node.js", "TypeScript", "Problem Solving",
]

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(\+?\d[\d\-\s()]{8,}\d)")


def extract_text_from_pdf(file_path: str) -> str:
    """Extract text using PyMuPDF, falling back to pdfplumber if needed."""
    try:
        text_parts = []
        with fitz.open(file_path) as doc:
            for page in doc:
                text_parts.append(page.get_text())
        text = "\n".join(text_parts).strip()
        if text:
            return text
    except Exception:
        pass

    # Fallback: pdfplumber
    text_parts = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text_parts.append(page.extract_text() or "")
    return "\n".join(text_parts).strip()


def extract_text_from_docx(file_path: str) -> str:
    doc = Document(file_path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def extract_raw_text(file_path: str, filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return extract_text_from_pdf(file_path)
    elif lower.endswith(".docx"):
        return extract_text_from_docx(file_path)
    raise ValueError("Unsupported resume file type. Only PDF and DOCX are supported.")


def _fallback_structure(text: str) -> dict:
    """Regex/keyword based structuring, used when no LLM API key is configured."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    email_match = EMAIL_RE.search(text)
    phone_match = PHONE_RE.search(text)
    name = lines[0] if lines else ""

    found_skills = [s for s in COMMON_SKILLS if re.search(rf"\b{re.escape(s)}\b", text, re.IGNORECASE)]

    def _section(*headers):
        pattern = r"(?:%s)\s*:?\s*\n(.*?)(?=\n[A-Z][A-Za-z ]{2,25}\s*:?\s*\n|\Z)" % "|".join(headers)
        m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        return m.group(1).strip() if m else ""

    education = _section("Education", "Academic Background")
    experience = _section("Experience", "Work Experience", "Employment History")
    projects = _section("Projects", "Personal Projects")
    certifications = _section("Certifications", "Certificates")

    return {
        "name": name,
        "email": email_match.group(0) if email_match else "",
        "phone": phone_match.group(0) if phone_match else "",
        "skills": found_skills,
        "education": [e.strip("-• \t") for e in education.splitlines() if e.strip()],
        "experience": [e.strip("-• \t") for e in experience.splitlines() if e.strip()],
        "projects": [e.strip("-• \t") for e in projects.splitlines() if e.strip()],
        "certifications": [e.strip("-• \t") for e in certifications.splitlines() if e.strip()],
        "previous_companies": [],
        "extraction_method": "fallback_regex",
    }


def _llm_structure(text: str) -> dict:
    """Use an LLM to structure the resume text into JSON (as recommended in Section 4)."""
    from openai import OpenAI

    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    prompt = f"""Extract the following candidate information from the resume text below
and return ONLY valid JSON with keys:
name, email, phone, education (list), experience (list), skills (list),
projects (list), certifications (list), previous_companies (list).

Resume text:
---
{text[:8000]}
---
"""
    response = client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    content = response.choices[0].message.content.strip()
    content = re.sub(r"^```json|```$", "", content, flags=re.MULTILINE).strip()
    data = json.loads(content)
    data["extraction_method"] = "llm"
    return data


def parse_resume(file_path: str, filename: str) -> dict:
    """
    Main entry point: extract raw text, then structure it into JSON.
    Uses the LLM structuring path when OPENAI_API_KEY is configured,
    otherwise falls back to the regex/keyword based extractor.
    Returns: (raw_text, structured_dict) is NOT returned here; callers should
    call extract_raw_text separately if they also need the raw text.
    """
    raw_text = extract_raw_text(file_path, filename)

    if settings.OPENAI_API_KEY:
        try:
            structured = _llm_structure(raw_text)
            return raw_text, structured
        except Exception:
            # If the LLM call fails for any reason, gracefully fall back.
            pass

    structured = _fallback_structure(raw_text)
    return raw_text, structured
