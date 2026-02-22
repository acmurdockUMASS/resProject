import os
import uuid
import json
import re
import logging
import os
from typing import Any, Dict, List, Optional, Union
from dotenv import load_dotenv
from pydantic import BaseModel
from fastapi import FastAPI, UploadFile
from .parse import extract_text
from .storage import put_object, presigned_get_url, get_object_bytes
from .models import UploadResumeResponse, PresignedUrlResponse, JobSearchResponse, JobResult, JobSearchRequest
from .resume_schema import Resume
from .parser import parse_resume_text
from .llm import propose_chat_edits, propose_job_tailored_edits
from .render import render_resume_to_latex
from .theirstack import search_jobs, map_job
import io
import zipfile
from pathlib import Path

# Load environment variables FIRST
load_dotenv()

# Create FastAPI app BEFORE decorators
app = FastAPI()
logger = logging.getLogger(__name__)

def _parse_allowed_origins() -> List[str]:
        configured = os.getenv("CORS_ALLOWED_ORIGINS", "")
        if configured.strip():
                    return [origin.strip() for origin in configured.split(",") if origin.strip()]

        return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://seamstress-m6lai.ondigitalocean.app",
    ]


AFFIRMATIVE_RE = re.compile(
    r"\b(yes|yep|yeah|yup|sure|ok|okay|please do|go ahead|sounds good|confirm|apply it|do it|looks great)\b",
    re.IGNORECASE,
)

NEGATIVE_RE = re.compile(
    r"\b(no|nope|nah|don't|do not|stop|cancel|never mind|nevermind|not now)\b",
    re.IGNORECASE,
)
NO_CHANGE_RE = re.compile(
    r"\b(nothing|no changes?|looks good|looks fine|it'?s fine|leave it|leave as is|as is|we'?re good|all set|just export|ready to export|good as is)\b",
    re.IGNORECASE,
)
def _is_no_change(message: str) -> bool:
    return bool(NO_CHANGE_RE.search(message.lower()))

def _load_optional_json(key: str) -> Optional[Union[Dict[str, Any], List[Any]]]:
    try:
        raw = get_object_bytes(key)
    except Exception:
        return None
    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        return None


def _save_json(key: str, payload: Union[Dict[str, Any], List[Any]]):
    put_object(key, json.dumps(payload, indent=2).encode("utf-8"), "application/json")


def _is_affirmative(message: str) -> bool:
    return bool(AFFIRMATIVE_RE.search(message.lower()))


def _is_negative(message: str) -> bool:
    return bool(NEGATIVE_RE.search(message.lower()))


def _normalize_chat_request(user_message: str) -> str:
    msg = user_message.strip()
    if not msg:
        return msg

    lowered = msg.lower()
    tokens = re.findall(r"[a-zA-Z']+", lowered)
    short = len(tokens) <= 3

    if short and any(k in lowered for k in ("bullet", "bullets")):
        return (
            "Rewrite all experience and project bullets to be concise, professional, "
            "and ATS-friendly while preserving facts."
        )
    if short and any(k in lowered for k in ("professional", "polish", "improve", "better")):
        return (
            "Polish my resume wording across all experience and project bullets without "
            "adding new facts."
        )
    if short and any(k in lowered for k in ("skills", "tech stack", "stack")):
        return (
            "Improve my resume skills section wording and organization while keeping all "
            "existing facts."
        )
    return msg



@app.get("/health")
def health():
    return {"ok": True}


@app.post("/api/resume", response_model=UploadResumeResponse)
async def upload_resume(file: UploadFile):
    raw_text, raw_bytes = await extract_text(file)

    doc_id = str(uuid.uuid4())
    filename = file.filename or "resume"

    upload_key = f"uploads/{doc_id}/{filename}"
    put_object(upload_key, raw_bytes, file.content_type or "application/octet-stream")

    text_key = f"extracted/{doc_id}/resume.txt"
    put_object(text_key, raw_text.encode("utf-8"), "text/plain; charset=utf-8")

    return UploadResumeResponse(
        doc_id=doc_id,
        filename=filename,
        text_preview=raw_text[:1200],
        text_chars=len(raw_text),
    )


@app.get("/api/resume/{doc_id}/text", response_model=PresignedUrlResponse)
async def get_extracted_text(doc_id: str):
    text_key = f"extracted/{doc_id}/resume.txt"
    url = presigned_get_url(text_key, expires_seconds=3600)
    return PresignedUrlResponse(doc_id=doc_id, upload_key=text_key, download_url=url)

