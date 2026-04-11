from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class WorkerRegisterRequest(BaseModel):
    name: str


class WorkerResponse(BaseModel):
    id: UUID
    name: str
    status: str

    model_config = {"from_attributes": True}


class WorkerHeartbeatRequest(BaseModel):
    status: str
    current_job_id: UUID | None = None
    current_stage: str | None = None


class WorkerListItem(BaseModel):
    id: UUID
    name: str
    status: str
    current_job_id: UUID | None
    current_stage: str | None
    last_heartbeat_at: datetime
    last_error: str | None

    model_config = {"from_attributes": True}
