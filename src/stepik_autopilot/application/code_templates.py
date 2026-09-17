from dataclasses import replace

from stepik_autopilot.application.dto import BatchDTO, ChoiceTaskDTO, ItemDTO
from stepik_autopilot.application.protocols import StepikCourseGateway


class CodeTemplates:
    """Read missing editor templates for runs persisted before templates were stored."""

    def __init__(self, courses: StepikCourseGateway) -> None:
        self._courses = courses

    async def enrich[T: (ItemDTO, ChoiceTaskDTO)](self, items: tuple[T, ...]) -> tuple[T, ...]:
        step_ids = tuple(
            dict.fromkeys(item.step_id for item in items if item.kind == "code" and item.code_templates is None)
        )
        if not step_ids:
            return items
        templates = await self._courses.code_templates(step_ids)
        return tuple(
            replace(item, code_templates=templates[item.step_id])
            if item.kind == "code" and item.code_templates is None
            else item
            for item in items
        )

    async def batch(self, batch: BatchDTO) -> BatchDTO:
        return replace(batch, items=await self.enrich(batch.items))
