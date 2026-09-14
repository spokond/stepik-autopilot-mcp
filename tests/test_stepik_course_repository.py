from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest

from stepik_autopilot.core.exceptions import ValidationError
from stepik_autopilot.infra.stepik.client import StepikApiClient
from stepik_autopilot.infra.stepik.resources import StepikCourseRepository

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class FakeStepikClient:
    def __init__(self) -> None:
        self.requests: list[str] = []

    async def request(
        self,
        method: str,
        path: str,
        params: list[tuple[str, str]] | None = None,
        json: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        del method, params, json
        self.requests.append(path)
        responses: dict[str, dict[str, Any]] = {
            "/api/courses/42": {"courses": [{"id": 42, "sections": [10, 20, 30]}]},
            "/api/sections/20": {"sections": [{"id": 20, "title": "Selected section", "units": [200]}]},
            "/api/units/200": {"units": [{"id": 200, "assignments": [2000, 2001]}]},
            "/api/assignments/2000": {"assignments": [{"id": 2000, "step": 501}]},
            "/api/assignments/2001": {"assignments": [{"id": 2001, "step": 502}]},
        }
        return responses[path]

    async def paged(
        self,
        path: str,
        key: str,
        params: list[tuple[str, str]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        del key
        assert path == "/api/steps"
        step_id = dict(params or [])["ids[]"]
        yield {
            "id": int(step_id),
            "block": {"name": "choice", "text": f"Question {step_id}", "options": {"choices": ["A", "B"]}},
        }


@pytest.mark.anyio
async def test_content_resolves_one_based_section_numbers_without_external_requests() -> None:
    client = FakeStepikClient()
    repository = StepikCourseRepository(cast("StepikApiClient", cast("object", client)))

    content = await repository.content("42", section_numbers=(2,))

    assert len(content.sections) == 1
    assert content.sections[0].number == 2
    assert content.sections[0].id == "20"
    assert content.sections[0].title == "Selected section"
    assert content.sections[0].step_ids == ("501", "502")
    assert tuple(task.step_id for task in content.tasks) == ("501", "502")
    assert "/api/sections/10" not in client.requests
    assert "/api/sections/30" not in client.requests


@pytest.mark.anyio
async def test_content_rejects_section_number_outside_course_outline() -> None:
    client = FakeStepikClient()
    repository = StepikCourseRepository(cast("StepikApiClient", cast("object", client)))

    with pytest.raises(ValidationError, match="course section numbers not found: 4"):
        await repository.content("42", section_numbers=(4,))

    assert client.requests == ["/api/courses/42"]
