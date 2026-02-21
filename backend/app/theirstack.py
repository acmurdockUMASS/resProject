import os
from typing import Any, Dict, List, Optional

import httpx

THEIRSTACK_BASE = "https://api.theirstack.com"

def _auth_headers() -> Dict[str, str]:
    key = os.getenv("THEIRSTACK_API_KEY")
    if not key:
        raise RuntimeError("Missing THEIRSTACK_API_KEY in environment")
    return {"Authorization": f"Bearer {key}", "Accept": "application/json"}

def _to_salary_string(job: Dict[str, Any]) -> Optional[str]:
    # TheirStack often returns salary_string, plus min/max salary fields.
    s = job.get("salary_string")
    if s:
        return s
    lo = job.get("min_annual_salary_usd")
    
    if lo and hi:
        return f"${int(lo):,} - ${int(hi):,} USD"
    if lo:
        return f"${int(lo):,}+ USD"
    if hi:
        return f"Up to ${int(hi):,} USD"
    return None

async def search_jobs(
    *,
    query: str,
    location_regex: Optional[str] = None,
    min_salary_usd: Optional[int] = None,
    
    limit: int = 25,
) -> List[Dict[str, Any]]:
    """
    Returns raw job dicts from TheirStack.
    Filters out anything older than 14 days by using posted_at_max_age_days=14.
    """
    payload: Dict[str, Any] = {
        "limit": limit,
        "posted_at_max_age_days": 14,  # filters out posts older than ~14 days
        "job_title_or": [query],        # treat your query as a title match
        # you can also use job_description_contains_or, job_title_pattern_or, etc.
    }

    if location_regex:
        payload["job_location_pattern_or"] = [location_regex]  # e.g. "Massachusetts|Boston|Remote"

    if min_salary_usd is not None:
        payload["min_salary_usd"] = min_salary_usd


    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{THEIRSTACK_BASE}/v1/jobs/search",
            headers=_auth_headers(),
            json=payload,
        )
        r.raise_for_status()
        data = r.json()

    # TheirStack returns a list under "data" in many endpoints; keep this defensive:
    jobs = data.get("data") if isinstance(data, dict) else None
    if jobs is None:
        # sometimes docs/examples use "jobs" or "results"
        jobs = data.get("jobs") or data.get("results") or []
    return jobs

def _company_name(job: Dict[str, Any]) -> str:
    # Prefer explicit company_name
    if isinstance(job.get("company_name"), str) and job["company_name"].strip():
        return job["company_name"].strip()

    company = job.get("company")

    # company sometimes is {"name": "..."}
    if isinstance(company, dict):
        name = company.get("name")
        if isinstance(name, str):
            return name.strip()

    # company sometimes is "Acme Inc"
    if isinstance(company, str):
        return company.strip()

    return ""


def map_job(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map TheirStack job record to the fields you want.
    """
    return {
        "job_id": job.get("id") or job.get("job_id"),
        "job_title": job.get("job_title") or job.get("title") or "",
        "company": _company_name(job),
        "description": job.get("description"),
        "location": job.get("location") or job.get("short_location") or job.get("long_location") or "",
        "salary": _to_salary_string(job),
        "apply_url": job.get("url") or job.get("final_url") or job.get("source_url"),
        "date_posted": job.get("date_posted"),
    }