from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class JobCreateRequest(BaseModel):
    canonical_key: str
    company: str
    title: str
    location: str | None = None
    platform: str
    source_url: str
    external_job_id: str | None = None
    status: str = "queued"


class JobStatusUpdateRequest(BaseModel):
    worker_id: UUID
    from_status: str
    to_status: str


class JobResponse(BaseModel):
    id: UUID
    canonical_key: str
    company: str
    title: str
    location: str | None
    platform: str
    source_url: str
    external_job_id: str | None
    status: str
    claimed_by_worker_id: UUID | None
    lease_expires_at: datetime | None

    model_config = {"from_attributes": True}


class JobClaimRequest(BaseModel):
    worker_id: UUID


class JobClaimResponse(BaseModel):
    job: JobResponse | None
