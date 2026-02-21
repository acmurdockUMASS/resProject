import uuid
import json
from dotenv import load_dotenv
from pydantic import BaseModel
from fastapi import FastAPI, UploadFile
from .parse import extract_text
from .storage import put_object, presigned_get_url, get_object_bytes
from .models import UploadResumeResponse, PresignedUrlResponse, JobSearchResponse, JobResult 
from .resume_schema import Resume
from .parser import parse_resume_text
from .llm import apply_chat_edits
from .theirstack import search_jobs, map_job

# Load environment variables FIRST
load_dotenv()

# Create FastAPI app BEFORE decorators
app = FastAPI()



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


@app.post("/api/resume/{doc_id}/chat")
async def chat_resume(doc_id: str, req: ChatRequest):
    draft_key = f"draft/{doc_id}/resume.json"
    parsed_key = f"parsed/{doc_id}/resume.json"

    try:
        raw = get_object_bytes(draft_key)
    except Exception:
        raw = get_object_bytes(parsed_key)

    parsed_json = json.loads(raw.decode("utf-8"))
    resume = Resume.model_validate(parsed_json)

    updated = apply_chat_edits(resume, req.message)

    put_object(
        draft_key,
        updated.model_dump_json(indent=2).encode("utf-8"),
        "application/json",
    )

    return {
        "doc_id": doc_id,
        "draft_key": draft_key,
        "resume": updated.model_dump(),
    }


@app.post("/api/jobs/search", response_model=JobSearchResponse)
async def jobs_search(req: JobSearchRequest):
    raw_jobs = await search_jobs(
        query=req.query,
        location_regex=req.location_regex,
        min_salary_usd=req.min_salary_usd,
        max_salary_usd=req.max_salary_usd,
        limit=req.limit,
    )
    mapped = [map_job(j) for j in raw_jobs]

    # Adapt to your current JobResult model (you may want to add description/date_posted there)
    results = [
        JobResult(
            job_id=j["job_id"],
            job_title=j["job_title"] or "",
            company=j["company"] or "",
            location=j["location"] or "",
            salary=j["salary"],
            apply_url=j["apply_url"],
        )
        for j in mapped
    ]

    return JobSearchResponse(query=req.query, results=results)