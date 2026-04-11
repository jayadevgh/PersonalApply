from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.answer_template import AnswerTemplate
from app.models.enums import JobStatus, QuestionStatus, WorkerStatus
from app.models.job import Job
from app.models.question import Question
from app.models.question_answer_event import QuestionAnswerEvent
from app.models.worker import Worker
from app.schemas.question import (
    BlockedQuestionResponse,
    QuestionAnswerRequest,
    QuestionCreateRequest,
    QuestionSkipRequest,
    SimilarAnswer,
)
from app.services.matching import get_similar_answers


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/questions", tags=["questions"])


@router.post("")
def create_question(payload: QuestionCreateRequest, db: Session = Depends(get_db)):
    job = db.get(Job, payload.job_id)
    worker = db.get(Worker, payload.worker_id)
    if not job or not worker:
        raise HTTPException(status_code=404, detail="Job or worker not found")

    question = Question(
        job_id=payload.job_id,
        worker_id=payload.worker_id,
        raw_text=payload.raw_text,
        normalized_text=payload.normalized_text,
        field_type=payload.field_type,
        field_label=payload.field_label,
        page_url=payload.page_url,
        dom_hint=payload.dom_hint,
        status=QuestionStatus.AWAITING_USER.value,
    )
    db.add(question)

    job.status = JobStatus.BLOCKED_WAITING_FOR_USER.value
    worker.status = WorkerStatus.WAITING_FOR_USER.value
    worker.current_stage = "blocked_on_question"

    db.commit()
    db.refresh(question)
    return {"question_id": str(question.id)}


@router.get("/blocked", response_model=list[BlockedQuestionResponse])
def get_blocked_questions(db: Session = Depends(get_db)):
    questions = (
        db.execute(
            select(Question, Job)
            .join(Job, Question.job_id == Job.id)
            .where(Question.status == QuestionStatus.AWAITING_USER.value)
            .order_by(Question.created_at.asc())
        )
        .all()
    )

    result = []
    for question, job in questions:
        similar = get_similar_answers(db, question.normalized_text, limit=5)
        result.append(
            BlockedQuestionResponse(
                id=question.id,
                job_id=job.id,
                company=job.company,
                title=job.title,
                raw_text=question.raw_text,
                status=question.status,
                created_at=question.created_at,
                similar_answers=[
                    SimilarAnswer(
                        id=t.id,
                        title=t.title,
                        category=t.category,
                        answer_text=t.answer_text,
                    )
                    for t in similar
                ],
            )
        )
    return result


@router.post("/{question_id}/answer")
def answer_question(question_id: str, payload: QuestionAnswerRequest, db: Session = Depends(get_db)):
    question = db.get(Question, question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")

    worker = db.get(Worker, payload.worker_id)
    job = db.get(Job, question.job_id)
    if worker is None or job is None:
        raise HTTPException(status_code=404, detail="Worker or job not found")

    template = None
    if payload.answer_template_id:
        template = db.get(AnswerTemplate, payload.answer_template_id)
        if template:
            template.times_used += 1

    created_template = None
    if payload.save_as_template:
        if not payload.template_title or not payload.template_category:
            raise HTTPException(status_code=400, detail="template_title and template_category required")
        created_template = AnswerTemplate(
            title=payload.template_title,
            category=payload.template_category,
            answer_text=payload.final_submitted_text,
            tags=payload.template_tags or [],
            approved=True,
        )
        db.add(created_template)
        db.flush()

    db.add(
        QuestionAnswerEvent(
            question_id=question.id,
            answer_template_id=(template.id if template else (created_template.id if created_template else None)),
            final_submitted_text=payload.final_submitted_text,
            edited_by_user=True,
            saved_for_reuse=payload.save_as_template,
        )
    )

    question.status = QuestionStatus.RESOLVED.value
    question.resolved_at = datetime.now(timezone.utc)

    job.status = JobStatus.APPLYING.value
    worker.status = WorkerStatus.AUTOFILLING.value
    worker.current_stage = "resuming_after_question"

    db.commit()

    return {"ok": True, "template_id": str(created_template.id) if created_template else None}


@router.post("/{question_id}/skip")
def skip_question(question_id: str, payload: QuestionSkipRequest, db: Session = Depends(get_db)):
    question = db.get(Question, question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")

    worker = db.get(Worker, payload.worker_id)
    job = db.get(Job, question.job_id)
    if worker is None or job is None:
        raise HTTPException(status_code=404, detail="Worker or job not found")

    question.status = QuestionStatus.SKIPPED.value
    question.resolved_at = datetime.now(timezone.utc)

    job.status = JobStatus.SKIPPED.value
    worker.status = WorkerStatus.IDLE.value
    worker.current_job_id = None
    worker.current_stage = None

    db.commit()
    return {"ok": True}
