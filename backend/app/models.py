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


class JobSearchRequest(BaseModel):
    query: str
    location_regex: Optional[str] = None
    min_salary_usd: Optional[int] = None
    limit: int = 10

class JobResult(BaseModel):
    job_id: str
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