@app.post("/api/resume/{doc_id}/parse")
async def parse_resume(doc_id: str):
    text_key = f"extracted/{doc_id}/resume.txt"
    raw_text = get_object_bytes(text_key).decode("utf-8", errors="replace")

    resume = parse_resume_text(raw_text)

    parsed_key = f"parsed/{doc_id}/resume.json"
    put_object(
        parsed_key,
        resume.model_dump_json(indent=2).encode("utf-8"),
        "application/json",
    )

    return {
        "doc_id": doc_id,
        "parsed_key": parsed_key,
        "resume": resume.model_dump(),
    }


class ChatRequest(BaseModel):
    message: str


class TailorResumeRequest(BaseModel):
    job_description: str


@app.post("/api/resume/{doc_id}/chat")
async def chat_resume(doc_id: str, req: ChatRequest):
    draft_key = f"draft/{doc_id}/resume.json"
    parsed_key = f"parsed/{doc_id}/resume.json"
    history_key = f"chat/{doc_id}/history.json"
    pending_key = f"draft/{doc_id}/pending.json"

    user_message = req.message.strip()
    normalized_user_message = _normalize_chat_request(user_message)
    history: List[Dict[str, str]] = _load_optional_json(history_key) or []
    pending = _load_optional_json(pending_key)
    pending_is_active = bool(pending and pending.get("status") == "pending")

    try:
        raw = get_object_bytes(draft_key)
        source_key = draft_key
    except Exception:
        raw = get_object_bytes(parsed_key)
        source_key = parsed_key

    parsed_json = json.loads(raw.decode("utf-8", errors="replace"))
    resume = Resume.model_validate(parsed_json)

    if pending_is_active and _is_affirmative(user_message):
        updated = Resume.model_validate(pending["resume"])
        put_object(
            draft_key,
            updated.model_dump_json(indent=2).encode("utf-8"),
            "application/json",
        )
        pending["status"] = "applied"
        _save_json(pending_key, pending)
        assistant_message = "Great — I applied the edits and updated your resume. Want to export it now?"
        history.extend(
            [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": assistant_message},
            ]
        )
        _save_json(history_key, history)
        return {
            "doc_id": doc_id,
            "draft_key": draft_key,
            "resume": updated.model_dump(),
            "assistant_message": assistant_message,
            "edits_summary": pending.get("edits_summary", []),
            "needs_confirmation": False,
            "status": "applied",
        }

    if pending_is_active and _is_negative(user_message):
        pending["status"] = "rejected"
        _save_json(pending_key, pending)
        assistant_message = "No problem — tell me what you'd like to change next."
        history.extend(
            [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": assistant_message},
            ]
        )
        _save_json(history_key, history)
        return {
            "doc_id": doc_id,
            "source_key": source_key,
            "resume": resume.model_dump(),
            "assistant_message": assistant_message,
            "needs_confirmation": False,
            "status": "rejected",
        }
    # If user explicitly says no changes needed
    if _is_no_change(user_message) and not pending_is_active:
        assistant_message = (
            "Got it — no changes needed. Want to export it now?"
        )

        history.extend(
            [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": assistant_message},
            ]
        )
        _save_json(history_key, history)

        return {
            "doc_id": doc_id,
            "source_key": source_key,
            "resume": resume.model_dump(),
            "assistant_message": assistant_message,
            "edits_summary": [],
            "needs_confirmation": False,
            "status": "info",
        }
    try:
        proposal = propose_chat_edits(resume, normalized_user_message, history)
    except Exception:
        logger.exception("chat proposal failed for doc_id=%s", doc_id)
        # Never crash on user input; return a safe message
        assistant_message = (
            "I hit a temporary formatting issue while generating your edits. Try again with:\n"
            "- “Rewrite all my experience and project bullets to be more professional.”\n"
            "- “Shorten my bullets to one line each.”\n"
            "- “What should I edit?”"
        )

        history.extend(
            [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": assistant_message},
            ]
        )
        _save_json(history_key, history)

        return {
            "doc_id": doc_id,
            "source_key": source_key,
            "assistant_message": assistant_message,
            "edits_summary": [],
            "proposed_resume": resume.model_dump(),
            "needs_confirmation": False,
            "status": "info",
        }

    # ✅ SUCCESS PATH: set assistant_message from the proposal
    assistant_message = proposal.assistant_message

    history.extend(
        [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_message},
        ]
    )
    _save_json(history_key, history)

    if proposal.needs_confirmation:
        _save_json(
            pending_key,
            {
                "status": "pending",
                "resume": proposal.proposed_resume,
                "edits_summary": proposal.edits_summary,
            },
        )

    return {
        "doc_id": doc_id,
        "source_key": source_key,
        "assistant_message": assistant_message,
        "edits_summary": proposal.edits_summary,
        "proposed_resume": proposal.proposed_resume,
        "needs_confirmation": proposal.needs_confirmation,
        "status": "pending" if proposal.needs_confirmation else "info",
    }


