# backend/app/llm.py
import os
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

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
    "skills": {{"languages": [], "frameworks": [], "tools": [], "concepts": [], "categories":[]}}],
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
    """
    Gemini should propose resume edits based on the user's message.
    It must return ONLY JSON matching the response schema below.
    """
    history_block = ""
    if history:
        # Keep last few turns to avoid huge prompts
        turns = history[-8:]
        history_block = "\n\nCHAT_HISTORY:\n" + "\n".join(
            f'{t["role"].upper()}: {t["content"]}' for t in turns
        )

    return f"""
Return ONLY valid JSON. No markdown. No commentary.

You are helping edit an existing resume JSON object. The resume JSON schema MUST remain identical.
Do NOT invent employers, schools, titles, dates, locations, metrics, or links.
You MAY rewrite bullet wording to be more professional/technical while preserving meaning.
You MAY add new bullets ONLY if the user explicitly provides the underlying facts.
If the user says "remove", remove it. If the user says "keep", preserve it.
If unknown, use "" or [].

Return JSON with exactly these keys:
- assistant_message: string to show the user
- edits_summary: array of short bullet strings describing the changes
- proposed_resume: full resume JSON object (same schema as CURRENT_RESUME_JSON)
- needs_confirmation: boolean

If you need more info, ask a concise question in assistant_message, set needs_confirmation=false,
and return proposed_resume equal to CURRENT_RESUME_JSON with edits_summary=[].

If CURRENT_RESUME_JSON.header.linkedin and CURRENT_RESUME_JSON.header.portfolio are both empty
AND CURRENT_RESUME_JSON.header.location is empty, ask for the user's city and state abbreviation
(e.g., "Boston, MA") before proposing edits.

If you are ready to propose edits, include edits_summary (3-7 bullets), set needs_confirmation=true,
and in assistant_message say: "Here are the edits I can make:" then list the edits, and end with
"Should I go ahead and make your new resume?".

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

    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

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
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in environment (.env).")

    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

    client = genai.Client(api_key=api_key)

    prompt = _build_chat_prompt(resume.model_dump(), user_message, history)

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

    text = (resp.text or "").strip()

    # still strip fences just in case (usually unnecessary once schema enforced)
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1].strip() if len(parts) > 1 else text
        if text.lower().startswith("json"):
            text = text[4:].strip()

    # Validate directly
    proposal = LLMEditProposal.model_validate_json(text)
    # Ensure proposed resume still validates against the schema
    Resume.model_validate(proposal.proposed_resume)
    return proposal


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

    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

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
