# backend/app/llm.py
import os
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from pydantic import ValidationError
from google import genai
from google.genai import types

from .resume_schema import Resume


class LLMEditProposal(BaseModel):
    assistant_message: str
    edits_summary: List[str] = Field(default_factory=list)
    proposed_resume: Dict[str, Any]
    needs_confirmation: bool = True


def _strip_fences(text: str) -> str:
    value = (text or "").strip()
    if value.startswith("```"):
        parts = value.split("```")
        value = parts[1].strip() if len(parts) > 1 else value
        if value.lower().startswith("json"):
            value = value[4:].strip()
    return value


def _extract_json_object(text: str) -> str:
    """
    Pull the outermost JSON object from noisy model output.
    Keeps strict schema validation later via Pydantic.
    """
    s = _strip_fences(text)
    if not s:
        raise ValueError("empty response")
    if s.startswith("{") and s.endswith("}"):
        return s

    start = s.find("{")
    if start < 0:
        raise ValueError("no json object in response")

    depth = 0
    in_string = False
    escaped = False
    end = -1
    for i, ch in enumerate(s[start:], start=start):
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break

    if end < 0:
        raise ValueError("unterminated json object in response")
    return s[start : end + 1]


def _parse_proposal_response(raw_text: str) -> LLMEditProposal:
    payload = _extract_json_object(raw_text)
    proposal = LLMEditProposal.model_validate_json(payload)
    Resume.model_validate(proposal.proposed_resume)
    return proposal


def _build_parse_prompt(raw_text: str, seed_resume: Dict[str, Any]) -> str:
    """
    Gemini should extract resume content into the Resume JSON schema.
    It must return ONLY JSON matching the Resume schema below.
    """
    schema = {
        "header": {
            "name": "",
            "email": "",
            "phone": "",
            "linkedin": "",
            "github": "",
            "portfolio": "",
            "location": ""
        },
        "education": [
            {"school": "", "degree": "", "major": "", "grad": "", "gpa": "", "coursework": []}
        ],
        "skills": {
            "languages": [],
            "frameworks": [],
            "tools": [],
            "concepts": [],
            # IMPORTANT: make this a dict to match your “heading as key” rule
            "categories": {}
        },
        "experience": [
            {"company": "", "location": "", "role": "", "start": "", "end": "", "bullets": []}
        ],
        "projects": [
            {"name": "", "link": "", "stack": [], "start": "", "end": "", "bullets": []}
        ],
        "leadership": [
            {"org": "", "title": "", "start": "", "end": "", "bullets": []}
        ],
        "awards": []
    }

    return f"""
Return ONLY valid JSON. No markdown. No commentary.

You will be given:
1) SEED_RESUME_JSON already extracted from the resume.
2) RAW_RESUME_TEXT (raw text from the resume).

Your job:
- PRESERVE all existing data in SEED_RESUME_JSON.
- Fill missing/empty fields by extracting from RAW_RESUME_TEXT.
- Do NOT remove or overwrite existing non-empty values
  unless RAW_RESUME_TEXT explicitly corrects them.

If the user asks for a broad improvement like "make it professional", "polish it", "improve it":
- Propose rewrites across ALL experience + project bullets (rewrite wording only, no new facts).
- Set needs_confirmation=true
- Provide edits_summary (strings describing what you changed)

Output must EXACTLY match this JSON schema (same keys, correct types):
{json.dumps(schema, indent=2)}

Rules:
- Do NOT invent employers, schools, titles, dates, locations, metrics, links, or awards.
- If a field is missing, use "" or [] or {{}} as appropriate.
- Split bullets into concise action-oriented statements.
- Preserve original meaning; paraphrase only for clarity.
- If unsure, leave empty.

Skills parsing rule:
- If skills are grouped under custom headings (e.g., "Laboratory:", "Software and Analytical:", "Professional:"),
  store them in skills.categories as a JSON object:
  {{
    "Laboratory": ["Skill1", "Skill2"],
    "Software and Analytical": ["SkillA"]
  }}

If a resume section does not match the schema exactly, map it to the closest section:
- certifications -> awards
- activities -> leadership
- relevant coursework -> education.coursework

SEED_RESUME_JSON:
{json.dumps(seed_resume, indent=2)}

RAW_RESUME_TEXT:
{raw_text}
""".strip()


