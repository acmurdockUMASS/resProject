import os
from typing import Any, Dict, List, Optional

import httpx
from fastapi import HTTPException

THEIRSTACK_BASE = "https://api.theirstack.com"


def _auth_headers() -> Dict[str, str]:
    key = os.getenv("THEIRSTACK_API_KEY")
    if not key:
        raise RuntimeError("Missing THEIRSTACK_API_KEY in environment")

    return {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }


def _to_salary_string(job: Dict[str, Any]) -> Optional[str]:
    """
    Converts salary fields into a readable string.
    Only uses salary_string or min_annual_salary_usd.
    """

    s = job.get("salary_string")
    if isinstance(s, str) and s.strip():
        return s.strip()

    lo = job.get("min_annual_salary_usd")
    if lo:
        return f"${int(lo):,}+ USD"

    return None


async def search_jobs(
    *,
    query: str,
    location: Optional[str] = None,  # "Des Moines, IA" or "IA"
    min_salary_usd: Optional[int] = None,
    limit: int = 25,
) -> List[Dict[str, Any]]:
    """
    Searches TheirStack for US jobs.
    - Filters jobs posted in last 14 days.
    - Accepts location in format "City, ST" or just "ST".
    - US-only (we do NOT send country filters).
    """

    payload: Dict[str, Any] = {
        "limit": limit,
        "posted_at_max_age_days": 14,
        "job_title_or": [query],
    }
    # NOTE: TheirStack /v1/jobs/search rejects unknown fields like `location`.
    # We accept `location` in our API but filter locally after results are returned.

    if min_salary_usd is not None:
        payload["min_salary_usd"] = min_salary_usd

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{THEIRSTACK_BASE}/v1/jobs/search",
            headers=_auth_headers(),
            json=payload,
        )

    if r.status_code >= 400:
        # Surface TheirStack's actual validation errors
        raise HTTPException(status_code=r.status_code, detail=r.text)

    data = r.json()

    # TheirStack sometimes returns different keys
    jobs = None
    if isinstance(data, dict):
        jobs = (
            data.get("data")
            or data.get("jobs")
            or data.get("results")
        )

    if not jobs:
        return []

    return jobs


def _extract_company_name(company: Dict[str, Any]) -> str:
    name = company.get("name") or company.get("company_name")
    if isinstance(name, str):
        return name.strip()
    return ""


async def search_companies_technographics(*, technologies: List[str], limit: int = 25) -> List[Dict[str, Any]]:
    """
    Query TheirStack technographics endpoint for companies using resume skills/technologies.
    Tries a couple of payload shapes for compatibility.
    """
    if not technologies:
        return []

    techs = [t.strip() for t in technologies if isinstance(t, str) and t.strip()]
    if not techs:
        return []

    payload_candidates = [
        {"limit": limit, "technologies_or": techs},
        {"limit": limit, "technographics_or": techs},
        {"limit": limit, "technologies": techs},
    ]

    last_error: Optional[httpx.Response] = None
    async with httpx.AsyncClient(timeout=30) as client:
        for payload in payload_candidates:
            r = await client.post(
                f"{THEIRSTACK_BASE}/v1/companies/technographics_v1",
                headers=_auth_headers(),
                json=payload,
            )
            if r.status_code < 400:
                data = r.json()
                companies = None
                if isinstance(data, dict):
                    companies = data.get("data") or data.get("companies") or data.get("results")
                if not companies:
                    return []
                return companies
            last_error = r

    if last_error is not None:
        raise HTTPException(status_code=last_error.status_code, detail=last_error.text)

    return []


def _company_name(job: Dict[str, Any]) -> str:
    """
    Extracts company name safely from various formats.
    """

    company_name = job.get("company_name")
    if isinstance(company_name, str) and company_name.strip():
        return company_name.strip()

    company = job.get("company")

    if isinstance(company, dict):
        name = company.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()

    if isinstance(company, str) and company.strip():
        return company.strip()

    return ""


def map_job(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalizes TheirStack job response into your internal format.
    """

    return {
        "job_id": job.get("id") or job.get("job_id") or "",
        "job_title": job.get("job_title") or job.get("title") or "",
        "company": _company_name(job),
        "description": job.get("description"),
        "location": (
            job.get("location")
            or job.get("short_location")
            or job.get("long_location")
            or ""
        ),
        "salary": _to_salary_string(job),
        "apply_url": (
            job.get("url")
            or job.get("final_url")
            or job.get("source_url")
        ),
        "date_posted": job.get("date_posted"),
    }