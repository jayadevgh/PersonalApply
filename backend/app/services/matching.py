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