def _build_chat_prompt(
    resume_json: Dict[str, Any],
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """
    Gemini should propose edits to an existing Resume JSON.
    Must return ONLY JSON matching LLMEditProposal shape:
    {
      "assistant_message": "...",
      "edits_summary": ["..."],
      "proposed_resume": { ... Resume JSON ... },
      "needs_confirmation": true/false
    }
    """
    history = history or []

    # Make history deterministic + safe
    history_lines: List[str] = []
    for turn in history[-12:]:  # keep it short
        role = (turn.get("role") or "").strip().lower()
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        if role not in ("user", "assistant"):
            role = "user"
        history_lines.append(f"{role.upper()}: {content}")

    history_block = "\n".join(history_lines) if history_lines else "NONE"

    return f"""
Return ONLY valid JSON. No markdown. No commentary.

You are editing an existing resume represented as JSON (RESUME_JSON).
You must produce an edit proposal in this exact shape:

{{
  "assistant_message": "brief explanation of what you changed and why",
  "edits_summary": ["short bullet-like strings describing changes"],
  "proposed_resume": <RESUME_JSON with edits applied>,
  "needs_confirmation": true
}}

Rules:
- Do NOT invent facts (companies, titles, dates, metrics, links).
- You MAY rewrite bullets for clarity, impact, concision, and professionalism WITHOUT adding new facts.
- Preserve structure and keys.
- Only change fields relevant to the user's request.
- If the request is broad ("polish", "make professional", "improve"), rewrite ALL experience + project bullets.
- Default needs_confirmation=true unless user explicitly asked for an automatic rewrite and no factual risk exists.

Conversation history:
{history_block}

Current RESUME_JSON:
{json.dumps(resume_json, indent=2)}

User request:
{user_message}
""".strip()

def _build_job_tailor_prompt(
    resume_json: Dict[str, Any],
    job_description: str,
) -> str:
    """
    Gemini should tailor resume language to a target job description
    while preserving factual integrity.
    """
    return f"""
Return ONLY valid JSON. No markdown. No commentary.

You are tailoring an existing resume JSON object to align with a job posting.
The resume JSON schema MUST remain identical.

If the user says “make it professional / polish / improve”, you MUST propose edits across all experience + project bullets. Do NOT ask what to improve.

Hard integrity rules:
- Do NOT invent employers, schools, titles, dates, locations, links, awards, projects, or metrics.
- Keep all existing experience factually consistent.
- You MAY rephrase bullets to mirror the job description language and emphasize relevant accomplishments.
- You MAY reorder bullets within an experience/project for relevance.
- You MAY remove less relevant bullets only if enough relevant content remains for that entry.
- If job requirements are not present in the resume, do not fabricate them.

Optimization goals:
- Match terminology from the job description where truthful (tools, domains, responsibilities).
- Prioritize impact and relevance in experience/project bullets.
- Keep bullet tone concise, achievement-oriented, and ATS-friendly.

Return JSON with exactly these keys:
- assistant_message: string to show the user
- edits_summary: array of short bullet strings describing the changes
- proposed_resume: full resume JSON object (same schema as CURRENT_RESUME_JSON)
- needs_confirmation: boolean

Always set needs_confirmation=true.
In assistant_message say: "I tailored your resume to this job description. Here are the edits I can make:" then list the edits and end with "Should I go ahead and make your new resume?".

CURRENT_RESUME_JSON:
{json.dumps(resume_json, indent=2)}

JOB_DESCRIPTION:
{job_description}
""".strip()


def parse_resume_with_llm(raw_text: str, seed_resume: Dict[str, Any]) -> Resume:
    """
    Input: raw resume text
    Output: Resume Pydantic model parsed with LLM
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in environment (.env).")

    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    client = genai.Client(api_key=api_key)
    prompt = _build_parse_prompt(raw_text, seed_resume)

    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=4096,
        ),
    )

    payload = _extract_json_object(resp.text or "")
    data: Any = json.loads(payload)
    return Resume.model_validate(data)


def propose_chat_edits(
    resume: Resume,
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> LLMEditProposal:
    """
    Input: Resume Pydantic model (already parsed WITHOUT AI)
    Output: LLM edit proposal and message for the user

    Robustness:
    - Calls Gemini once with the normal prompt
    - If output fails JSON/schema validation, retries once with a strict "fix your JSON" prompt
    - If still failing, returns a safe, non-crashing response
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in environment (.env).")

    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    client = genai.Client(api_key=api_key)

    def _retry_prompt(previous_output: str, base_prompt: str) -> str:
        return f"""
You returned invalid JSON.

Return ONLY valid JSON that matches the required response schema EXACTLY.
No markdown. No commentary. No extra keys.

Fix your previous output into valid JSON:
{previous_output}

Original instructions:
{base_prompt}
""".strip()

    base_prompt = _build_chat_prompt(resume.model_dump(), user_message, history)

    # --- Attempt 1 ---
    resp1 = client.models.generate_content(
        model=model,
        contents=base_prompt,
        config=types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=4096,
            response_mime_type="application/json",
        ),
    )

    text1 = resp1.text or ""

    try:
        return _parse_proposal_response(text1)
    except ValidationError:
        # fall through to retry
        pass
    except Exception:
        # any other parsing error -> retry once
        pass

    # --- Attempt 2 (strict repair) ---
    rp = _retry_prompt(text1, base_prompt)
    resp2 = client.models.generate_content(
        model=model,
        contents=rp,
        config=types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=4096,
            response_mime_type="application/json",
        ),
    )

    text2 = resp2.text or ""

    try:
        return _parse_proposal_response(text2)
    except Exception:
        # --- Final safe fallback (no crash, no loop) ---
        return LLMEditProposal(
            assistant_message=(
                "I ran into a formatting issue generating the edit plan. "
                "Try again with a broad command like:\n"
                "- “Rewrite all my experience and project bullets to be more professional.”\n"
                "- “Tighten my bullets to one line each, keeping the meaning the same.”"
            ),
            edits_summary=[],
            proposed_resume=resume.model_dump(),
            needs_confirmation=False,
        )

