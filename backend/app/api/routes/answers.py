from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.answer_template import AnswerTemplate
from app.schemas.answer import AnswerTemplateCreateRequest, AnswerTemplateResponse


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/answers/templates", tags=["answers"])


@router.get("", response_model=list[AnswerTemplateResponse])
def list_templates(
    category: str | None = Query(default=None),
    approved: bool | None = Query(default=None),
    q: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    stmt = select(AnswerTemplate).order_by(AnswerTemplate.created_at.desc())
    if category:
        stmt = stmt.where(AnswerTemplate.category == category)
    if approved is not None:
        stmt = stmt.where(AnswerTemplate.approved == approved)
    if q:
        stmt = stmt.where(AnswerTemplate.title.ilike(f"%{q}%"))

    return db.execute(stmt).scalars().all()


@router.post("", response_model=AnswerTemplateResponse)
def create_template(payload: AnswerTemplateCreateRequest, db: Session = Depends(get_db)):
    template = AnswerTemplate(
        title=payload.title,
        category=payload.category,
        answer_text=payload.answer_text,
        tags=payload.tags,
        approved=True,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template
