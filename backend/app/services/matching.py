import re

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.answer_template import AnswerTemplate


def normalize_question(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def get_exact_template(
    db: Session,
    normalized_text: str,
    field_type: str | None,
    options_fingerprint: str | None,
) -> AnswerTemplate | None:
    """
    Exact-match lookup using the full memory key:
      (normalized_question_text, field_type, options_fingerprint)

    All three parts must match. None values are treated as wildcards only on
    the template side — if the template was saved without a key part it won't
    match a question that has one, and vice versa.
    """
    stmt = (
        select(AnswerTemplate)
        .where(AnswerTemplate.approved.is_(True))
        .where(AnswerTemplate.normalized_question_text == normalized_text)
        .where(AnswerTemplate.field_type == field_type)
        .where(AnswerTemplate.options_fingerprint == options_fingerprint)
        .order_by(AnswerTemplate.times_used.desc())
        .limit(1)
    )
    return db.execute(stmt).scalars().first()


def get_similar_answers(db: Session, normalized_text: str, limit: int = 5) -> list[AnswerTemplate]:
    templates = db.execute(
        select(AnswerTemplate).where(AnswerTemplate.approved.is_(True))
    ).scalars().all()

    scored: list[tuple[int, AnswerTemplate]] = []
    for template in templates:
        score = max(
            fuzz.ratio(normalized_text, normalize_question(template.title)),
            fuzz.partial_ratio(normalized_text, normalize_question(template.answer_text[:200])),
        )
        if score >= 45:
            scored.append((score, template))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [template for _, template in scored[:limit]]
