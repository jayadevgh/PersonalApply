from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AnswerTemplateCreateRequest(BaseModel):
    title: str
    category: str
    answer_text: str
    tags: list[str] = Field(default_factory=list)


class AnswerTemplateResponse(BaseModel):
    id: UUID
    title: str
    normalized_question_text: str | None = None
    field_type: str | None = None
    category: str
    answer_text: str
    tags: list[str]
    approved: bool
    times_used: int
    created_at: datetime

    model_config = {"from_attributes": True}
