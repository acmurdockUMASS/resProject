import json
import os
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

from .resume_schema import Resume


def _gemini_client() -> tuple[genai.Client, str]:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in environment.")
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    return genai.Client(api_key=api_key), model


def _extract_json(text: str) -> Any:
    payload = (text or "").strip()
    if payload.startswith("```"):
        parts = payload.split("```")
        payload = parts[1].strip() if len(parts) > 1 else payload
        if payload.lower().startswith("json"):
            payload = payload[4:].strip()
    return json.loads(payload)


def structure_resume(raw_text: str, extra_experience: str = "") -> Resume:
    client, model = _gemini_client()

    prompt = f"""
Return ONLY valid JSON. No markdown or comments.
Build a resume JSON that matches this schema exactly:
{json.dumps(Resume.model_json_schema(), indent=2)}

Rules:
- Use only facts from resume text and extra experience provided.
- If unknown, use empty string or empty list.
- Keep bullets concise and action-oriented.

RESUME_TEXT:
{raw_text}

EXTRA_EXPERIENCE:
{extra_experience}
""".strip()

    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=4096),
    )
    return Resume.model_validate(_extract_json(resp.text or ""))


def _build_chat_prompt(
    resume_json: Dict[str, Any],
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    history_block = ""
    if history:
        turns = history[-8:]
        history_block = "\n\nCHAT_HISTORY:\n" + "\n".join(
            f'{t["role"].upper()}: {t["content"]}' for t in turns
        )

    return f"""
Return ONLY valid JSON. No markdown. No commentary.

You are editing an existing resume JSON object. The JSON schema MUST remain identical.
Do NOT invent employers, schools, titles, dates, locations, metrics, or links.
You MAY rewrite bullet wording to be more professional/technical while preserving meaning.
You MAY add new bullets ONLY if the user explicitly provides the underlying facts.
If the user says "remove", remove it. If the user says "keep", preserve it.
If unknown, use "" or [].

CURRENT_RESUME_JSON:
{json.dumps(resume_json, indent=2)}

USER_MESSAGE:
{user_message}
{history_block}
""".strip()


def apply_chat_edits(
    resume: Resume,
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> Resume:
    client, model = _gemini_client()
    prompt = _build_chat_prompt(resume.model_dump(), user_message, history)

    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=4096),
    )

    return Resume.model_validate(_extract_json(resp.text or ""))


def tailor_resume_for_job(
    resume: Resume,
    job_description: str,
    job_title: Optional[str] = None,
    company: Optional[str] = None,
) -> Resume:
    client, model = _gemini_client()

    target_context = ""
    if job_title or company:
        target_context = f"\nTARGET_ROLE: {job_title or ''}\nTARGET_COMPANY: {company or ''}\n"

    prompt = f"""
Return ONLY valid JSON. No markdown. No commentary.

You are tailoring an existing resume JSON to a specific job description.
Keep the SAME JSON schema and factual integrity.

Rules:
- Do NOT invent new experiences, technologies, dates, metrics, or employers.
- Reorder bullets and sections to emphasize relevant experience.
- Rewrite bullets with stronger impact where facts already exist.
- Add keywords from the job description only when they are truly supported by existing resume facts.
- Preserve truthful content; remove or de-emphasize less relevant bullets.

CURRENT_RESUME_JSON:
{json.dumps(resume.model_dump(), indent=2)}
{target_context}
JOB_DESCRIPTION:
{job_description}
""".strip()

    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=4096),
    )

    return Resume.model_validate(_extract_json(resp.text or ""))
