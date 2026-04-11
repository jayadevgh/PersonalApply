from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.enums import ApplicationStatus, JobStatus, WorkerStatus
from app.models.job import Job
from app.models.worker import Worker


def claim_next_job(db: Session, worker_id: UUID, lease_minutes: int) -> Job | None:
    now = datetime.now(timezone.utc)

    worker = db.get(Worker, worker_id)
    if worker is None:
        raise ValueError("Worker not found")

    candidate = (
        db.execute(
            select(Job)
            .where(Job.status == JobStatus.QUEUED.value)
            .where((Job.claimed_by_worker_id.is_(None)) | (Job.lease_expires_at < now))
            .order_by(Job.discovered_at.asc())
            .with_for_update(skip_locked=True)
        )
        .scalars()
        .first()
    )

    if candidate is None:
        worker.status = WorkerStatus.IDLE.value
        worker.current_job_id = None
        worker.current_stage = None
        db.commit()
        return None

    candidate.status = JobStatus.CLAIMED.value
    candidate.claimed_by_worker_id = worker_id
    candidate.lease_expires_at = now + timedelta(minutes=lease_minutes)

    worker.status = WorkerStatus.CLAIMING_JOB.value
    worker.current_job_id = candidate.id
    worker.current_stage = "claimed_job"

    max_attempt = (
        db.execute(
            select(Application.attempt_number)
            .where(Application.job_id == candidate.id)
            .order_by(Application.attempt_number.desc())
        )
        .scalars()
        .first()
    )
    next_attempt = (max_attempt or 0) + 1

    db.add(
        Application(
            job_id=candidate.id,
            worker_id=worker_id,
            attempt_number=next_attempt,
            status=ApplicationStatus.STARTED.value,
        )
    )
    db.commit()
    db.refresh(candidate)
    return candidate
