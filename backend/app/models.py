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


US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA",
    "HI","ID","IL","IN","IA","KS","KY","LA","ME","MD",
    "MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
    "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC",
    "SD","TN","TX","UT","VT","VA","WA","WV","WI","WY",
    "DC"
}

class JobSearchRequest(BaseModel):
    role: str
    city: Optional[str] = None
    state: Optional[str] = None  # 2-letter, e.g. "IA"
    min_salary_usd: Optional[int] = None
    limit: int = 10

    @model_validator(mode="after")
    def validate_request(self):
        if self.min_salary_usd is not None and self.min_salary_usd <= 0:
            raise ValueError("min_salary_usd must be > 0")

        # Normalize
        if self.city is not None:
            self.city = self.city.strip()
            if self.city == "":
                self.city = None

        if self.state is not None:
            self.state = self.state.strip().upper()
            if self.state == "":
                self.state = None

        # Enforce "US only": require a US state if location is provided at all
        if self.city and not self.state:
            raise ValueError("state is required when city is provided")

        if self.state and self.state not in US_STATES:
            raise ValueError("state must be a valid 2-letter US state code (e.g., 'IA')")

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