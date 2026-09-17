from stepik_autopilot.application.dto import CourseContentDTO, CoursePageDTO, PlanInputDTO, TaskDTO
from stepik_autopilot.application.use_cases.run import PlanCourse
from stepik_autopilot.core.enums import Selection
from stepik_autopilot.core.task_adapters import AdapterRegistry


class CourseGateway:
    async def courses(self, query: str | None, enrolled_only: bool, cursor: int, limit: int) -> CoursePageDTO:
        _ = query, enrolled_only, cursor, limit
        return CoursePageDTO((), None)

    async def content(
        self,
        course_id: str,
        explicit_step_ids: tuple[str, ...] | None = None,
        section_numbers: tuple[int, ...] | None = None,
    ) -> CourseContentDTO:
        _ = explicit_step_ids, section_numbers
        return CourseContentDTO(
            tasks=(
                TaskDTO("1", "1", course_id, "choice", "", None, False, False),
                TaskDTO("2", "2", course_id, "code", "", None, False, False),
                TaskDTO("3", "3", course_id, "table", "", None, False, False),
                TaskDTO("4", "4", course_id, "text", "", None, False, False),
                TaskDTO("5", "5", course_id, "video", "", None, False, False),
                TaskDTO("6", "6", course_id, "fill-blanks", "", None, False, False),
                TaskDTO("7", "7", course_id, "matching", "", None, False, False),
                TaskDTO("8", "8", course_id, "sorting", "", None, False, False),
            ),
            sections=(),
        )


async def test_plan_includes_every_practical_kind_and_excludes_lectures() -> None:
    plan = await PlanCourse(CourseGateway(), AdapterRegistry()).execute(
        PlanInputDTO("42", Selection.REMAINING, None, None)
    )

    assert plan.counts.available == 6
    assert plan.counts.excluded_theory == 2
    assert plan.counts.unsupported == 1
    assert [(item.kind, item.count) for item in plan.types] == [
        ("choice", 1),
        ("code", 1),
        ("fill-blanks", 1),
        ("matching", 1),
        ("sorting", 1),
        ("table", 1),
    ]
