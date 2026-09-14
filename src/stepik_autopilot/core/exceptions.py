class StepikAutopilotError(Exception):
    code = "stepik_autopilot.error"


class NotFoundError(StepikAutopilotError):
    code = "not_found"


class ConflictError(StepikAutopilotError):
    code = "conflict"


class ValidationError(StepikAutopilotError):
    code = "validation_error"


class UnsupportedTaskError(StepikAutopilotError):
    code = "unsupported_task"


class RunStateError(StepikAutopilotError):
    code = "invalid_run_state"


class ExternalServiceError(StepikAutopilotError):
    code = "stepik_unavailable"
