from dataclasses import dataclass

from stepik_autopilot.core.enums import (
    DeliveryState,
    Grading,
    ItemState,
    OperationState,
    RunMode,
    RunState,
    Selection,
    Strategy,
    Target,
)


@dataclass(frozen=True, slots=True)
class ChoiceDatasetDTO:
    options: tuple[str, ...]
    is_multiple_choice: bool


@dataclass(frozen=True, slots=True)
class ChoiceReplyDTO:
    choices: tuple[bool, ...]


@dataclass(frozen=True, slots=True)
class TextReplyDTO:
    text: str


@dataclass(frozen=True, slots=True)
class NumberReplyDTO:
    number: str


@dataclass(frozen=True, slots=True)
class BlanksReplyDTO:
    blanks: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MatchingReplyDTO:
    ordering: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class TableCellDTO:
    name: str
    answer: bool


@dataclass(frozen=True, slots=True)
class TableRowDTO:
    name_row: str
    columns: tuple[TableCellDTO, ...]


@dataclass(frozen=True, slots=True)
class TableReplyDTO:
    choices: tuple[TableRowDTO, ...]


@dataclass(frozen=True, slots=True)
class SqlReplyDTO:
    solve_sql: str


@dataclass(frozen=True, slots=True)
class CodeReplyDTO:
    language: str
    code: str


@dataclass(frozen=True, slots=True)
class CourseSummaryDTO:
    id: str
    title: str


@dataclass(frozen=True, slots=True)
class CoursePageDTO:
    courses: tuple[CourseSummaryDTO, ...]
    next_cursor: int | None


@dataclass(frozen=True, slots=True)
class CourseSectionDTO:
    number: int
    id: str
    title: str
    step_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TaskDTO:
    step_id: str
    assignment_id: str
    course_id: str
    kind: str
    question: str
    progress_id: str | None
    is_passed: bool | None
    failed: bool
    choice_options: tuple[str, ...] = ()
    is_multiple_choice: bool = False
    code_languages: tuple[str, ...] = ()
    code_templates: dict[str, str] | None = None


@dataclass(frozen=True, slots=True)
class CourseContentDTO:
    tasks: tuple[TaskDTO, ...]
    sections: tuple[CourseSectionDTO, ...]


@dataclass(frozen=True, slots=True)
class AttemptDTO:
    id: str
    step_id: str
    dataset: ChoiceDatasetDTO | None
    expires_at: str | None
    code_languages: tuple[str, ...] = ()
    quiz_data: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class RunDTO:
    id: str
    account_id: str
    course_id: str
    mode: RunMode
    strategy: Strategy
    selection: Selection
    target: Target
    grading: Grading
    state: RunState


@dataclass(frozen=True, slots=True)
class ItemDTO:
    id: str
    run_id: str
    step_id: str
    assignment_id: str
    kind: str
    question: str
    state: ItemState
    choice_dataset: ChoiceDatasetDTO | None = None
    code_languages: tuple[str, ...] = ()
    attempt_id: str | None = None
    expires_at: str | None = None
    batch_id: str | None = None
    draft_revision: int = 0
    quiz_data: dict[str, object] | None = None
    code_templates: dict[str, str] | None = None


@dataclass(frozen=True, slots=True)
class SubmissionDTO:
    id: str
    item_id: str
    delivery: DeliveryState
    grading: ItemState
    upstream_id: str | None = None
    reply_hash: str | None = None
    operation_id: str | None = None


@dataclass(frozen=True, slots=True)
class SubmissionReceiptDTO:
    item_id: str
    delivery: DeliveryState
    submission_id: str | None
    draft_revision: int | None


@dataclass(frozen=True, slots=True)
class RemoteSubmissionDTO:
    id: str
    state: ItemState
    feedback: str | None
    review_required: bool


@dataclass(frozen=True, slots=True)
class OperationDTO:
    id: str
    account_id: str
    item_id: str
    attempt_id: str
    reply: (
        ChoiceReplyDTO
        | TextReplyDTO
        | NumberReplyDTO
        | SqlReplyDTO
        | CodeReplyDTO
        | BlanksReplyDTO
        | MatchingReplyDTO
        | TableReplyDTO
    )
    state: OperationState
    reply_hash: str
    upstream_id: str | None = None


@dataclass(frozen=True, slots=True)
class PlanCountsDTO:
    available: int
    passed: int
    unknown_progress: int
    excluded_theory: int
    unsupported: int


@dataclass(frozen=True, slots=True)
class TaskTypeCountDTO:
    kind: str
    count: int


@dataclass(frozen=True, slots=True)
class PlanDTO:
    course_id: str
    selection: Selection
    counts: PlanCountsDTO
    types: tuple[TaskTypeCountDTO, ...]
    sections: tuple[CourseSectionDTO, ...]


@dataclass(frozen=True, slots=True)
class ChoiceTaskDTO:
    item_id: str
    step_id: str
    attempt_id: str
    question: str
    options: tuple[str, ...]
    is_multiple_choice: bool
    expires_at: str | None
    kind: str = "choice"
    code_languages: tuple[str, ...] = ()
    quiz_data: dict[str, object] | None = None
    code_templates: dict[str, str] | None = None


@dataclass(frozen=True, slots=True)
class BatchDTO:
    batch_id: str
    items: tuple[ChoiceTaskDTO, ...]
    more_available: bool
    recovered: bool = False


@dataclass(frozen=True, slots=True)
class RunStartedDTO:
    run_id: str
    state: RunState
    first_batch: BatchDTO


@dataclass(frozen=True, slots=True)
class NextBatchStateDTO:
    run_id: str
    state: RunState | None
    blocked: bool
    collect_required: bool
    finished: bool


@dataclass(frozen=True, slots=True)
class BatchCommitDTO:
    run_id: str
    receipts: tuple[SubmissionReceiptDTO, ...]
    collect_required: bool


@dataclass(frozen=True, slots=True)
class ResultsCountsDTO:
    correct: int
    wrong: int
    pending: int
    review_required: int
    outcome_unknown: int


@dataclass(frozen=True, slots=True)
class ResultsDTO:
    run_id: str
    counts: ResultsCountsDTO


@dataclass(frozen=True, slots=True)
class RunStatusDTO:
    run_id: str
    state: RunState


@dataclass(frozen=True, slots=True)
class RunControlDTO:
    run_id: str
    state: RunState
    recovery_required: tuple[str, ...]
    reconciled: tuple[str, ...]
    added_items: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RunResourceDTO:
    id: str
    course_id: str
    state: RunState
    items: tuple[ItemResourceDTO, ...]


@dataclass(frozen=True, slots=True)
class ItemResourceDTO:
    id: str
    state: ItemState
    kind: str
    question: str
    step_id: str = ""
    attempt_id: str | None = None
    quiz_data: dict[str, object] | None = None
    code_templates: dict[str, str] | None = None


@dataclass(frozen=True, slots=True)
class SubmissionResourceDTO:
    id: str
    item_id: str
    delivery: DeliveryState
    grading: ItemState


@dataclass(frozen=True, slots=True)
class ReadResultDTO:
    run: RunResourceDTO | None = None
    item: ItemResourceDTO | None = None
    submission: SubmissionResourceDTO | None = None
