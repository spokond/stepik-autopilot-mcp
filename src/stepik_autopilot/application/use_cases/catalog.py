from stepik_autopilot.application.dto import (
    CoursePageDTO,
    ItemResourceDTO,
    ListCoursesInputDTO,
    ReadInputDTO,
    ReadResultDTO,
    RunResourceDTO,
    SubmissionResourceDTO,
)
from stepik_autopilot.application.protocols import (
    ItemRepository,
    RunRepository,
    StepikAccountGateway,
    StepikCourseGateway,
    SubmissionRepository,
)
from stepik_autopilot.core.exceptions import NotFoundError


class ListCourses:
    def __init__(self, courses: StepikCourseGateway) -> None:
        self._courses = courses

    async def execute(self, request: ListCoursesInputDTO) -> CoursePageDTO:
        return await self._courses.courses(request.query, request.enrolled_only, request.cursor, request.limit)


class ReadRunData:
    def __init__(
        self,
        accounts: StepikAccountGateway,
        runs: RunRepository,
        items: ItemRepository,
        submissions: SubmissionRepository,
    ) -> None:
        self._accounts, self._runs, self._items, self._submissions = accounts, runs, items, submissions

    async def execute(self, request: ReadInputDTO) -> ReadResultDTO:
        account = await self._accounts.current_account()
        run = await self._runs.get_run(account, request.run_id)
        if run is None:
            msg = "run not found"
            raise NotFoundError(msg)
        if request.item_id is not None:
            item = await self._items.get_item(account, run.id, request.item_id)
            if item is None:
                msg = "item not found"
                raise NotFoundError(msg)
            return ReadResultDTO(item=ItemResourceDTO(item.id, item.state, item.kind, item.question))
        if request.submission_id is not None:
            submission = await self._submissions.get_submission(account, run.id, request.submission_id)
            if submission is None:
                msg = "submission not found"
                raise NotFoundError(msg)
            return ReadResultDTO(
                submission=SubmissionResourceDTO(
                    submission.id, submission.item_id, submission.delivery, submission.grading
                )
            )
        items = await self._items.list_items(account, run.id)
        return ReadResultDTO(
            run=RunResourceDTO(
                run.id,
                run.course_id,
                run.state,
                tuple(ItemResourceDTO(item.id, item.state, item.kind, item.question) for item in items),
            )
        )
