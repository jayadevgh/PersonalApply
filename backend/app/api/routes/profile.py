"""
Profile API — stores user profile in backend/data/profile.json.
The worker reads from GET /profile instead of .env so the UI can manage it.
"""

import json
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
PROFILE_PATH = DATA_DIR / "profile.json"
UPLOADS_DIR = DATA_DIR / "uploads"

DEFAULTS: dict = {
    "first_name": "",
    "last_name": "",
    "email": "",
    "phone": "",
    "linkedin": "",
    "github": "",
    "website": "",
    "location": "",
    "city": "",
    "country": "United States",
    "state": "",
    "zip": "",
    "job_title": "",
    "relocation": "yes",
    "start_date": "",
    "school": "",
    "degree": "",
    "discipline": "",
    "gpa": "",
    "work_auth": "yes",
    "sponsorship": "no",
    "gender": "",
    "race": "",
    "veteran": "",
    "disability": "",
    "pronouns": "",
    "resume_path": "",
    # Behaviour settings
    "auto_submit": False,
}


def _read() -> dict:
    if PROFILE_PATH.exists():
        try:
            return {**DEFAULTS, **json.loads(PROFILE_PATH.read_text())}
        except Exception:
            pass
    return dict(DEFAULTS)


def _write(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(json.dumps(data, indent=2))


class ProfileUpdate(BaseModel):
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    github: str = ""
    website: str = ""
    location: str = ""
    city: str = ""
    country: str = "United States"
    state: str = ""
    zip: str = ""
    job_title: str = ""
    relocation: str = "yes"
    start_date: str = ""
    school: str = ""
    degree: str = ""
    discipline: str = ""
    gpa: str = ""
    work_auth: str = "yes"
    sponsorship: str = "no"
    gender: str = ""
    race: str = ""
    veteran: str = ""
    disability: str = ""
    pronouns: str = ""
    auto_submit: bool = False


router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("")
def get_profile() -> dict:
    return _read()


@router.put("")
def update_profile(payload: ProfileUpdate) -> dict:
    current = _read()
    updated = {**current, **payload.model_dump()}
    _write(updated)
    return updated


@router.post("/resume")
async def upload_resume(file: UploadFile = File(...)) -> dict:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOADS_DIR / file.filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    profile = _read()
    profile["resume_path"] = str(dest)
    _write(profile)
    return {"resume_path": str(dest), "filename": file.filename}
