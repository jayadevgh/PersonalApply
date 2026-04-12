"""
Field classification helpers for form autofill.
"""

import hashlib
import re

# ── Greenhouse URL detection ──────────────────────────────────────────────────

GREENHOUSE_HOST_PATTERN = re.compile(r"^job-boards(\..+)?\.greenhouse\.io$")


def is_greenhouse_url(url: str) -> bool:
    try:
        from urllib.parse import urlparse
        host = urlparse(url).hostname or ""
        return bool(GREENHOUSE_HOST_PATTERN.match(host))
    except Exception:
        return False


# ── Label normalization ───────────────────────────────────────────────────────

def normalize_label(text: str) -> str:
    return " ".join(
        "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in (text or "")).split()
    )


# ── Known profile field map ───────────────────────────────────────────────────

KNOWN_FIELD_LABELS: dict[str, str] = {
    "first name": "first_name",
    "preferred first name": "first_name",
    "last name": "last_name",
    "surname": "last_name",
    "full name": "full_name",
    "name": "full_name",
    "email": "email",
    "email address": "email",
    "phone": "phone",
    "phone number": "phone",
    "mobile": "phone",
    "mobile number": "phone",
    "linkedin profile url": "linkedin",
    "linkedin profile": "linkedin",
    "linkedin url": "linkedin",
    "linkedin": "linkedin",
    "github profile url": "github",
    "github profile": "github",
    "github url": "github",
    "github": "github",
    "portfolio personal website url": "website",
    "portfolio website": "website",
    "personal website": "website",
    "website": "website",
    "location city": "city",
    "city": "city",
    "location": "location",
    "current location": "location",
    "desired location": "location",
    "country": "country",
    "state": "state",
    "province": "state",
    "zip": "zip",
    "zip code": "zip",
    "postal code": "zip",
    "school": "school",
    "university": "school",
    "college": "school",
    "degree": "degree",
    "highest degree": "degree",
    "discipline": "discipline",
    "field of study": "discipline",
    "major": "discipline",
    "gpa": "gpa",
    "current or most recent job title level": "job_title",
    "current job title": "job_title",
    "job title": "job_title",
    "most recent job title": "job_title",
    "open for relocation": "relocation",
    "willing to relocate": "relocation",
    "preferred start date": "start_date",
    "available start date": "start_date",
    "start date": "start_date",
}


def profile_key_for_label(label: str) -> str | None:
    return KNOWN_FIELD_LABELS.get(normalize_label(label))


def is_known_field(label: str) -> bool:
    return profile_key_for_label(label) is not None


# ── Answer matching for native selects ───────────────────────────────────────

def match_answer_to_option(saved_answer: str, options: list[str]) -> str | None:
    """Find the best match for saved_answer in a list of option strings.
    Strategies: exact → containment → first token containment.
    """
    if not saved_answer or not options:
        return None
    answer_lower = saved_answer.lower().strip()

    for opt in options:
        if opt.lower().strip() == answer_lower:
            return opt

    for opt in options:
        opt_lower = opt.lower().strip()
        if opt_lower in answer_lower or answer_lower in opt_lower:
            return opt

    return None


# ── Options fingerprint ───────────────────────────────────────────────────────

def fingerprint_options(options: list[str]) -> str | None:
    if not options:
        return None
    normalized = sorted(normalize_label(o) for o in options)
    return hashlib.md5("|".join(normalized).encode()).hexdigest()[:16]


# ── Unknown question classification ──────────────────────────────────────────

BLOCKABLE_FIELD_TYPES = frozenset({
    "textarea", "text", "input", "select", "radio", "checkbox", "react_select"
})


def is_unknown_question(label: str, field_type: str) -> bool:
    if field_type not in BLOCKABLE_FIELD_TYPES:
        return False
    if is_known_field(label):
        return False
    return True


# ── Consent checkbox detection ────────────────────────────────────────────────

CONSENT_PATTERNS = [
    re.compile(r"\bby (checking|clicking|selecting) this\b", re.I),
    re.compile(r"\bi agree\b", re.I),
    re.compile(r"\bi certify\b", re.I),
    re.compile(r"\bi confirm\b", re.I),
    re.compile(r"\bi acknowledge\b", re.I),
    re.compile(r"\bterms (and|&) conditions\b", re.I),
    re.compile(r"\bprivacy policy\b", re.I),
]


def is_consent_checkbox(label: str, field_type: str) -> bool:
    if field_type != "checkbox":
        return False
    for pattern in CONSENT_PATTERNS:
        if pattern.search(label):
            return True
    return False
