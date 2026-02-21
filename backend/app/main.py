import uuid
from fastapi import FastAPI, UploadFile
from fastapi.responses import JSONResponse
from .parse import extract_text
from .storage import put_object, presigned_get_url
from .models import UploadResumeResponse, PresignedUrlResponse
from dotenv import load_dotenv
from pydantic import BaseModel
from .resume_schema import Resume
from .llm import apply_chat_edits
from .storage import get_object_bytes
from .llm import structure_resume
from .parser import parse_resume_text
from .storage import get_object_bytes
import json
THEIRSTACK_BASE = "https://api.theirstack.com/v1"
THEIRSTACK_API_KEY = os.getenv("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhY211cmRvY2tAdW1hc3MuZWR1IiwicGVybWlzc2lvbnMiOiJ1c2VyIiwiY3JlYXRlZF9hdCI6IjIwMjYtMDItMjFUMjA6MTY6MjMuODI5NTAzKzAwOjAwIn0.xPrmBu2QaBoAiSVC1cwx1oAIIJN-X1iWxJSta-AUxnk")

@app.post("/api/resume/{doc_id}/parse")
async def parse_resume(doc_id: str):
    text_key = f"extracted/{doc_id}/resume.txt"
    raw_text = get_object_bytes(text_key).decode("utf-8", errors="replace")

    resume = parse_resume_text(raw_text)

    out_key = f"parsed/{doc_id}/resume.json"
    put_object(
        out_key,
        resume.model_dump_json(indent=2).encode("utf-8"),
        "application/json"
    )

    return {
        "doc_id": doc_id,
        "parsed_key": out_key,
        "resume": resume.model_dump()
    }

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


def _theirstack_post(path: str, body: Dict[str, Any], timeout_seconds: int = 20) -> Dict[str, Any]:
    if not THEIRSTACK_API_KEY:
        raise HTTPException(status_code=500, detail="Missing THEIRSTACK_API_KEY in environment")

    url = f"{THEIRSTACK_BASE}{path}"
    data = json.dumps(body).encode("utf-8")

    req = Request(
        url,
        data=data,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {THEIRSTACK_API_KEY}",  # TheirStack auth
            "User-Agent": "resProject/1.0",
        },
    )

    with urlopen(req, timeout=timeout_seconds) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)
class ChatRequest(BaseModel):
    message: str
@app.post("/api/resume/{doc_id}/chat")
async def chat_resume(doc_id: str, req: ChatRequest):

    # 1Load current draft JSON (or parsed if first time)
    draft_key = f"draft/{doc_id}/resume.json"
    parsed_key = f"parsed/{doc_id}/resume.json"

    try:
        raw = get_object_bytes(draft_key)
    except Exception:
        raw = get_object_bytes(parsed_key)

    parsed_json = json.loads(raw.decode("utf-8"))

    # 2️Validate into Resume model
    resume = Resume.model_validate(parsed_json)

    # 3️ Apply AI edits
    updated = apply_chat_edits(resume, req.message)

    # 4️ Save updated draft back to Spaces
    put_object(
        draft_key,
        updated.model_dump_json(indent=2).encode("utf-8"),
        "application/json"
    )

    # 5️ Return updated resume JSON
    return updated.model_dump()

