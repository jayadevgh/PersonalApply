from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class QuestionCreateRequest(BaseModel):
    job_id: UUID
    worker_id: UUID
    raw_text: str
    normalized_text: str
    field_type: str | None = None
    field_label: str | None = None
    page_url: str | None = None
    dom_hint: str | None = None
    options: list[str] | None = None
    options_fingerprint: str | None = None
    required: bool = False


class QuestionAnswerRequest(BaseModel):
    worker_id: UUID
    final_submitted_text: str = ""
    answer_template_id: UUID | None = None
    save_as_template: bool = False
    template_title: str | None = None
    template_category: str | None = None
    template_tags: list[str] | None = None


class QuestionSkipRequest(BaseModel):
    worker_id: UUID
    reason: str | None = None


class SimilarAnswer(BaseModel):
    id: UUID
    title: str
    category: str
    answer_text: str


class BlockedQuestionResponse(BaseModel):
    id: UUID
    job_id: UUID
    worker_id: UUID
    company: str
    title: str
    raw_text: str
    field_type: str | None
    options: list[str] | None
    required: bool
    status: str
    similar_answers: list[SimilarAnswer]
    created_at: datetime
