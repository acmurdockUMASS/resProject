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