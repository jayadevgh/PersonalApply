from fastapi import FastAPI

from app.api.routes.answers import router as answers_router
from app.api.routes.health import router as health_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.questions import router as questions_router
from app.api.routes.workers import router as workers_router
from app.db.base import Base
from app.db.session import engine

# Import models so metadata is populated
from app.models import answer_template, application, job, question, question_answer_event, worker, worker_log  # noqa: F401

app = FastAPI(title="PersonalApply Backend")

Base.metadata.create_all(bind=engine)

app.include_router(health_router)
app.include_router(workers_router)
app.include_router(jobs_router)
app.include_router(questions_router)
app.include_router(answers_router)
