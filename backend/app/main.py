import json
import os
import uuid
from typing import Any, Dict, List
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException, Query, UploadFile
from pydantic import BaseModel

from .models import (
    JobResult,
    JobSearchResponse,
    TailorResumeRequest,
    UploadResumeResponse,
)
from .parse import extract_text
from .parser import parse_resume_text
from .resume_schema import Resume
from .storage import get_object_bytes, put_object

app = FastAPI()

THEIRSTACK_BASE = "https://api.theirstack.com/v1"
THEIRSTACK_API_KEY = os.getenv("THEIRSTACK_API_KEY")


def _get_llm_function(name: str):
    try:
        from . import llm as llm_module
    except Exception as exc:  # pragma: no cover - defensive startup/runtime guard
        raise HTTPException(status_code=500, detail=f"LLM module unavailable: {exc}") from exc

    fn = getattr(llm_module, name, None)
    if fn is None:
        raise HTTPException(status_code=500, detail=f"LLM function unavailable: {name}")
    return fn


@app.get("/health")
def health() -> Dict[str, bool]:
    return {"ok": True}


@app.post("/api/resume", response_model=UploadResumeResponse)
async def upload_resume(file: UploadFile) -> UploadResumeResponse:
    raw_text, raw_bytes = await extract_text(file)

    doc_id = str(uuid.uuid4())
    filename = file.filename or "resume"

    upload_key = f"uploads/{doc_id}/{filename}"
    put_object(upload_key, raw_bytes, file.content_type or "application/octet-stream")

    text_key = f"extracted/{doc_id}/resume.txt"
    put_object(text_key, raw_text.encode("utf-8"), "text/plain")

    return UploadResumeResponse(
        doc_id=doc_id,
        filename=filename,
        text_preview=raw_text[:1200],
        text_chars=len(raw_text),
    )


@app.post("/api/resume/{doc_id}/parse")
async def parse_resume(doc_id: str) -> Dict[str, Any]:
    text_key = f"extracted/{doc_id}/resume.txt"
    raw_text = get_object_bytes(text_key).decode("utf-8")

    resume = parse_resume_text(raw_text)

    out_key = f"parsed/{doc_id}/resume.json"
    put_object(out_key, resume.model_dump_json(indent=2).encode(), "application/json")

    return {"doc_id": doc_id, "resume": resume.model_dump()}


class StructureRequest(BaseModel):
    extra_experience: str = ""


@app.post("/api/resume/{doc_id}/structure")
async def structure_resume_endpoint(doc_id: str, req: StructureRequest) -> Dict[str, Any]:
    text_key = f"extracted/{doc_id}/resume.txt"
    raw_text = get_object_bytes(text_key).decode("utf-8")

    structure_fn = _get_llm_function("structure_resume")
    resume = structure_fn(raw_text, req.extra_experience)

    out_key = f"structured/{doc_id}/resume.json"
    put_object(out_key, resume.model_dump_json(indent=2).encode(), "application/json")

    return resume.model_dump()


class ChatRequest(BaseModel):
    message: str


def _load_latest_resume(doc_id: str) -> Resume:
    candidate_keys = [
        f"draft/{doc_id}/resume.json",
        f"tailored/{doc_id}/resume.json",
        f"structured/{doc_id}/resume.json",
        f"parsed/{doc_id}/resume.json",
    ]

    for key in candidate_keys:
        try:
            raw = get_object_bytes(key)
            return Resume.model_validate(json.loads(raw.decode()))
        except Exception:
            continue

    raise HTTPException(
        status_code=404,
        detail="No resume draft found for this doc_id. Parse or structure resume first.",
    )


@app.post("/api/resume/{doc_id}/chat")
async def chat_resume(doc_id: str, req: ChatRequest) -> Dict[str, Any]:
    resume = _load_latest_resume(doc_id)
    chat_fn = _get_llm_function("apply_chat_edits")
    updated = chat_fn(resume, req.message)

    draft_key = f"draft/{doc_id}/resume.json"
    put_object(draft_key, updated.model_dump_json(indent=2).encode(), "application/json")

    return updated.model_dump()


@app.post("/api/resume/{doc_id}/tailor")
async def tailor_resume(doc_id: str, req: TailorResumeRequest) -> Dict[str, Any]:
    resume = _load_latest_resume(doc_id)

    job_description = req.job_description.strip() if req.job_description else ""
    if not job_description:
        raise HTTPException(status_code=400, detail="job_description is required")

    tailor_fn = _get_llm_function("tailor_resume_for_job")
    tailored = tailor_fn(
        resume=resume,
        job_description=job_description,
        job_title=req.job_title,
        company=req.company,
    )

    tailored_key = f"tailored/{doc_id}/resume.json"
    draft_key = f"draft/{doc_id}/resume.json"

    payload = tailored.model_dump_json(indent=2).encode()
    put_object(tailored_key, payload, "application/json")
    put_object(draft_key, payload, "application/json")

    return tailored.model_dump()



def _theirstack_post(path: str, body: Dict[str, Any]) -> Dict[str, Any]:
    if not THEIRSTACK_API_KEY:
        raise HTTPException(status_code=500, detail="Missing THEIRSTACK_API_KEY")

    req = Request(
        f"{THEIRSTACK_BASE}{path}",
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {THEIRSTACK_API_KEY}",
            "Content-Type": "application/json",
        },
    )

    with urlopen(req) as resp:
        return json.loads(resp.read().decode())


@app.get("/api/jobs/search", response_model=JobSearchResponse)
def search_jobs(
    q: str = Query(...),
    location: str = Query(""),
    min_salary_usd: int = Query(0),
    max_age_days: int = Query(14),
    limit: int = Query(20),
    offset: int = Query(0),
) -> JobSearchResponse:
    body: Dict[str, Any] = {
        "offset": offset,
        "limit": limit,
        "posted_at_max_age_days": max_age_days,
        "job_title_or": [q],
    }

    if location:
        body["job_location_or"] = [location]

    if min_salary_usd > 0:
        body["min_annual_salary_usd_gte"] = float(min_salary_usd)

    payload = _theirstack_post("/jobs/search", body)

    jobs = payload.get("data", [])
    results: List[JobResult] = []

    for j in jobs:
        results.append(
            JobResult(
                job_title=j.get("job_title", ""),
                company=j.get("company_name", ""),
                location=j.get("location", ""),
                salary=j.get("salary_string", "Not listed"),
                job_id=int(j.get("id", -1)),
                apply_url=j.get("url"),
                description=(j.get("description") or j.get("job_description") or ""),
            )
        )

    return JobSearchResponse(query=q, results=results)
