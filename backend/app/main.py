import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response

from app.api.routes.answers import router as answers_router
from app.api.routes.health import router as health_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.profile import router as profile_router
from app.api.routes.questions import router as questions_router
from app.api.routes.workers import router as workers_router
from app.db.base import Base
from app.db.session import engine

# Import models so metadata is populated
from app.models import answer_template, application, job, question, question_answer_event, worker, worker_log  # noqa: F401

app = FastAPI(title="PersonalApply Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

app.include_router(health_router)
app.include_router(workers_router)
app.include_router(jobs_router)
app.include_router(questions_router)
app.include_router(answers_router)
app.include_router(profile_router)


@app.get("/ui/blocked", response_class=HTMLResponse)
def blocked_questions_ui():
    html_path = os.path.join(os.path.dirname(__file__), "ui", "blocked.html")
    with open(html_path) as f:
        content = f.read()
    return Response(content=content, media_type="text/html", headers={
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache",
    })


@app.get("/ui/templates", response_class=HTMLResponse)
def templates_ui():
    html_path = os.path.join(os.path.dirname(__file__), "ui", "templates.html")
    with open(html_path) as f:
        content = f.read()
    return Response(content=content, media_type="text/html", headers={
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache",
    })
