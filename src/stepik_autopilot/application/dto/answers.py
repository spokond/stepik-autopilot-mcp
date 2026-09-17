from dataclasses import dataclass

from stepik_autopilot.core.enums import Grading, RunMode, Selection, Strategy, Target


@dataclass(frozen=True, slots=True)
class ChoiceAnswerDTO:
    selected_indexes: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class TextAnswerDTO:
    value: str


@dataclass(frozen=True, slots=True)
class SqlAnswerDTO:
    code: str


@dataclass(frozen=True, slots=True)
class CodeAnswerDTO:
    language: str
    code: str


@dataclass(frozen=True, slots=True)
class BlanksAnswerDTO:
    blanks: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MatchingAnswerDTO:
    ordering: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class TableAnswerDTO:
    selected_columns: tuple[tuple[int, ...], ...]


@dataclass(frozen=True, slots=True)
class CommitAnswerDTO:
    item_id: str
    answer: (
        ChoiceAnswerDTO
        | TextAnswerDTO
        | SqlAnswerDTO
        | CodeAnswerDTO
        | BlanksAnswerDTO
        | MatchingAnswerDTO
        | TableAnswerDTO
    )


@dataclass(frozen=True, slots=True)
class ListCoursesInputDTO:
    query: str | None
    enrolled_only: bool
    cursor: int
    limit: int


@dataclass(frozen=True, slots=True)
class PlanInputDTO:
    course_id: str
    selection: Selection
    explicit_step_ids: tuple[str, ...] | None
    section_numbers: tuple[int, ...] | None


@dataclass(frozen=True, slots=True)
class StartRunInputDTO:
    course_id: str
    mode: RunMode
    strategy: Strategy
    target: Target
    selection: Selection
    grading: Grading
    explicit_step_ids: tuple[str, ...] | None
    section_numbers: tuple[int, ...] | None
    request_id: str


@dataclass(frozen=True, slots=True)
class NextBatchInputDTO:
    run_id: str
    request_id: str


@dataclass(frozen=True, slots=True)
class CommitBatchInputDTO:
    run_id: str
    request_id: str
    action: str
    answers: tuple[CommitAnswerDTO, ...]
    draft_revision: int | None


@dataclass(frozen=True, slots=True)
class CollectResultsInputDTO:
    run_id: str


@dataclass(frozen=True, slots=True)
class RunControlInputDTO:
    run_id: str
    action: str
    request_id: str
    explicit_step_ids: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class RunStatusInputDTO:
    run_id: str


@dataclass(frozen=True, slots=True)
class ReadInputDTO:
    run_id: str
    item_id: str | None
    submission_id: str | None
