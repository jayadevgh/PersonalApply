from enum import Enum


class JobStatus(str, Enum):
    DISCOVERED = "discovered"
    QUEUED = "queued"
    CLAIMED = "claimed"
    APPLYING = "applying"
    BLOCKED_WAITING_FOR_USER = "blocked_waiting_for_user"
    REVIEW = "review"
    SUBMITTED = "submitted"
    FAILED = "failed"
    SKIPPED = "skipped"
    DUPLICATE = "duplicate"


class WorkerStatus(str, Enum):
    IDLE = "idle"
    CLAIMING_JOB = "claiming_job"
    OPENING_APPLICATION = "opening_application"
    AUTOFILLING = "autofilling"
    WAITING_FOR_USER = "waiting_for_user"
    SUBMITTING = "submitting"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    DEAD = "dead"


class ApplicationStatus(str, Enum):
    STARTED = "started"
    BLOCKED = "blocked"
    SUBMITTED = "submitted"
    FAILED = "failed"
    SKIPPED = "skipped"
    DUPLICATE = "duplicate"


class QuestionStatus(str, Enum):
    NEW = "new"
    AWAITING_USER = "awaiting_user"
    ANSWERED = "answered"
    SKIPPED = "skipped"
    RESOLVED = "resolved"