@app.post("/api/resume/{doc_id}/tailor")
async def tailor_resume_for_job(doc_id: str, req: TailorResumeRequest):
    draft_key = f"draft/{doc_id}/resume.json"
    parsed_key = f"parsed/{doc_id}/resume.json"
    pending_key = f"draft/{doc_id}/pending.json"

    job_description = req.job_description.strip()
    if not job_description:
        return {"error": "job_description is required"}

    try:
        raw = get_object_bytes(draft_key)
        source_key = draft_key
    except Exception:
        raw = get_object_bytes(parsed_key)
        source_key = parsed_key

    parsed_json = json.loads(raw.decode("utf-8", errors="replace"))
    resume = Resume.model_validate(parsed_json)

    proposal = propose_job_tailored_edits(resume, job_description)

    _save_json(
        pending_key,
        {
            "status": "pending",
            "resume": proposal.proposed_resume,
            "edits_summary": proposal.edits_summary,
        },
    )

    return {
        "doc_id": doc_id,
        "source_key": source_key,
        "assistant_message": proposal.assistant_message,
        "edits_summary": proposal.edits_summary,
        "proposed_resume": proposal.proposed_resume,
        "needs_confirmation": True,
        "status": "pending",
    }


@app.post("/api/resume/{doc_id}/export")
async def export_resume(doc_id: str):
    # Load draft if it exists, else parsed
    draft_key = f"draft/{doc_id}/resume.json"
    parsed_key = f"parsed/{doc_id}/resume.json"

    try:
        raw = get_object_bytes(draft_key)
        source_key = draft_key
    except Exception:
        raw = get_object_bytes(parsed_key)
        source_key = parsed_key

    resume_json = json.loads(raw.decode("utf-8", errors="replace"))

    # Load template.tex from disk
    template_path = Path(__file__).parent / "latex" / "template.tex"
    if not template_path.exists():
        return {
            "error": "Missing template.tex",
            "expected_path": str(template_path),
            "used_resume_key": source_key,
        }

    template_tex = template_path.read_text(encoding="utf-8")
    rendered_tex = render_resume_to_latex(Resume.model_validate(resume_json), template_tex)

    # Zip it in-memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("resume.json", json.dumps(resume_json, indent=2))
        z.writestr("resume.tex", rendered_tex)

    buf.seek(0)

    export_key = f"exports/{doc_id}/resume_bundle.zip"
    put_object(export_key, buf.read(), "application/zip")

    url = presigned_get_url(export_key, expires_seconds=3600)

    return {
        "doc_id": doc_id,
        "source_key": source_key,
        "export_key": export_key,
        "download_url": url,
    }

@app.post("/api/jobs/search", response_model=JobSearchResponse)
async def jobs_search(req: JobSearchRequest):
    # TheirStack currently only supports filtering by role/title + salary (+ other internal fields),
    # and will reject unknown fields like `location`. So we:
    # 1) Fetch jobs using supported filters
    # 2) Apply location filtering locally on the returned results

    # Pull more than `req.limit` so local filtering still has enough results
    fetch_limit = min(max(req.limit * 5, req.limit), 100)

    raw_jobs = await search_jobs(
        query=req.role,
        min_salary_usd=req.min_salary_usd,
        limit=fetch_limit,
    )

    mapped = [map_job(j) for j in raw_jobs]

    # Local location filter (expects canonical "City, ST" from JobSearchRequest validator)

    # Enforce final limit after local filtering
    mapped = mapped[: req.limit]


    results = [
        JobResult(
            job_id=str(j.get("job_id", "")),
            job_title=j.get("job_title") or "",
            company=j.get("company") or "",
            location=j.get("location") or "",
            salary=j.get("salary"),
            apply_url=j.get("apply_url"),
            description=j.get("description"),
            date_posted=j.get("date_posted"),
        )   
        for j in mapped
    ]

    return JobSearchResponse(role=req.role, results=results)


# this allows the front end deployer to connect
from fastapi.middleware.cors import CORSMiddleware

def _cors_origins_from_env() -> List[str]:
    configured = os.getenv("FRONTEND_ORIGINS", "").strip()
    if configured:
        origins = [o.strip().rstrip("/") for o in configured.split(",") if o.strip()]
        if origins:
            return origins
    return [
        "http://localhost:5173",
        "http://localhost:3000",
        "https://seamstress-m6lai.ondigitalocean.app",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins_from_env(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
