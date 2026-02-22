# backend/app/parser.py
import re
from .resume_schema import Resume
from .llm import parse_resume_with_llm

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")

def parse_resume_text(raw: str) -> Resume:
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    text = "\n".join(lines)

    email = EMAIL_RE.search(text).group(0) if EMAIL_RE.search(text) else ""
    phone = PHONE_RE.search(text).group(0) if PHONE_RE.search(text) else ""
    name = lines[0] if lines else ""

    seed_resume = {
        "header": {
            "name": name,
            "email": email,
            "phone": phone,
            "linkedin": "",
            "github": "",
            "portfolio": "",
            "location": ""
        },
        "education": [],
        "skills": {"languages": [], "frameworks": [], "tools": [], "concepts": [], "categories": {}},
        "experience": [],
        "projects": [],
        "leadership": [],
        "awards": []
    }

    try:
        return parse_resume_with_llm(text, seed_resume)
    except Exception:
        # Heuristic fallback if LLM parsing is unavailable
        return Resume.model_validate(seed_resume)