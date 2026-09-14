from urllib.parse import urlparse

from dishka import AsyncContainer, Scope

from stepik_autopilot.application.dto import (
    BatchDTO,
    CollectResultsInputDTO,
    CommitBatchInputDTO,
    ListCoursesInputDTO,
    NextBatchInputDTO,
    PlanInputDTO,
    ReadInputDTO,
    RunControlInputDTO,
    RunStatusInputDTO,
    StartRunInputDTO,
)
from stepik_autopilot.application.use_cases.catalog import ListCourses, ReadRunData
from stepik_autopilot.application.use_cases.run import (
    CollectResults,
    CommitBatch,
    ControlRun,
    NextBatch,
    PlanCourse,
    RunStatus,
    StartRun,
)
from stepik_autopilot.core.exceptions import StepikAutopilotError, ValidationError
from stepik_autopilot.presentation.schemas import (
    BatchCommitInput,
    BatchCommitOutput,
    BatchOutput,
    CourseListInput,
    CoursesOutput,
    ErrorOutput,
    IdempotentRunInput,
    ItemResourceOutput,
    PlanInput,
    PlanOutput,
    ReadInput,
    ReadOutput,
    ResultsOutput,
    RunControlInput,
    RunControlOutput,
    RunIdInput,
    RunNextStateOutput,
    RunResourceOutput,
    RunStartInput,
    RunStartOutput,
    RunStatusInput,
    RunStatusOutput,
    SubmissionResourceOutput,
)


def error_output(error: StepikAutopilotError) -> ErrorOutput:
    return ErrorOutput(code=error.code, message=str(error))


async def stepik_courses(container: AsyncContainer, arguments: CourseListInput) -> CoursesOutput | ErrorOutput:
    try:
        async with container(scope=Scope.REQUEST) as request_container:
            value = await (await request_container.get(ListCourses)).execute(
                ListCoursesInputDTO(arguments.query, arguments.enrolled_only, arguments.cursor, arguments.limit)
            )
            return CoursesOutput.from_dto(value)
    except StepikAutopilotError as error:
        return error_output(error)


async def stepik_plan(container: AsyncContainer, arguments: PlanInput) -> PlanOutput | ErrorOutput:
    try:
        async with container(scope=Scope.REQUEST) as request_container:
            value = await (await request_container.get(PlanCourse)).execute(
                PlanInputDTO(
                    arguments.course_id,
                    arguments.selection,
                    tuple(arguments.explicit_step_ids) if arguments.explicit_step_ids else None,
                    tuple(arguments.section_numbers) if arguments.section_numbers else None,
                )
            )
            return PlanOutput.from_dto(value)
    except StepikAutopilotError as error:
        return error_output(error)


async def stepik_run_start(container: AsyncContainer, arguments: RunStartInput) -> RunStartOutput | ErrorOutput:
    try:
        async with container(scope=Scope.REQUEST) as request_container:
            input = StartRunInputDTO(
                arguments.course_id,
                arguments.mode,
                arguments.strategy,
                arguments.target,
                arguments.selection,
                arguments.grading,
                tuple(arguments.explicit_step_ids) if arguments.explicit_step_ids else None,
                tuple(arguments.section_numbers) if arguments.section_numbers else None,
                arguments.request_id,
            )
            return RunStartOutput.from_dto(await (await request_container.get(StartRun)).execute(input))
    except StepikAutopilotError as error:
        return error_output(error)


async def stepik_run_next(
    container: AsyncContainer, arguments: IdempotentRunInput
) -> BatchOutput | RunNextStateOutput | ErrorOutput:
    try:
        async with container(scope=Scope.REQUEST) as request_container:
            value = await (await request_container.get(NextBatch)).execute(
                NextBatchInputDTO(arguments.run_id, arguments.request_id)
            )
            return BatchOutput.from_dto(value) if isinstance(value, BatchDTO) else RunNextStateOutput.from_dto(value)
    except StepikAutopilotError as error:
        return error_output(error)


async def stepik_batch_commit(
    container: AsyncContainer, arguments: BatchCommitInput
) -> BatchCommitOutput | ErrorOutput:
    try:
        async with container(scope=Scope.REQUEST) as request_container:
            answers = tuple(answer.to_dto() for answer in arguments.answers)
            value = await (await request_container.get(CommitBatch)).execute(
                CommitBatchInputDTO(
                    arguments.run_id, arguments.request_id, arguments.action, answers, arguments.draft_revision
                )
            )
            return BatchCommitOutput.from_dto(value)
    except StepikAutopilotError as error:
        return error_output(error)


async def stepik_results_collect(container: AsyncContainer, arguments: RunIdInput) -> ResultsOutput | ErrorOutput:
    try:
        async with container(scope=Scope.REQUEST) as request_container:
            return ResultsOutput.from_dto(
                await (await request_container.get(CollectResults)).execute(CollectResultsInputDTO(arguments.run_id))
            )
    except StepikAutopilotError as error:
        return error_output(error)


async def stepik_run_control(container: AsyncContainer, arguments: RunControlInput) -> RunControlOutput | ErrorOutput:
    try:
        async with container(scope=Scope.REQUEST) as request_container:
            return RunControlOutput.from_dto(
                await (await request_container.get(ControlRun)).execute(
                    RunControlInputDTO(arguments.run_id, arguments.action, arguments.request_id)
                )
            )
    except StepikAutopilotError as error:
        return error_output(error)


async def stepik_run_status(container: AsyncContainer, arguments: RunStatusInput) -> RunStatusOutput | ErrorOutput:
    try:
        async with container(scope=Scope.REQUEST) as request_container:
            return RunStatusOutput.from_dto(
                await (await request_container.get(RunStatus)).execute(RunStatusInputDTO(arguments.run_id))
            )
    except StepikAutopilotError as error:
        return error_output(error)


async def stepik_read(container: AsyncContainer, arguments: ReadInput) -> ReadOutput | ErrorOutput:
    try:
        runs: list[RunResourceOutput] = []
        items: list[ItemResourceOutput] = []
        submissions: list[SubmissionResourceOutput] = []
        async with container(scope=Scope.REQUEST) as request_container:
            use_case = await request_container.get(ReadRunData)
            for uri in arguments.uris:
                parsed = urlparse(uri)
                parts = tuple(part for part in parsed.path.split("/") if part)
                if parsed.scheme != "stepik" or parsed.netloc != "runs" or not parts:
                    msg = "unsupported private resource URI"
                    raise ValidationError(msg)
                item_id = parts[2] if len(parts) == 3 and parts[1] == "items" else None
                submission_id = parts[2] if len(parts) == 3 and parts[1] == "submissions" else None
                if len(parts) not in {1, 3}:
                    msg = "unsupported private resource URI"
                    raise ValidationError(msg)
                value = await use_case.execute(ReadInputDTO(parts[0], item_id, submission_id))
                if value.run is not None:
                    runs.append(RunResourceOutput.from_dto(value.run))
                elif value.item is not None:
                    items.append(ItemResourceOutput.from_dto(value.item))
                elif value.submission is not None:
                    submissions.append(SubmissionResourceOutput.from_dto(value.submission))
                else:
                    msg = "read result has no resource"
                    raise ValidationError(msg)
        return ReadOutput(runs=runs, items=items, submissions=submissions)
    except StepikAutopilotError as error:
        return error_output(error)
