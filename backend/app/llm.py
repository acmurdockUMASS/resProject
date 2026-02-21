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

If you are ready to propose edits, include edits_summary (3-7 bullets), set needs_confirmation=true,
and in assistant_message say: "Here are the edits I can make:" then list the edits, and end with
"Should I go ahead and make your new resume?".

CURRENT_RESUME_JSON:
{json.dumps(resume_json, indent=2)}

USER_MESSAGE:
{user_message}
{history_block}
""".strip()


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
        ),
    )

    text = (resp.text or "").strip()

    # If Gemini adds code fences, strip them
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1].strip() if len(parts) > 1 else text
        if text.lower().startswith("json"):
            text = text[4:].strip()

    data: Any = json.loads(text)
    proposal = LLMEditProposal.model_validate(data)

    # Ensure proposed resume still validates against the schema
    Resume.model_validate(proposal.proposed_resume)
    return proposal