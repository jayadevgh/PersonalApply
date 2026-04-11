import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class QuestionAnswerEvent(Base):
    __tablename__ = "question_answer_events"
    __table_args__ = (
        Index("idx_question_answer_events_question_id", "question_id"),
        Index("idx_question_answer_events_answer_template_id", "answer_template_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    answer_template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("answer_templates.id", ondelete="SET NULL"), nullable=True
    )
    final_submitted_text: Mapped[str] = mapped_column(Text, nullable=False)
    edited_by_user: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    saved_for_reuse: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