def propose_job_tailored_edits(
    resume: Resume,
    job_description: str,
) -> LLMEditProposal:
    """
    Input: Resume Pydantic model + raw job description text
    Output: LLM edit proposal focused on job-tailored resume phrasing
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in environment (.env).")

    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    client = genai.Client(api_key=api_key)
    prompt = _build_job_tailor_prompt(resume.model_dump(), job_description)

    def _retry_prompt(previous_output: str, base_prompt: str) -> str:
        return f"""
You returned invalid JSON.

Return ONLY valid JSON that matches the required response schema EXACTLY.
No markdown. No commentary. No extra keys.

Fix your previous output into valid JSON:
{previous_output}

Original instructions:
{base_prompt}
""".strip()

    resp1 = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=4096,
            response_mime_type="application/json",
        ),
    )

    text1 = resp1.text or ""
    try:
        return _parse_proposal_response(text1)
    except Exception:
        pass

    resp2 = client.models.generate_content(
        model=model,
        contents=_retry_prompt(text1, prompt),
        config=types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=4096,
            response_mime_type="application/json",
        ),
    )
    text2 = resp2.text or ""
    try:
        return _parse_proposal_response(text2)
    except Exception:
        return LLMEditProposal(
            assistant_message=(
                "I tailored your resume to this job description and prepared safe edits, "
                "but formatting failed this time. Please retry once to regenerate."
            ),
            edits_summary=[],
            proposed_resume=resume.model_dump(),
            needs_confirmation=False,
        )
