from typing import List, Optional

from pydantic import BaseModel


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
    description: str = ""


class JobSearchResponse(BaseModel):
    query: str
    results: List[JobResult]


class TailorResumeRequest(BaseModel):
    job_description: str
    job_title: Optional[str] = None
    company: Optional[str] = None
