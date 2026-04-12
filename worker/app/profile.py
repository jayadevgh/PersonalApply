"""
UserProfile — the source of truth for known-field autofill values.

For MVP, loaded from environment variables.
Later: loaded from backend API or local config file.

Profile keys must match the values in field_matching.KNOWN_FIELD_LABELS.
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class UserProfile:
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
    # EEO / compliance — used for deterministic dropdown matching
    work_auth: str = "yes"    # "yes" or "no"
    sponsorship: str = "no"   # "yes" or "no"
    gender: str = ""
    race: str = ""
    veteran: str = ""
    disability: str = ""
    pronouns: str = ""
    resume_path: str = ""  # local path to resume file for upload

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def get(self, key: str) -> str:
        """Return profile value by key, or empty string if missing."""
        if key == "full_name":
            return self.full_name
        return getattr(self, key, "") or ""

    def to_dict(self) -> dict:
        return {
            "first_name": self.first_name,
            "last_name": self.last_name,
            "full_name": self.full_name,
            "email": self.email,
            "phone": self.phone,
            "linkedin": self.linkedin,
            "github": self.github,
            "website": self.website,
            "location": self.location,
            "city": self.city,
            "country": self.country,
            "state": self.state,
            "zip": self.zip,
            "job_title": self.job_title,
            "relocation": self.relocation,
            "start_date": self.start_date,
            "school": self.school,
            "degree": self.degree,
            "discipline": self.discipline,
            "gpa": self.gpa,
            "work_auth": self.work_auth,
            "sponsorship": self.sponsorship,
            "gender": self.gender,
            "race": self.race,
            "veteran": self.veteran,
            "disability": self.disability,
            "pronouns": self.pronouns,
            "resume_path": self.resume_path,
        }

    @classmethod
    def from_env(cls) -> "UserProfile":
        return cls(
            first_name=os.getenv("PROFILE_FIRST_NAME", ""),
            last_name=os.getenv("PROFILE_LAST_NAME", ""),
            email=os.getenv("PROFILE_EMAIL", ""),
            phone=os.getenv("PROFILE_PHONE", ""),
            linkedin=os.getenv("PROFILE_LINKEDIN", ""),
            github=os.getenv("PROFILE_GITHUB", ""),
            website=os.getenv("PROFILE_WEBSITE", ""),
            location=os.getenv("PROFILE_LOCATION", ""),
            city=os.getenv("PROFILE_CITY", ""),
            country=os.getenv("PROFILE_COUNTRY", "United States"),
            state=os.getenv("PROFILE_STATE", ""),
            zip=os.getenv("PROFILE_ZIP", ""),
            job_title=os.getenv("PROFILE_JOB_TITLE", ""),
            relocation=os.getenv("PROFILE_RELOCATION", "yes"),
            start_date=os.getenv("PROFILE_START_DATE", ""),
            school=os.getenv("PROFILE_SCHOOL", ""),
            degree=os.getenv("PROFILE_DEGREE", ""),
            discipline=os.getenv("PROFILE_DISCIPLINE", ""),
            gpa=os.getenv("PROFILE_GPA", ""),
            work_auth=os.getenv("PROFILE_WORK_AUTH", "yes"),
            sponsorship=os.getenv("PROFILE_SPONSORSHIP", "no"),
            gender=os.getenv("PROFILE_GENDER", ""),
            race=os.getenv("PROFILE_RACE", ""),
            veteran=os.getenv("PROFILE_VETERAN", ""),
            disability=os.getenv("PROFILE_DISABILITY", ""),
            pronouns=os.getenv("PROFILE_PRONOUNS", ""),
            resume_path=os.getenv("PROFILE_RESUME_PATH", ""),
        )


def get_profile_dict() -> dict:
    """Load profile from env and return as a plain dict."""
    return UserProfile.from_env().to_dict()
