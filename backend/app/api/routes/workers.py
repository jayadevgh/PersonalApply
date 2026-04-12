import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

# PIDs of worker processes spawned by this backend instance
_worker_procs: dict[str, subprocess.Popen] = {}

# Fill logs per worker: { worker_id: [{"label", "value", "source"}, ...] }
_fill_logs: dict[str, list[dict]] = {}

# Field overrides queued by UI, consumed by worker during review loop
_field_overrides: dict[str, list[dict]] = {}

WORKER_DIR = Path(os.environ.get(
    "WORKER_DIR",
    str(Path(__file__).parent.parent.parent.parent.parent / "worker")
))

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


@router.post("/spawn")
def spawn_worker(name: str = Body(..., embed=True), db: Session = Depends(get_db)):
    python = WORKER_DIR / ".venv" / "bin" / "python"
    if not python.exists():
        raise HTTPException(status_code=500, detail=f"Worker python not found at {python}")
    env = {**os.environ, "WORKER_NAME": name}
    proc = subprocess.Popen(
        [str(python), "-m", "app.main"],
        cwd=str(WORKER_DIR),
        env=env,
    )
    # Optimistically register (worker will re-register on boot anyway)
    existing = db.execute(select(Worker).where(Worker.name == name)).scalars().first()
    if existing:
        worker_id = str(existing.id)
    else:
        w = Worker(name=name, status="idle")
        db.add(w)
        db.commit()
        db.refresh(w)
        worker_id = str(w.id)
    _worker_procs[worker_id] = proc
    return {"worker_id": worker_id, "pid": proc.pid, "name": name}


@router.delete("/{worker_id}")
def stop_worker(worker_id: str, db: Session = Depends(get_db)):
    proc = _worker_procs.pop(worker_id, None)
    if proc:
        proc.terminate()
    worker = db.get(Worker, worker_id)
    if worker is None:
        raise HTTPException(status_code=404, detail="Worker not found")
    worker.status = "dead"
    worker.current_job_id = None
    worker.current_stage = None
    db.commit()
    return {"ok": True}


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


@router.post("/{worker_id}/fill-log")
def post_fill_log(worker_id: str, events: list[dict[str, Any]] = Body(...)):
    """Worker posts the list of fills it made so the UI can display them during review."""
    _fill_logs[worker_id] = events
    return {"ok": True}


@router.get("/{worker_id}/fill-log")
def get_fill_log(worker_id: str):
    return _fill_logs.get(worker_id, [])


@router.post("/{worker_id}/field-override")
def post_field_override(worker_id: str, override: dict[str, Any] = Body(...)):
    """UI queues a field re-fill to be applied by the worker during its review loop."""
    _field_overrides.setdefault(worker_id, []).append(override)
    return {"ok": True}


@router.get("/{worker_id}/field-overrides")
def get_field_overrides(worker_id: str):
    """Worker polls this, consuming and clearing the queue."""
    overrides = _field_overrides.pop(worker_id, [])
    return overrides
