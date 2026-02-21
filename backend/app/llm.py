# backend/app/llm.py
import os
import json
from typing import Any

from google import genai
from google.genai import types

from .resume_schema import Resume


def _build_prompt(raw_text: str, extra: str) -> str:
    # Keep it strict: JSON only, no markdown, no LaTeX
    return f"""
Return ONLY valid JSON. No markdown. No commentary.

Rules:
- Do NOT invent employers, schools, titles, dates, metrics, or links.
- If something is unknown, use "" or [].
- Bullets should be concise, technical, and honest.

JSON schema (must match exactly):
{{
  "header": {{"name":"","email":"","phone":"","linkedin":"","github":"","portfolio":"","location":""}},
  "education":[{{"school":"","degree":"","major":"","grad":"","gpa":"","coursework":[]}}],
  "skills":{{"languages":[],"frameworks":[],"tools":[],"concepts":[]}},
  "experience":[{{"company":"","location":"","role":"","start":"","end":"","bullets":[]}}],
  "projects":[{{"name":"","link":"","stack":[],"start":"","end":"","bullets":[]}}],
  "leadership":[{{"org":"","title":"","start":"","end":"","bullets":[]}}],
  "awards":[]
}}

RESUME TEXT:
{raw_text}

EXTRA EXPERIENCE (optional):
{extra}
""".strip()


def structure_resume(raw_text: str, extra_experience: str = "") -> Resume:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in environment (.env).")

    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

    client = genai.Client(api_key=api_key)

    resp = client.models.generate_content(
        model=model,
        contents=_build_prompt(raw_text, extra_experience),
        config=types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=4096,
        ),
    )

    text = (resp.text or "").strip()
    data: Any = json.loads(text)
    return Resume.model_validate(data)