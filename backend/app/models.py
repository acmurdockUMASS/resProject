from pydantic import BaseModel, model_validator
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
    role: str
    country: Optional[str] = None
    min_salary_usd: Optional[int] = None
    limit: int = 10

    @model_validator(mode="after")
    def validate_salary(self):
        if self.min_salary_usd is not None and self.min_salary_usd <= 0:
            raise ValueError("min_salary_usd must be > 0")
        return self


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
    role: str
    results: List[JobResult]