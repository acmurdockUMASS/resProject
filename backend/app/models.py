from pydantic import BaseModel
from typing import List, Optional

class UploadResumeResponse(BaseModel):
    doc_id: str
    filename: str
    text_preview: str
    text_chars: int


class PresignedUrlResponse(BaseModel):
    doc_id: str
    upload_key: str
    download_url: str

from pydantic import BaseModel
from typing import List, Optional


class UploadResumeResponse(BaseModel):
    doc_id: str
    filename: str
    text_preview: str
    text_chars: int


class PresignedUrlResponse(BaseModel):
    doc_id: str
    upload_key: str
    download_url: str


class JobResult(BaseModel):
    job_title: str
    company: str
    location: str
    salary: Optional[str] = None
    job_id: int
    apply_url: Optional[str] = None


class JobSearchResponse(BaseModel):
    board_token: str
    query: str
    results: List[JobResult]