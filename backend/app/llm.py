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


def _build_parse_prompt(raw_text: str, seed_resume: Dict[str, Any]) -> str:
        """
        Gemini should extract resume content into the Resume JSON schema.
        It must return ONLY JSON matching the Resume schema below.
        """
        return f"""
Return ONLY valid JSON. No markdown. No commentary.


You will be given a SEED_RESUME_JSON already extracted from the resume.
Your job is to PRESERVE all existing data in SEED_RESUME_JSON and fill missing fields
by extracting from RAW_RESUME_TEXT. Do NOT remove or overwrite existing non-empty values
unless the raw text explicitly corrects them.

If the user asks for a broad improvement like "make it professional", "polish it", "improve it",
you MUST propose edits across ALL experience + project bullets (rewrite wording only, no new facts).
Do NOT ask what to improve in that case.
Set needs_confirmation=true and provide edits_summary.

Map any extra resume information into the closest matching field so the final output
matches this JSON schema:
{{
    "header": {{
        "name": "",
        "email": "",
        "phone": "",
        "linkedin": "",
        "github": "",
        "portfolio": "",
        "location": ""
    }},
    "education": [
        {{"school": "", "degree": "", "major": "", "grad": "", "gpa": "", "coursework": []}}
    ],
    "skills": {{"languages": [], "frameworks": [], "tools": [], "concepts": [], "categories":[]}}
    ],
    "experience": [
        {{"company": "", "location": "", "role": "", "start": "", "end": "", "bullets": []}}
    ],
    "projects": [
        {{"name": "", "link": "", "stack": [], "start": "", "end": "", "bullets": []}}
    ],
    "leadership": [
        {{"org": "", "title": "", "start": "", "end": "", "bullets": []}}
    ],
    "awards": []
}}

Rules:
- Do NOT invent employers, schools, titles, dates, locations, metrics, links, or awards.
- If a field is missing in the resume, use "" or [] as appropriate.
- Split bullets into concise action-oriented statements.
- Preserve original meaning; paraphrase only if necessary for clarity.
- If you are unsure, leave the field empty.
-- Skills parsing rule:
  If skills are grouped under custom headings (e.g., "Laboratory:", "Software and Analytical:", "Professional:"),
  put them in skills.categories with the heading as the key and an array of the listed items as the value.
- If a resume section does not match the schema exactly, map it to the closest section.
    For example: certifications -> awards, activities -> leadership, relevant coursework -> education.coursework.

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

    history_block = ""
    if history:
        turns = history[-8:]
        history_block = "\n\nCHAT_HISTORY:\n" + "\n".join(
            f'{t["role"].upper()}: {t["content"]}' for t in turns
        )

    return f"""
Return ONLY valid JSON.
No markdown.
No commentary.
No explanations outside JSON.
You MUST include ALL required keys.

You are a resume editing assistant.

CRITICAL:
You must ALWAYS return a JSON object with EXACTLY these keys:
- assistant_message (string)
- edits_summary (array of strings)
- proposed_resume (full resume JSON object)
- needs_confirmation (boolean)

If asking a question:
- edits_summary MUST be []
- proposed_resume MUST equal CURRENT_RESUME_JSON exactly
- needs_confirmation MUST be false

If making edits:
- edits_summary MUST contain 3-7 short bullet descriptions
- proposed_resume MUST be the FULL modified resume JSON
- needs_confirmation MUST be true

If user says something broad like:
"bullets"
"make it professional"
"polish it"
"improve it"

You MUST interpret that as:
Rewrite ALL experience + project bullets to be more professional.
Do NOT ask which bullets.
Do NOT ask what to improve.
Propose edits.

Do NOT invent employers, dates, metrics, or links.

If CURRENT_RESUME_JSON.header.name is empty:
Ask for the name before editing.

CURRENT_RESUME_JSON:
{json.dumps(resume_json, indent=2)}

USER_MESSAGE:
{user_message}
{history_block}
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

    text = (resp.text or "").strip()

    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1].strip() if len(parts) > 1 else text
        if text.lower().startswith("json"):
            text = text[4:].strip()

    data: Any = json.loads(text)
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

    def _strip_fences(s: str) -> str:
        s = (s or "").strip()
        if s.startswith("```"):
            parts = s.split("```")
            s = parts[1].strip() if len(parts) > 1 else s
            if s.lower().startswith("json"):
                s = s[4:].strip()
        return s

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

    text1 = _strip_fences(resp1.text or "")

    try:
        proposal = LLMEditProposal.model_validate_json(text1)
        Resume.model_validate(proposal.proposed_resume)
        return proposal
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

    text2 = _strip_fences(resp2.text or "")

    try:
        proposal2 = LLMEditProposal.model_validate_json(text2)
        Resume.model_validate(proposal2.proposed_resume)
        return proposal2
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

    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=4096,
            response_mime_type="application/json",
        ),
    )

    text = (resp.text or "").strip()

    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1].strip() if len(parts) > 1 else text
        if text.lower().startswith("json"):
            text = text[4:].strip()

    proposal = LLMEditProposal.model_validate_json(text)
    Resume.model_validate(proposal.proposed_resume)
    return proposal
def _build_chat_retry_prompt(raw_output: str, base_prompt: str) -> str:
    return f"""
You returned invalid JSON.

You MUST now return ONLY valid JSON that matches the required response schema EXACTLY.
No markdown. No commentary. No extra keys.

Here is your previous output (DO NOT repeat it verbatim; fix it into valid JSON):
{raw_output}

Original instructions:
{base_prompt}
""".strip()