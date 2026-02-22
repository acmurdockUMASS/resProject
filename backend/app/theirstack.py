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
    Only uses salary_string or min_annual_salary_usd.
    No max salary handling.
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
    country: Optional[str] = None,
    min_salary_usd: Optional[int] = None,
    limit: int = 25,
) -> List[Dict[str, Any]]:
    """
    Returns raw job dicts from TheirStack.
    Filters out anything older than 14 days.
    """

    payload: Dict[str, Any] = {
        "limit": limit,
        "posted_at_max_age_days": 14,
        "job_title_or": [query],
    }

    if country:
        payload["job_country_or"] = [country]

    if min_salary_usd is not None:
        payload["min_salary_usd"] = min_salary_usd

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{THEIRSTACK_BASE}/v1/jobs/search",
            headers=_auth_headers(),
            json=payload,
    )

    if r.status_code >= 400:
        # show TheirStack's exact error instead of generic 500
        detail = r.text
        raise HTTPException(status_code=r.status_code, detail=detail)

    data = r.json()

    jobs = data.get("data") if isinstance(data, dict) else None
    if jobs is None:
        jobs = (
            data.get("jobs") if isinstance(data, dict) else None
        ) or (
            data.get("results") if isinstance(data, dict) else None
        ) or []

    return jobs


def _company_name(job: Dict[str, Any]) -> str:
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
    return {
        "job_id": job.get("id") or job.get("job_id") or "",
        "job_title": job.get("job_title") or job.get("title") or "",
        "company": _company_name(job),
        "description": job.get("description"),
        "location": job.get("location")
        or job.get("short_location")
        or job.get("long_location")
        or "",
        "salary": _to_salary_string(job),
        "apply_url": job.get("url")
        or job.get("final_url")
        or job.get("source_url"),
        "date_posted": job.get("date_posted"),
    }