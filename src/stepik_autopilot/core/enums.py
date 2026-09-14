from enum import StrEnum


class RunMode(StrEnum):
    INSPECT = "inspect"
    AUTOPILOT = "autopilot"
    REVIEW = "review"
    TUTOR = "tutor"


class Strategy(StrEnum):
    BALANCED = "balanced"
    THROUGHPUT = "throughput"
    ECONOMY = "economy"


class Selection(StrEnum):
    REMAINING = "remaining"
    FAILED = "failed"
    EXPLICIT = "explicit"


class Target(StrEnum):
    TASKS_COMPLETE = "tasks_complete"
    ALL_AVAILABLE_TASKS = "all_available_tasks"
    SCORE = "score"


class Grading(StrEnum):
    DEFERRED = "deferred"
    IMMEDIATE = "immediate"


class RunState(StrEnum):
    DISPATCHING = "dispatching"
    ROUND_DISPATCHED = "round_dispatched"
    COLLECTING = "collecting"
    REPAIRING = "repairing"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    FINISHED = "finished"


class ItemState(StrEnum):
    READY = "ready"
    LEASED = "leased"
    DRAFT = "draft"
    QUEUED = "queued"
    SENDING = "sending"
    ACCEPTED = "accepted"
    CORRECT = "correct"
    WRONG = "wrong"
    EVALUATION = "evaluation"
    REVIEW_REQUIRED = "review_required"
    OUTCOME_UNKNOWN = "outcome_unknown"
    UNSUPPORTED = "unsupported"
    EXCLUDED_THEORY = "excluded_theory"


class OperationState(StrEnum):
    PREPARED = "prepared"
    SENDING = "sending"
    ACCEPTED = "accepted"
    OUTCOME_UNKNOWN = "outcome_unknown"
    RECONCILED = "reconciled"


class DeliveryState(StrEnum):
    QUEUED = "queued"
    ACCEPTED = "accepted"
    ERROR = "submit_error"
    OUTCOME_UNKNOWN = "outcome_unknown"
