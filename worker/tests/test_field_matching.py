"""
Smoke tests for field_matching.py and GreenhouseAdapter.classify_fields().

Run from worker/ with:
    PYTHONPATH=. python tests/test_field_matching.py
"""

import sys
sys.path.insert(0, ".")

from app.adapters.field_matching import (
    normalize_label,
    is_known_field,
    is_eeo_field,
    detect_topic,
    is_unknown_question,
    find_decline_option,
    match_answer_to_option,
    is_greenhouse_url,
    profile_key_for_label,
)
from app.adapters.greenhouse import GreenhouseAdapter
from app.profile import UserProfile

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"

failures = 0


def check(label: str, actual, expected):
    global failures
    ok = actual == expected
    status = PASS if ok else FAIL
    print(f"  {status}  {label}")
    if not ok:
        print(f"         expected: {expected!r}")
        print(f"         got:      {actual!r}")
        failures += 1


print("\n── normalize_label ─────────────────────────────────────────────")
check("strips punctuation",       normalize_label("First Name*"),    "first name")
check("collapses whitespace",     normalize_label("Email  Address"), "email address")
check("lowercases",               normalize_label("LinkedIn URL"),   "linkedin url")

print("\n── is_known_field ──────────────────────────────────────────────")
check("first name",               is_known_field("First Name"),      True)
check("email address",            is_known_field("Email Address"),   True)
check("linkedin profile url",     is_known_field("LinkedIn Profile URL"), True)
check("open-ended question",      is_known_field("Why do you want to work here?"), False)

print("\n── profile_key_for_label ───────────────────────────────────────")
check("first name → first_name",  profile_key_for_label("First Name"),  "first_name")
check("email → email",            profile_key_for_label("Email"),        "email")
check("linkedin profile url",     profile_key_for_label("LinkedIn Profile URL"), "linkedin")
check("unknown → None",           profile_key_for_label("Tell us about yourself"), None)

print("\n── detect_topic ────────────────────────────────────────────────")
check("gender identity before gender",  detect_topic("What is your gender identity?"), "gender_identity")
check("plain gender",                   detect_topic("Gender"),                         "gender")
check("race/ethnicity",                 detect_topic("Race / Ethnicity"),               "race_ethnicity")
check("work authorization",             detect_topic("Are you authorized to work in the US?"), "work_auth")
check("visa sponsorship",               detect_topic("Will you require visa sponsorship?"),    "sponsorship")
check("veteran status",                 detect_topic("Are you a veteran?"),             "veteran")
check("disability",                     detect_topic("Do you have a disability?"),      "disability")
check("pronouns",                       detect_topic("What are your pronouns?"),        "pronouns")
check("open-ended → None",              detect_topic("Why do you want to work here?"),  None)

print("\n── is_eeo_field ────────────────────────────────────────────────")
check("gender is EEO",            is_eeo_field("Gender"),            True)
check("work auth is EEO",         is_eeo_field("Work Authorization"), True)
check("open-ended is not EEO",    is_eeo_field("Describe yourself"), False)

print("\n── is_unknown_question ─────────────────────────────────────────")
check("open textarea → block",        is_unknown_question("Why do you want to work here?", "textarea"), True)
check("known field → don't block",    is_unknown_question("First Name", "text"),                        False)
check("EEO field → don't block",      is_unknown_question("Gender", "textarea"),                        False)
check("non-text field → don't block", is_unknown_question("Some question", "select"),                   False)

print("\n── find_decline_option ─────────────────────────────────────────")
opts_with_decline = ["Male", "Female", "Non-binary", "Prefer not to say"]
opts_without      = ["Male", "Female", "Non-binary"]
check("finds decline option",         find_decline_option(opts_with_decline), "Prefer not to say")
check("returns None when absent",     find_decline_option(opts_without),      None)

print("\n── match_answer_to_option ──────────────────────────────────────")
gender_opts = ["Man", "Woman", "Non-binary", "Prefer not to say"]
check("exact match",           match_answer_to_option("Non-binary", gender_opts, "gender"),   "Non-binary")
check("synonym male→Man",      match_answer_to_option("male", gender_opts, "gender"),         "Man")
check("synonym female→Woman",  match_answer_to_option("female", gender_opts, "gender"),       "Woman")
work_opts = ["Yes", "No", "Other"]
check("yes→Yes",               match_answer_to_option("yes", work_opts, "work_auth"),         "Yes")
check("no match → None",       match_answer_to_option("zzz", gender_opts, "gender"),          None)

print("\n── is_greenhouse_url ───────────────────────────────────────────")
check("valid greenhouse URL",     is_greenhouse_url("https://job-boards.acme.greenhouse.io/jobs/123"), True)
check("non-greenhouse URL",       is_greenhouse_url("https://jobs.lever.co/acme/123"),                 False)
check("bare greenhouse domain",   is_greenhouse_url("https://greenhouse.io/jobs/123"),                 False)

print("\n── GreenhouseAdapter.classify_fields ───────────────────────────")
profile = UserProfile(
    first_name="Jay", last_name="Smith", email="jay@example.com",
    phone="555-1234", linkedin="https://linkedin.com/in/jay",
    work_auth="yes", gender="", race="",
)
adapter = GreenhouseAdapter(profile=profile)

fields = [
    {"label": "First Name",    "field_type": "text"},
    {"label": "Last Name",     "field_type": "text"},
    {"label": "Email",         "field_type": "text"},
    {"label": "Phone",         "field_type": "text"},
    {"label": "LinkedIn Profile URL", "field_type": "text"},
    {"label": "Gender",        "field_type": "select",
     "options": ["Male", "Female", "Non-binary", "Prefer not to say"]},
    {"label": "Race / Ethnicity", "field_type": "select",
     "options": ["Asian", "Black or African American", "White", "Decline to self-identify"]},
    {"label": "Are you authorized to work in the US?", "field_type": "select",
     "options": ["Yes", "No"]},
    {"label": "Why do you want to work here?",         "field_type": "textarea"},
    {"label": "Describe a challenging project.",        "field_type": "textarea"},
]

result = adapter.classify_fields(fields)

check("5 known fields filled",    len(result["fill"]),  5)
check("first_name value",         result["fill"][0]["value"], "Jay")
check("email value",              result["fill"][2]["value"], "jay@example.com")
check("2 EEO fields handled",     len(result["eeo"]),   3)  # gender + race + work_auth
check("gender → decline",         result["eeo"][0]["option"], "Prefer not to say")
check("race → decline",           result["eeo"][1]["option"], "Decline to self-identify")
check("work_auth → Yes",          result["eeo"][2]["option"], "Yes")
check("2 unknown questions",      len(result["block"]), 2)
check("first block label",        result["block"][0]["label"], "Why do you want to work here?")

# ── Summary ───────────────────────────────────────────────────────────────────
print()
if failures == 0:
    print(f"\033[32mAll checks passed.\033[0m\n")
else:
    print(f"\033[31m{failures} check(s) failed.\033[0m\n")
    sys.exit(1)
