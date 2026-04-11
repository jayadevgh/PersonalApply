from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.enums import JobStatus
from app.models.job import Job
from app.models.worker import Worker
from app.schemas.worker import (
    WorkerHeartbeatRequest,
    WorkerListItem,
    WorkerRegisterRequest,
    WorkerResponse,
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/workers", tags=["workers"])


@router.post("/register", response_model=WorkerResponse)
def register_worker(payload: WorkerRegisterRequest, db: Session = Depends(get_db)):
    existing = db.execute(select(Worker).where(Worker.name == payload.name)).scalars().first()
    if existing:
        return existing

    worker = Worker(name=payload.name, status="idle")
    db.add(worker)
    db.commit()
    db.refresh(worker)
    return worker


@router.get("", response_model=list[WorkerListItem])
def list_workers(db: Session = Depends(get_db)):
    workers = db.execute(select(Worker).order_by(Worker.created_at.asc())).scalars().all()
    return workers


@router.post("/{worker_id}/heartbeat")
def heartbeat(worker_id: str, payload: WorkerHeartbeatRequest, db: Session = Depends(get_db)):
    worker = db.get(Worker, worker_id)
    if worker is None:
        raise HTTPException(status_code=404, detail="Worker not found")

    worker.status = payload.status
    worker.current_job_id = payload.current_job_id
    worker.current_stage = payload.current_stage
    worker.last_heartbeat_at = datetime.now(timezone.utc)

    if payload.current_job_id:
        job = db.get(Job, payload.current_job_id)
        if (
            job
            and job.claimed_by_worker_id == worker.id
            and job.status in {JobStatus.CLAIMED.value, JobStatus.APPLYING.value}
        ):
            job.lease_expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.lease_minutes)

    db.commit()
    return {"ok": True, "server_time": datetime.now(timezone.utc).isoformat()}
