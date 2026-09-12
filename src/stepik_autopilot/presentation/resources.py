from dishka import AsyncContainer, Scope

from stepik_autopilot.application.dto import ReadInputDTO
from stepik_autopilot.application.use_cases.catalog import ReadRunData
from stepik_autopilot.presentation.schemas import (
    ItemResourceOutput,
    ReadOutput,
    RunResourceOutput,
    SubmissionResourceOutput,
)


async def run_resource(container: AsyncContainer, run_id: str) -> RunResourceOutput:
    async with container(scope=Scope.REQUEST) as request_container:
        result = await (await request_container.get(ReadRunData)).execute(ReadInputDTO(run_id, None, None))
    if result.run is None:
        msg = "run resource was not returned"
        raise ValueError(msg)
    return RunResourceOutput.from_dto(result.run)


async def item_resource(container: AsyncContainer, run_id: str, item_id: str) -> ItemResourceOutput:
    async with container(scope=Scope.REQUEST) as request_container:
        result = await (await request_container.get(ReadRunData)).execute(ReadInputDTO(run_id, item_id, None))
    if result.item is None:
        msg = "item resource was not returned"
        raise ValueError(msg)
    return ItemResourceOutput.from_dto(result.item)


async def submission_resource(container: AsyncContainer, run_id: str, submission_id: str) -> SubmissionResourceOutput:
    async with container(scope=Scope.REQUEST) as request_container:
        result = await (await request_container.get(ReadRunData)).execute(ReadInputDTO(run_id, None, submission_id))
    if result.submission is None:
        msg = "submission resource was not returned"
        raise ValueError(msg)
    return SubmissionResourceOutput.from_dto(result.submission)


def resource_index() -> ReadOutput:
    return ReadOutput(runs=[], items=[], submissions=[])
