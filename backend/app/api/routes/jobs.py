import base64
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.enums import JobStatus, WorkerStatus
from app.models.job import Job
from app.models.worker import Worker
from app.schemas.job import (
    JobClaimRequest,
    JobClaimResponse,
    JobCreateRequest,
    JobResponse,
    JobStatusUpdateRequest,
)
from app.services.claim import claim_next_job


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


ALLOWED_TRANSITIONS = {
    JobStatus.DISCOVERED.value: {JobStatus.QUEUED.value},
    JobStatus.QUEUED.value: {JobStatus.CLAIMED.value, JobStatus.DUPLICATE.value},
    JobStatus.CLAIMED.value: {JobStatus.APPLYING.value, JobStatus.QUEUED.value},
    JobStatus.APPLYING.value: {
        JobStatus.BLOCKED_WAITING_FOR_USER.value,
        JobStatus.REVIEW.value,
        JobStatus.SUBMITTED.value,
        JobStatus.FAILED.value,
        JobStatus.SKIPPED.value,
        JobStatus.QUEUED.value,
    },
    JobStatus.REVIEW.value: {
        JobStatus.SUBMITTED.value,
        JobStatus.FAILED.value,
        JobStatus.SKIPPED.value,
        JobStatus.QUEUED.value,
    },
    JobStatus.BLOCKED_WAITING_FOR_USER.value: {JobStatus.APPLYING.value, JobStatus.SKIPPED.value},
}

router = APIRouter(prefix="/jobs", tags=["jobs"])

# In-memory stores
_submit_signals: dict[str, str] = {}
_evidence: dict[str, dict] = {}  # job_id -> evidence dict


