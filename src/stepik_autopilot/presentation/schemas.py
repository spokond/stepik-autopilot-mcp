from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from stepik_autopilot.application.dto import (
    BatchCommitDTO,
    BatchDTO,
    ChoiceAnswerDTO,
    CodeAnswerDTO,
    CommitAnswerDTO,
    CoursePageDTO,
    CourseSectionDTO,
    ItemResourceDTO,
    NextBatchStateDTO,
    PlanCountsDTO,
    PlanDTO,
    ResultsDTO,
    RunControlDTO,
    RunResourceDTO,
    RunStartedDTO,
    RunStatusDTO,
    SqlAnswerDTO,
    SubmissionReceiptDTO,
    SubmissionResourceDTO,
    TaskTypeCountDTO,
    TextAnswerDTO,
)
from stepik_autopilot.core.enums import Grading, RunMode, Selection, Strategy, Target

RequestId = Annotated[str, StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")]
Identifier = Annotated[str, StringConstraints(min_length=1, max_length=128)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ErrorOutput(StrictModel):
    code: str = Field(description="Stable application error code.")
    message: str = Field(description="Human-readable error detail.")


class CourseOutput(StrictModel):
    id: str = Field(description="Stepik course identifier.")
    title: str = Field(description="Course title.")


class CoursesOutput(StrictModel):
    courses: list[CourseOutput] = Field(description="Courses on this page.")
    next_cursor: int | None = Field(description="Cursor for the next page.")

    @classmethod
    def from_dto(cls, value: CoursePageDTO) -> CoursesOutput:
        return cls(courses=[CourseOutput(id=x.id, title=x.title) for x in value.courses], next_cursor=value.next_cursor)


class CourseSectionOutput(StrictModel):
    number: int = Field(description="One-based section number in the course outline.")
    section_id: str = Field(description="Stepik section identifier.")
    title: str = Field(description="Section title.")
    step_ids: list[str] = Field(description="Selected Stepik steps in this section.")

    @classmethod
    def from_dto(cls, value: CourseSectionDTO) -> CourseSectionOutput:
        return cls(number=value.number, section_id=value.id, title=value.title, step_ids=list(value.step_ids))


class PlanOutput(StrictModel):
    course_id: str = Field(description="Planned course.")
    selection: str = Field(description="Selection mode.")
    counts: PlanCountsOutput = Field(description="Counted plan categories.")
    task_types: list[TaskTypeCountOutput] = Field(description="Observed Stepik task kinds and counts.")
    sections: list[CourseSectionOutput] = Field(
        description="Resolved section numbers, Stepik identifiers, titles, and selected steps."
    )

    @classmethod
    def from_dto(cls, value: PlanDTO) -> PlanOutput:
        return cls(
            course_id=value.course_id,
            selection=value.selection.value,
            counts=PlanCountsOutput.from_dto(value.counts),
            task_types=[TaskTypeCountOutput.from_dto(item) for item in value.types],
            sections=[CourseSectionOutput.from_dto(item) for item in value.sections],
        )


class PlanCountsOutput(StrictModel):
    available: int = Field(description="Supported available tasks.")
    passed: int = Field(description="Passed practical tasks.")
    unknown_progress: int = Field(description="Tasks with unknown progress.")
    excluded_theory: int = Field(description="Excluded lecture tasks.")
    unsupported: int = Field(description="Unsupported practical tasks.")

    @classmethod
    def from_dto(cls, value: PlanCountsDTO) -> PlanCountsOutput:
        return cls(
            available=value.available,
            passed=value.passed,
            unknown_progress=value.unknown_progress,
            excluded_theory=value.excluded_theory,
            unsupported=value.unsupported,
        )


class TaskTypeCountOutput(StrictModel):
    kind: str = Field(description="Stepik block kind.")
    count: int = Field(description="Number of tasks with this kind.")

    @classmethod
    def from_dto(cls, value: TaskTypeCountDTO) -> TaskTypeCountOutput:
        return cls(kind=value.kind, count=value.count)


class ChoiceBatchItemOutput(StrictModel):
    item_id: str = Field(description="Durable run item identifier.")
    step_id: str = Field(description="Stepik step identifier.")
    attempt_id: str = Field(description="Stepik attempt identifier.")
    question: str = Field(description="Question text.")
    options: list[str] = Field(description="Choice options in attempt order.")
    is_multiple_choice: bool = Field(description="Whether multiple options may be selected.")
    expires_at: str | None = Field(description="Attempt expiration timestamp.")
    kind: str = Field(description="Stepik block kind.")
    code_languages: list[str] = Field(description="Languages accepted by a code attempt.")


class BatchOutput(StrictModel):
    batch_id: str = Field(description="Durable batch identifier.")
    items: list[ChoiceBatchItemOutput] = Field(description="Prepared choice tasks.")
    more_available: bool = Field(description="Whether another ready batch exists.")
    recovered: bool = Field(description="Whether this is a recovered lease.")

    @classmethod
    def from_dto(cls, value: BatchDTO) -> BatchOutput:
        return cls(
            batch_id=value.batch_id,
            items=[
                ChoiceBatchItemOutput(
                    item_id=x.item_id,
                    step_id=x.step_id,
                    attempt_id=x.attempt_id,
                    question=x.question,
                    options=list(x.options),
                    is_multiple_choice=x.is_multiple_choice,
                    expires_at=x.expires_at,
                    kind=x.kind,
                    code_languages=list(x.code_languages),
                )
                for x in value.items
            ],
            more_available=value.more_available,
            recovered=value.recovered,
        )


class RunStartOutput(StrictModel):
    run_id: str = Field(description="Started run identifier.")
    state: str = Field(description="Run state.")
    first_batch: BatchOutput = Field(description="Initial prepared batch.")

    @classmethod
    def from_dto(cls, value: RunStartedDTO) -> RunStartOutput:
        return cls(run_id=value.run_id, state=value.state.value, first_batch=BatchOutput.from_dto(value.first_batch))


class RunNextStateOutput(StrictModel):
    run_id: str = Field(description="Run identifier.")
    state: str | None = Field(description="Current run state.")
    blocked: bool = Field(description="Whether dispatch is blocked.")
    collect_required: bool = Field(description="Whether collection is needed.")
    finished: bool = Field(description="Whether the run has no work left.")

    @classmethod
    def from_dto(cls, value: NextBatchStateDTO) -> RunNextStateOutput:
        return cls(
            run_id=value.run_id,
            state=value.state.value if value.state else None,
            blocked=value.blocked,
            collect_required=value.collect_required,
            finished=value.finished,
        )


class BatchCommitOutput(StrictModel):
    run_id: str = Field(description="Run identifier.")
    receipts: list[SubmissionReceiptOutput] = Field(description="Per-item delivery receipts.")
    collect_required: bool = Field(description="Whether deferred results should be collected.")

    @classmethod
    def from_dto(cls, value: BatchCommitDTO) -> BatchCommitOutput:
        return cls(
            run_id=value.run_id,
            receipts=[SubmissionReceiptOutput.from_dto(item) for item in value.receipts],
            collect_required=value.collect_required,
        )


class SubmissionReceiptOutput(StrictModel):
    item_id: str = Field(description="Durable item identifier.")
    delivery: str = Field(description="Confirmed delivery state.")
    submission_id: str | None = Field(description="Upstream Stepik submission identifier.")
    draft_revision: int | None = Field(description="Saved draft revision, if applicable.")

    @classmethod
    def from_dto(cls, value: SubmissionReceiptDTO) -> SubmissionReceiptOutput:
        return cls(
            item_id=value.item_id,
            delivery=value.delivery.value,
            submission_id=value.submission_id,
            draft_revision=value.draft_revision,
        )


class ResultsOutput(StrictModel):
    run_id: str = Field(description="Run identifier.")
    correct: int = Field(description="Correct results.")
    wrong: int = Field(description="Wrong results.")
    pending: int = Field(description="Pending evaluations.")
    review_required: int = Field(description="Results requiring review.")
    outcome_unknown: int = Field(description="Unknown outcomes.")

    @classmethod
    def from_dto(cls, value: ResultsDTO) -> ResultsOutput:
        return cls(
            run_id=value.run_id,
            correct=value.counts.correct,
            wrong=value.counts.wrong,
            pending=value.counts.pending,
            review_required=value.counts.review_required,
            outcome_unknown=value.counts.outcome_unknown,
        )


class RunControlOutput(StrictModel):
    run_id: str = Field(description="Run identifier.")
    state: str = Field(description="New run state.")
    recovery_required: list[str] = Field(description="Items needing reconciliation.")
    reconciled: list[str] = Field(description="Reconciled items.")

    @classmethod
    def from_dto(cls, value: RunControlDTO) -> RunControlOutput:
        return cls(
            run_id=value.run_id,
            state=value.state.value,
            recovery_required=list(value.recovery_required),
            reconciled=list(value.reconciled),
        )


class RunStatusOutput(StrictModel):
    run_id: str = Field(description="Run identifier.")
    state: str = Field(description="Run state.")

    @classmethod
    def from_dto(cls, value: RunStatusDTO) -> RunStatusOutput:
        return cls(run_id=value.run_id, state=value.state.value)


class ReadOutput(StrictModel):
    runs: list[RunResourceOutput] = Field(description="Resolved run resources.")
    items: list[ItemResourceOutput] = Field(description="Resolved item resources.")
    submissions: list[SubmissionResourceOutput] = Field(description="Resolved submission resources.")


class ItemResourceOutput(StrictModel):
    id: str = Field(description="Durable item identifier.")
    state: str = Field(description="Item state.")
    kind: str = Field(description="Stepik block kind.")
    question: str = Field(description="Question text.")

    @classmethod
    def from_dto(cls, value: ItemResourceDTO) -> ItemResourceOutput:
        return cls(id=value.id, state=value.state.value, kind=value.kind, question=value.question)


class RunResourceOutput(StrictModel):
    id: str = Field(description="Durable run identifier.")
    course_id: str = Field(description="Stepik course identifier.")
    state: str = Field(description="Run state.")
    items: list[ItemResourceOutput] = Field(description="Items belonging to this run.")

    @classmethod
    def from_dto(cls, value: RunResourceDTO) -> RunResourceOutput:
        return cls(
            id=value.id,
            course_id=value.course_id,
            state=value.state.value,
            items=[ItemResourceOutput.from_dto(item) for item in value.items],
        )


class SubmissionResourceOutput(StrictModel):
    id: str = Field(description="Durable submission identifier.")
    item_id: str = Field(description="Related durable item identifier.")
    delivery: str = Field(description="Delivery state.")
    grading: str = Field(description="Grading state.")

    @classmethod
    def from_dto(cls, value: SubmissionResourceDTO) -> SubmissionResourceOutput:
        return cls(
            id=value.id,
            item_id=value.item_id,
            delivery=value.delivery.value,
            grading=value.grading.value,
        )


class ChoiceAnswerInput(StrictModel):
    kind: Literal["choice"]
    selected_indexes: list[Annotated[int, Field(ge=0)]] = Field(min_length=1)

    def to_dto(self) -> ChoiceAnswerDTO:
        return ChoiceAnswerDTO(tuple(self.selected_indexes))


class TextAnswerInput(StrictModel):
    kind: Literal["string", "number"]
    value: str = Field(min_length=1)

    def to_dto(self) -> TextAnswerDTO:
        return TextAnswerDTO(self.value)


class CodeAnswerInput(StrictModel):
    kind: Literal["code"]
    language: str = Field(min_length=1)
    code: str = Field(min_length=1)

    def to_dto(self) -> CodeAnswerDTO:
        return CodeAnswerDTO(self.language, self.code)


class SqlAnswerInput(StrictModel):
    kind: Literal["sql"]
    code: str = Field(min_length=1)

    def to_dto(self) -> SqlAnswerDTO:
        return SqlAnswerDTO(self.code)


class CommitAnswerInput(StrictModel):
    item_id: Identifier
    answer: ChoiceAnswerInput | TextAnswerInput | SqlAnswerInput | CodeAnswerInput

    def to_dto(self) -> CommitAnswerDTO:
        return CommitAnswerDTO(self.item_id, self.answer.to_dto())


class CourseListInput(StrictModel):
    query: str | None = None
    enrolled_only: bool = True
    cursor: int = Field(default=1, ge=1)
    limit: int = Field(default=30, ge=1, le=100)


class PlanInput(StrictModel):
    course_id: Identifier
    selection: Selection = Field(default=Selection.REMAINING, strict=False)
    explicit_step_ids: list[Identifier] | None = Field(default=None, min_length=1)
    section_numbers: list[Annotated[int, Field(ge=1)]] | None = Field(default=None, min_length=1)

    @model_validator(mode="before")
    @classmethod
    def infer_selection(cls, value: object) -> object:
        if not isinstance(value, dict) or value.get("selection") is not None:
            return value
        if value.get("explicit_step_ids") is not None or value.get("section_numbers") is not None:
            return {**value, "selection": Selection.EXPLICIT}
        return value

    @model_validator(mode="after")
    def validate_selection_scope(self) -> PlanInput:
        has_steps = self.explicit_step_ids is not None
        has_sections = self.section_numbers is not None
        if has_steps and has_sections:
            msg = "explicit_step_ids and section_numbers are mutually exclusive"
            raise ValueError(msg)
        if self.selection is Selection.EXPLICIT and not (has_steps or has_sections):
            msg = "explicit selection requires explicit_step_ids or section_numbers"
            raise ValueError(msg)
        if self.selection is not Selection.EXPLICIT and (has_steps or has_sections):
            msg = "explicit_step_ids and section_numbers require selection='explicit'"
            raise ValueError(msg)
        if self.section_numbers is not None and len(set(self.section_numbers)) != len(self.section_numbers):
            msg = "section_numbers must not contain duplicates"
            raise ValueError(msg)
        return self


class RunStartInput(PlanInput):
    request_id: RequestId
    # MCP arguments arrive as JSON primitives.  Keep the model strict for all
    # other fields, but allow Pydantic to parse the documented enum strings.
    mode: RunMode = Field(default=RunMode.AUTOPILOT, strict=False)
    strategy: Strategy = Field(default=Strategy.BALANCED, strict=False)
    target: Target = Field(default=Target.TASKS_COMPLETE, strict=False)
    grading: Grading = Field(default=Grading.DEFERRED, strict=False)


class RunIdInput(StrictModel):
    run_id: Identifier


class IdempotentRunInput(RunIdInput):
    request_id: RequestId


class RunControlInput(IdempotentRunInput):
    action: Literal["pause", "resume", "cancel"]


class RunStatusInput(RunIdInput):
    pass


class BatchCommitInput(StrictModel):
    run_id: Identifier
    request_id: RequestId
    action: Literal["save", "submit"]
    answers: list[CommitAnswerInput] = Field(min_length=1)
    draft_revision: int | None = Field(default=None, ge=1)


class ReadInput(StrictModel):
    uris: list[str] = Field(min_length=1, max_length=20)
