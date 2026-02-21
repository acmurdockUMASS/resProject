import uuid
from fastapi import FastAPI, UploadFile
from fastapi.responses import JSONResponse
from .parse import extract_text
from .storage import put_object, presigned_get_url
from .models import UploadResumeResponse, PresignedUrlResponse
from dotenv import load_dotenv
from pydantic import BaseModel
from .storage import get_object_bytes
from .llm import structure_resume
import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import HTTPException, Query

from .models import JobResult, JobSearchResponse


GREENHOUSE_BASE = "https://boards-api.greenhouse.io/v1/boards"
load_dotenv()
app = FastAPI()


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/api/resume", response_model=UploadResumeResponse)
async def upload_resume(file: UploadFile):
    raw_text, raw_bytes = await extract_text(file)

    doc_id = str(uuid.uuid4())
    filename = file.filename or "resume"

    # Store original upload
    upload_key = f"uploads/{doc_id}/{filename}"
    put_object(upload_key, raw_bytes, file.content_type or "application/octet-stream")

    # Store extracted text
    text_key = f"extracted/{doc_id}/resume.txt"
    put_object(text_key, raw_text.encode("utf-8"), "text/plain; charset=utf-8")

    preview = raw_text[:1200]

    return UploadResumeResponse(
        doc_id=doc_id,
        filename=filename,
        text_preview=preview,
        text_chars=len(raw_text),
    )


@app.get("/api/resume/{doc_id}/text", response_model=PresignedUrlResponse)
async def get_extracted_text(doc_id: str):
    text_key = f"extracted/{doc_id}/resume.txt"
    url = presigned_get_url(text_key, expires_seconds=3600)
    return PresignedUrlResponse(doc_id=doc_id, upload_key=text_key, download_url=url)
class StructureRequest(BaseModel):
    extra_experience: str = ""


@app.post("/api/resume/{doc_id}/structure")
async def structure_resume_endpoint(doc_id: str, req: StructureRequest):
    # 1. Load extracted resume text
    text_key = f"extracted/{doc_id}/resume.txt"
    raw_text = get_object_bytes(text_key).decode("utf-8", errors="replace")

    # 2. Send to Gemini → structured JSON (Pydantic model)
    resume = structure_resume(raw_text, req.extra_experience)

    # 3. Store structured JSON
    out_key = f"structured/{doc_id}/resume.json"
    put_object(
        out_key,
        resume.model_dump_json(indent=2).encode("utf-8"),
        "application/json",
    )

    # 4. Return JSON
    return resume.model_dump()

def _fetch_json(url: str, timeout_seconds: int = 15) -> Dict[str, Any]:
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "resProject/1.0"})
    with urlopen(req, timeout=timeout_seconds) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def _money_from_cents(cents: Optional[int]) -> Optional[str]:
    if cents is None:
        return None
    # Greenhouse uses cents in pay_input_ranges
    dollars = int(round(cents / 100.0))
    return f"{dollars:,}"


def _format_salary_from_pay_input_ranges(pay_input_ranges: Any) -> Optional[str]:
    if not isinstance(pay_input_ranges, list) or not pay_input_ranges:
        return None

    # Use the first range (you can improve this to pick by location/title)
    r = pay_input_ranges[0] or {}
    min_c = r.get("min_cents")
    max_c = r.get("max_cents")
    cur = r.get("currency_type")

    min_s = _money_from_cents(min_c)
    max_s = _money_from_cents(max_c)

    if min_s and max_s and cur:
        return f"{min_s}–{max_s} {cur}"
    if min_s and max_s:
        return f"{min_s}–{max_s}"
    if min_s and cur:
        return f"{min_s}+ {cur}"
    if min_s:
        return f"{min_s}+"
    return None


def _matches_query(job: Dict[str, Any], q: str) -> bool:
    q = (q or "").strip().lower()
    if not q:
        return True

    title = (job.get("title") or "").lower()
    loc = ((job.get("location") or {}).get("name") or "").lower()

    # Optional: search in department/office names if content=true
    dept_names = " ".join([(d.get("name") or "") for d in (job.get("departments") or [])]).lower()
    office_names = " ".join([(o.get("name") or "") for o in (job.get("offices") or [])]).lower()

    hay = " ".join([title, loc, dept_names, office_names])
    # simple token matching
    tokens = [t for t in re.split(r"\s+", q) if t]
    return all(t in hay for t in tokens)


@app.get("/api/jobs/search", response_model=JobSearchResponse)
def search_greenhouse_jobs(
    board_token: str = Query(..., description="Greenhouse board token, e.g. 'openai' for boards.greenhouse.io/openai"),
    q: str = Query("", description="User search query (keywords)"),
    limit: int = Query(10, ge=1, le=25, description="Max results returned"),
):
    # 1) List jobs (public)
    list_url = f"{GREENHOUSE_BASE}/{board_token}/jobs?" + urlencode({"content": "true"})
    try:
        payload = _fetch_json(list_url)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch job list: {e}")

    jobs = payload.get("jobs") or []
    matched = [j for j in jobs if _matches_query(j, q)]
    matched = matched[:limit]

    results: List[JobResult] = []

    # 2) For each matched job, fetch salary via pay_transparency=true (job details)
    for job in matched:
        job_id = job.get("id")
        title = job.get("title") or ""
        location = (job.get("location") or {}).get("name") or ""
        apply_url = job.get("absolute_url")

        salary: Optional[str] = None
        if job_id is not None:
            detail_url = f"{GREENHOUSE_BASE}/{board_token}/jobs/{job_id}?" + urlencode({"pay_transparency": "true"})
            try:
                detail = _fetch_json(detail_url)
                salary = _format_salary_from_pay_input_ranges(detail.get("pay_input_ranges"))
            except Exception:
                # If salary fetch fails, still return the job
                salary = None

        results.append(
            JobResult(
                job_title=title,
                company=board_token,
                location=location,
                salary=salary or "Not listed",
                job_id=int(job_id) if job_id is not None else -1,
                apply_url=apply_url,
            )
        )

    return JobSearchResponse(board_token=board_token, query=q, results=results)