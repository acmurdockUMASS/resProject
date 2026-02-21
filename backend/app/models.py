from pydantic import BaseModel
from typing import List, Optional
from datetime import date

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
    job_id: int
    job_title: str
    company: str
    location: str
    salary: Optional[str] = None
    apply_url: Optional[str] = None
    description: Optional[str] = None
    date_posted: Optional[date] = None

class JobSearchResponse(BaseModel):
    query: str
    results: List[JobResult]