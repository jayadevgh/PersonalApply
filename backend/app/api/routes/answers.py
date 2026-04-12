from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.answer_template import AnswerTemplate
from app.schemas.answer import AnswerTemplateCreateRequest, AnswerTemplateResponse
from app.services.matching import get_exact_template


class AnswerTemplateUpdateRequest(BaseModel):
    answer_text: str


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


@router.get("/exact-match", response_model=AnswerTemplateResponse)
def exact_match_template(
    normalized_text: str = Query(),
    field_type: str | None = Query(default=None),
    options_fingerprint: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    template = get_exact_template(db, normalized_text, field_type, options_fingerprint)
    if template is None:
        raise HTTPException(status_code=404, detail="No exact match found")
    return template


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


@router.patch("/{template_id}", response_model=AnswerTemplateResponse)
def update_template(template_id: str, payload: AnswerTemplateUpdateRequest, db: Session = Depends(get_db)):
    template = db.get(AnswerTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    template.answer_text = payload.answer_text
    db.commit()
    db.refresh(template)
    return template


@router.delete("/{template_id}")
def delete_template(template_id: str, db: Session = Depends(get_db)):
    template = db.get(AnswerTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    db.delete(template)
    db.commit()
    return {"ok": True}
