from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, model_validator


class UploadResumeResponse(BaseModel):
    doc_id: str
    filename: str
    text_preview: str
    text_chars: int


class PresignedUrlResponse(BaseModel):
    doc_id: str
    upload_key: str
    download_url: str


US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}


class JobSearchRequest(BaseModel):
    role: str
    location: Optional[str] = None  # Expected "City, ST" (e.g., "Boston, MA")
    min_salary_usd: Optional[int] = None
    limit: int = 10

    @model_validator(mode="after")
    def validate_request(self) -> "JobSearchRequest":
        # Salary validation
        if self.min_salary_usd is not None and self.min_salary_usd <= 0:
            raise ValueError("min_salary_usd must be > 0")

        # Normalize + validate location
        if self.location is not None:
            loc = self.location.strip()
            if loc == "":
                self.location = None
                return self

            # Require "City, ST"
            if "," not in loc:
                raise ValueError("location must be in format 'City, ST' (e.g., 'Boston, MA')")

            city, state = [part.strip() for part in loc.split(",", 1)]
            if city == "":
                raise ValueError("location city part cannot be empty (expected 'City, ST')")

            state = state.upper()
            if state == "":
                raise ValueError("location state part cannot be empty (expected 'City, ST')")

            if len(state) != 2 or state not in US_STATES:
                raise ValueError("state must be a valid 2-letter US state code (e.g., 'MA')")

            # Canonical formatting
            self.location = f"{city}, {state}"

        # Limit sanity (optional but helpful)
        if self.limit <= 0:
            raise ValueError("limit must be > 0")

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