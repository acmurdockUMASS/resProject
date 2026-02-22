import uuid
import json
import re
from typing import Any, Dict, List, Optional, Union
from dotenv import load_dotenv
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi import FastAPI, HTTPException, UploadFile
from .parse import extract_text
from .storage import put_object, presigned_get_url, get_object_bytes
from .models import UploadResumeResponse, PresignedUrlResponse, JobSearchResponse, JobResult, JobSearchRequest
from .resume_schema import Resume
from .parser import parse_resume_text
from .llm import propose_chat_edits, propose_job_tailored_edits
from .render import render_resume_to_latex
from .theirstack import search_jobs, map_job, search_companies_technographics
import io
import zipfile
from pathlib import Path
import re
# Load environment variables FIRST
load_dotenv()

# Create FastAPI app BEFORE decorators
app = FastAPI()


AFFIRMATIVE_RE = re.compile(r"\b(yes|yep|yeah|yup|sure|ok|okay|please do|go ahead|sounds good|confirm)\b")
NEGATIVE_RE = re.compile(r"\b(no|nope|nah|don't|do not|stop|cancel|never mind|nevermind)\b")


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

    proposal = propose_chat_edits(resume, user_message, history)
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
        try:
            raw = get_object_bytes(parsed_key)
            source_key = parsed_key
        except Exception as exc:
            raise HTTPException(
                status_code=404,
                detail="Resume not found for this doc_id. Upload and parse a resume before tailoring.",
            ) from exc

    parsed_json = json.loads(raw.decode("utf-8", errors="replace"))
    resume = Resume.model_validate(parsed_json)

    try:
        proposal = propose_job_tailored_edits(resume, job_description)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Unable to generate a complete tailored resume response from Gemini. Please try again.",
        ) from exc

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


@app.post("/api/resume/{doc_id}/job-match")
async def job_match_from_resume(doc_id: str):
    draft_key = f"draft/{doc_id}/resume.json"
    parsed_key = f"parsed/{doc_id}/resume.json"

    try:
        raw = get_object_bytes(draft_key)
        source_key = draft_key
    except Exception:
        raw = get_object_bytes(parsed_key)
        source_key = parsed_key

    resume = Resume.model_validate(json.loads(raw.decode("utf-8", errors="replace")))

    skills: List[str] = []
    skills.extend(resume.skills.languages)
    skills.extend(resume.skills.frameworks)
    skills.extend(resume.skills.tools)
    skills.extend(resume.skills.concepts)
    for _, grouped in resume.skills.categories.items():
        skills.extend(grouped)
    for project in resume.projects:
        skills.extend(project.stack)

    normalized_skills: List[str] = []
    seen = set()
    for skill in skills:
        cleaned = skill.strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            normalized_skills.append(cleaned)

    top_skills = normalized_skills[:12]
    if not top_skills:
        return {
            "doc_id": doc_id,
            "source_key": source_key,
            "skills_used": [],
            "recommended_jobs": [],
            "message": "No skills found on resume to run company/job matching.",
        }

    companies = await search_companies_technographics(technologies=top_skills, limit=40)
    company_names = {
        (c.get("name") or c.get("company_name") or "").strip().lower()
        for c in companies
        if isinstance(c, dict) and ((c.get("name") or c.get("company_name") or "").strip())
    }

    query_terms = top_skills[:3] or ["software engineer"]
    raw_jobs: List[Dict[str, Any]] = []
    seen_job_ids = set()
    for term in query_terms:
        jobs = await search_jobs(query=term, limit=40)
        for job in jobs:
            job_id = str(job.get("id") or job.get("job_id") or "")
            if job_id and job_id in seen_job_ids:
                continue
            if job_id:
                seen_job_ids.add(job_id)
            raw_jobs.append(job)

    mapped = [map_job(j) for j in raw_jobs]

    def _score(job: Dict[str, Any]) -> int:
        text = f"{job.get('job_title','')} {job.get('description','') or ''}".lower()
        score = sum(1 for skill in top_skills if skill.lower() in text)
        if (job.get("company") or "").strip().lower() in company_names:
            score += 4
        return score

    ranked = sorted(mapped, key=_score, reverse=True)
    recommended_jobs = []
    for job in ranked:
        score = _score(job)
        if score <= 0:
            continue
        recommended_jobs.append(
            {
                "job": job,
                "match_score": score,
                "recommendation": "Recommended: tailor your resume for this listing and apply.",
            }
        )
        if len(recommended_jobs) >= 10:
            break

    return {
        "doc_id": doc_id,
        "source_key": source_key,
        "skills_used": top_skills,
        "matched_company_count": len(company_names),
        "recommended_jobs": recommended_jobs,
    }
