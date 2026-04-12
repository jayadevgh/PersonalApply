from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query
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


# In-memory submit signals: {job_id: "submit" | "skip"}
_submit_signals: dict[str, str] = {}


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


@router.post("/claim", response_model=JobClaimResponse)
def claim_job(payload: JobClaimRequest, db: Session = Depends(get_db)):
    job = claim_next_job(db, payload.worker_id, settings.lease_minutes)
    return {"job": job}


@router.post("/{job_id}/status")
def update_job_status(job_id: str, payload: JobStatusUpdateRequest, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    worker = db.get(Worker, payload.worker_id)
    if worker is None:
        raise HTTPException(status_code=404, detail="Worker not found")

    if job.status != payload.from_status:
        raise HTTPException(status_code=409, detail=f"Job status mismatch. Expected {payload.from_status}, got {job.status}")

    allowed = ALLOWED_TRANSITIONS.get(job.status, set())
    if payload.to_status not in allowed:
        raise HTTPException(status_code=400, detail=f"Illegal transition: {job.status} -> {payload.to_status}")

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
