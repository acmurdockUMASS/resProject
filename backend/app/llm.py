# backend/app/llm.py
import os
import json
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

from .resume_schema import Resume


def _build_chat_prompt(
    resume_json: Dict[str, Any],
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """
    Gemini should update the resume JSON based on the user's message.
    It must return ONLY JSON matching the same schema.
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
    """
    Input: Resume Pydantic model (already parsed WITHOUT AI)
    Output: Updated Resume model (same schema)
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
    return Resume.model_validate(data)