# backend/app/parser.py
import re
from .resume_schema import Resume

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")

def parse_resume_text(raw: str) -> Resume:
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    text = "\n".join(lines)

    email = EMAIL_RE.search(text).group(0) if EMAIL_RE.search(text) else ""
    phone = PHONE_RE.search(text).group(0) if PHONE_RE.search(text) else ""
    name = lines[0] if lines else ""

    # VERY SIMPLE initial structure
    return Resume.model_validate({
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
        "skills": {"languages": [], "frameworks": [], "tools": [], "concepts": []},
        "experience": [],
        "projects": [],
        "leadership": [],
        "awards": []
    })