@router.post("", response_model=JobResponse)
def create_job(payload: JobCreateRequest, db: Session = Depends(get_db)):
    existing = db.execute(select(Job).where(Job.canonical_key == payload.canonical_key)).scalars().first()
    if existing:
        return existing

    job = Job(
        canonical_key=payload.canonical_key,
        company=payload.company,
        title=payload.title,
        location=payload.location,
        platform=payload.platform,
        source_url=payload.source_url,
        external_job_id=payload.external_job_id,
        status=payload.status,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.get("", response_model=list[JobResponse])
def list_jobs(
    status: str | None = Query(default=None),
    company: str | None = Query(default=None),
    platform: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    stmt = select(Job).order_by(Job.discovered_at.asc())
    if status:
        stmt = stmt.where(Job.status == status)
    if company:
        stmt = stmt.where(Job.company.ilike(f"%{company}%"))
    if platform:
        stmt = stmt.where(Job.platform == platform)

    return db.execute(stmt).scalars().all()


# ── Literal-path routes (must be declared before /{job_id}) ──────────────────

@router.get("/search")
def search_jobs(q: str = Query(...)) -> dict[str, Any]:
    """Search remote jobs via Remotive's free public API (no key required)."""
    try:
        r = httpx.get(
            "https://remotive.com/api/remote-jobs",
            params={"search": q, "limit": 100},
            timeout=12,
        )
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail="Job search API unavailable")
        jobs = r.json().get("jobs", [])
        return {
            "jobs": [
                {
                    "id": str(j["id"]),
                    "title": j.get("title", ""),
                    "company": j.get("company_name", ""),
                    "location": j.get("candidate_required_location") or "Remote",
                    "url": j.get("url", ""),
                    "published_at": j.get("publication_date", ""),
                    "tags": j.get("tags", []),
                }
                for j in jobs
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Job search failed: {e}")


@router.get("/prefill")
def prefill_job(url: str = Query(...)) -> dict[str, Any]:
    """Fetch a job URL and return extracted company, title, platform metadata."""
    is_greenhouse = bool(re.search(r"greenhouse\.io", url, re.IGNORECASE))

    if is_greenhouse:
        m = re.search(r"greenhouse\.io/([^/?#]+)/jobs/(\d+)", url)
        if m:
            slug, job_id_str = m.group(1), m.group(2)
            company = slug.replace("-", " ").title()
            try:
                api_url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id_str}"
                r = httpx.get(api_url, timeout=6)
                if r.status_code == 200:
                    data = r.json()
                    return {
                        "company": company,
                        "title": data.get("title"),
                        "platform": "greenhouse",
                        "location": (data.get("location") or {}).get("name"),
                    }
            except Exception:
                pass
            return {"company": company, "title": None, "platform": "greenhouse", "location": None}

        m2 = re.search(r"greenhouse\.io/([^/?#]+)", url)
        if m2:
            slug = m2.group(1)
            return {
                "company": slug.replace("-", " ").title(),
                "title": None,
                "platform": "greenhouse",
                "location": None,
            }
        return {"company": None, "title": None, "platform": "greenhouse", "location": None}

    # Generic HTML fetch — try OG tags then <title>
    try:
        r = httpx.get(url, follow_redirects=True, timeout=6, headers={"User-Agent": "Mozilla/5.0"})
        text = r.text
        m = re.search(r'<meta\s[^>]*property=["\']og:title["\'][^>]*content=["\'](.*?)["\']', text, re.I)
        if not m:
            m = re.search(r'<meta\s[^>]*content=["\'](.*?)["\'][^>]*property=["\']og:title["\']', text, re.I)
        if m:
            return {"title": m.group(1).strip(), "company": None, "platform": None, "location": None}
        m = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
        if m:
            return {"title": m.group(1).strip(), "company": None, "platform": None, "location": None}
    except Exception:
        pass

    return {"company": None, "title": None, "platform": None, "location": None}


@router.get("/greenhouse")
def browse_greenhouse(
    slug: str = Query(...),
    q: str | None = Query(default=None),
) -> dict[str, Any]:
    """Proxy Greenhouse board API — returns jobs sorted newest first."""
    try:
        api_url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
        r = httpx.get(api_url, timeout=10)
        if r.status_code == 404:
            raise HTTPException(status_code=404, detail=f"No Greenhouse board found for slug '{slug}'")
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail="Greenhouse API error")
        data = r.json()
        jobs = data.get("jobs", [])

        if q:
            q_lower = q.lower()
            jobs = [
                j for j in jobs
                if q_lower in j.get("title", "").lower()
                or q_lower in ((j.get("location") or {}).get("name", "")).lower()
            ]

        jobs.sort(key=lambda j: j.get("updated_at", ""), reverse=True)

        company = data.get("name") or slug.replace("-", " ").title()
        return {
            "company": company,
            "jobs": [
                {
                    "id": str(j["id"]),
                    "title": j.get("title", ""),
                    "location": (j.get("location") or {}).get("name", ""),
                    "updated_at": j.get("updated_at", ""),
                    "url": j.get("absolute_url", ""),
                }
                for j in jobs
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch Greenhouse jobs: {e}")


@router.post("/claim", response_model=JobClaimResponse)
def claim_job(payload: JobClaimRequest, db: Session = Depends(get_db)):
    job = claim_next_job(db, payload.worker_id, settings.lease_minutes)
    return {"job": job}


# ── Parameterized /{job_id} routes ────────────────────────────────────────────

@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}/signal")
def get_signal(job_id: str):
    return {"signal": _submit_signals.pop(job_id, None)}


@router.post("/{job_id}/signal")
def send_signal(job_id: str, action: str = Body(..., embed=True)):
    if action not in {"submit", "skip"}:
        raise HTTPException(status_code=400, detail="action must be 'submit' or 'skip'")
    _submit_signals[job_id] = action
    return {"ok": True}


@router.delete("/{job_id}")
def delete_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    db.delete(job)
    db.commit()
    return {"ok": True}


@router.post("/{job_id}/requeue")
def requeue_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    requeue_from = {JobStatus.SKIPPED.value, JobStatus.FAILED.value, JobStatus.SUBMITTED.value}
    if job.status not in requeue_from:
        raise HTTPException(status_code=400, detail=f"Cannot requeue job with status '{job.status}'")
    job.status = JobStatus.QUEUED.value
    job.claimed_by_worker_id = None
    job.lease_expires_at = None
    job.applied_at = None
    job.updated_at = datetime.now(timezone.utc)
    db.commit()
    # Clear any stale signal (skip/submit) from the previous run so the worker
    # doesn't immediately auto-skip or auto-submit when it picks this job up again.
    _submit_signals.pop(job_id, None)
    return {"ok": True}


@router.post("/{job_id}/status")
def update_job_status(job_id: str, payload: JobStatusUpdateRequest, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    worker = db.get(Worker, payload.worker_id)
    if worker is None:
        raise HTTPException(status_code=404, detail="Worker not found")

    if job.status != payload.from_status:
        raise HTTPException(
            status_code=409,
            detail=f"Job status mismatch. Expected {payload.from_status}, got {job.status}",
        )

    allowed = ALLOWED_TRANSITIONS.get(job.status, set())
    if payload.to_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Illegal transition: {job.status} -> {payload.to_status}",
        )

    if job.claimed_by_worker_id and job.claimed_by_worker_id != worker.id:
        raise HTTPException(status_code=403, detail="Worker does not own this job")

    job.status = payload.to_status
    job.updated_at = datetime.now(timezone.utc)

    if payload.to_status == JobStatus.SUBMITTED.value:
        job.applied_at = datetime.now(timezone.utc)

    if payload.to_status in {JobStatus.SUBMITTED.value, JobStatus.FAILED.value, JobStatus.SKIPPED.value}:
        worker.current_job_id = None
        worker.current_stage = None
        worker.status = WorkerStatus.IDLE.value

    db.commit()
    return {"ok": True}


@router.post("/{job_id}/evidence")
def post_evidence(job_id: str, payload: dict[str, Any], db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    _evidence[job_id] = {
        "clicked": payload.get("clicked", False),
        "success": payload.get("success", False),
        "url": payload.get("url", ""),
        "message": payload.get("message", ""),
        "screenshot_b64": payload.get("screenshot_b64"),
    }
    return {"ok": True}


@router.get("/{job_id}/evidence")
def get_evidence(job_id: str):
    ev = _evidence.get(job_id)
    if ev is None:
        raise HTTPException(status_code=404, detail="No evidence for this job")
    return {k: v for k, v in ev.items() if k != "screenshot_b64"}


@router.get("/{job_id}/screenshot")
def get_screenshot(job_id: str):
    ev = _evidence.get(job_id)
    if ev is None or not ev.get("screenshot_b64"):
        raise HTTPException(status_code=404, detail="No screenshot for this job")
    img_bytes = base64.b64decode(ev["screenshot_b64"])
    return Response(content=img_bytes, media_type="image/png")
