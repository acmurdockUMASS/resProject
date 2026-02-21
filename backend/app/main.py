import os
import uuid
import json
from typing import Dict, Any, List

from fastapi import FastAPI, UploadFile, HTTPException, Query
from pydantic import BaseModel
from dotenv import load_dotenv
from urllib.request import Request, urlopen

from .parse import extract_text
from .parser import parse_resume_text
from .storage import put_object, presigned_get_url, get_object_bytes
from .models import UploadResumeResponse, PresignedUrlResponse, JobResult, JobSearchResponse
from .resume_schema import Resume
from .llm import structure_resume, apply_chat_edits

load_dotenv()

app = FastAPI()

THEIRSTACK_BASE = "https://api.theirstack.com/v1"
THEIRSTACK_API_KEY = os.getenv("THEIRSTACK_API_KEY")


# ------------------ HEALTH ------------------

@app.get("/health")
def health():
    return {"ok": True}


# ------------------ RESUME UPLOAD ------------------

@app.post("/api/resume", response_model=UploadResumeResponse)
async def upload_resume(file: UploadFile):
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


# ------------------ PARSE ------------------

@app.post("/api/resume/{doc_id}/parse")
async def parse_resume(doc_id: str):
    text_key = f"extracted/{doc_id}/resume.txt"
    raw_text = get_object_bytes(text_key).decode("utf-8")

    resume = parse_resume_text(raw_text)

    out_key = f"parsed/{doc_id}/resume.json"
    put_object(out_key, resume.model_dump_json(indent=2).encode(), "application/json")

    return {"doc_id": doc_id, "resume": resume.model_dump()}


# ------------------ STRUCTURE ------------------

class StructureRequest(BaseModel):
    extra_experience: str = ""


@app.post("/api/resume/{doc_id}/structure")
async def structure_resume_endpoint(doc_id: str, req: StructureRequest):
    text_key = f"extracted/{doc_id}/resume.txt"
    raw_text = get_object_bytes(text_key).decode("utf-8")

    resume = structure_resume(raw_text, req.extra_experience)

    out_key = f"structured/{doc_id}/resume.json"
    put_object(out_key, resume.model_dump_json(indent=2).encode(), "application/json")

    return resume.model_dump()


# ------------------ CHAT EDITS ------------------

class ChatRequest(BaseModel):
    message: str


@app.post("/api/resume/{doc_id}/chat")
async def chat_resume(doc_id: str, req: ChatRequest):

    draft_key = f"draft/{doc_id}/resume.json"
    parsed_key = f"parsed/{doc_id}/resume.json"

    try:
        raw = get_object_bytes(draft_key)
    except Exception:
        raw = get_object_bytes(parsed_key)

    resume = Resume.model_validate(json.loads(raw.decode()))

    updated = apply_chat_edits(resume, req.message)

    put_object(draft_key, updated.model_dump_json(indent=2).encode(), "application/json")

    return updated.model_dump()


# ------------------ THEIRSTACK ------------------

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
):

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
            )
        )

    return JobSearchResponse(query=q, results=results)