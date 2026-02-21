import uuid
import json
from dotenv import load_dotenv
from pydantic import BaseModel
from fastapi import FastAPI, UploadFile
from .parse import extract_text
from .storage import put_object, presigned_get_url, get_object_bytes
from .models import UploadResumeResponse, PresignedUrlResponse, JobSearchResponse, JobResult, JobSearchRequest
from .resume_schema import Resume
from .parser import parse_resume_text
from .llm import apply_chat_edits
from .theirstack import search_jobs, map_job
import io
import zipfile
from pathlib import Path

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
    template_path = Path(__file__).parent / "templates" / "template.tex"
    if not template_path.exists():
        return {
            "error": "Missing template.tex",
            "expected_path": str(template_path),
            "used_resume_key": source_key,
        }

    template_tex = template_path.read_text(encoding="utf-8")

    # Zip it in-memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("resume.json", json.dumps(resume_json, indent=2))
        z.writestr("template.tex", template_tex)

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
    raw_jobs = await search_jobs(
        query=req.query,
        location_regex=req.location_regex,
        min_salary_usd=req.min_salary_usd,
        limit=req.limit,
    )

    mapped = [map_job(j) for j in raw_jobs]

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

    return JobSearchResponse(query=req.query, results=results)