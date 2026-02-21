from pydantic import BaseModel, root_validator
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
    location_city: Optional[str] = None
    min_salary_usd: Optional[int] = None
    rradius_miles: Optional[int] = None
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

    @root_validator
    def _validate_location_radius(cls, values):
        city = values.get("location_city")
        radius = values.get("radius_miles")

        if radius is not None and (city is None or str(city).strip() == ""):
            raise ValueError("radius_miles requires location_city")
        if radius is not None and radius <= 0:
            raise ValueError("radius_miles must be > 0")
        if values.get("min_salary_usd") is not None and values["min_salary_usd"] <= 0:
            raise ValueError("min_salary_usd must be > 0")

        return values

class JobSearchResponse(BaseModel):
    query: str
    results: List[JobResult]