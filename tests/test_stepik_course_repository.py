from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest

from stepik_autopilot.application.dto import TaskDTO
from stepik_autopilot.core.exceptions import ExternalServiceError, ValidationError
from stepik_autopilot.infra.stepik.client import StepikApiClient
from stepik_autopilot.infra.stepik.resources import StepikAttemptRepository, StepikCourseRepository

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
        identifiers = tuple(value for name, value in params or [] if name == "ids[]")
        responses = {
            "/api/units": {"200": {"id": 200, "assignments": [2000, 2001]}},
            "/api/assignments": {
                "2000": {"id": 2000, "step": 501},
                "2001": {"id": 2001, "step": 502},
            },
            "/api/steps": {
                identifier: {
                    "id": int(identifier),
                    "block": {
                        "name": "choice",
                        "text": f"Question {identifier}",
                        "options": {"choices": ["A", "B"]},
                    },
                }
                for identifier in identifiers
            },
            "/api/progresses": {},
        }
        for identifier in identifiers:
            yield responses[path][identifier]


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


class AttemptClient:
    def __init__(self, dataset: object) -> None:
        self._dataset = dataset

    async def request(
        self,
        method: str,
        path: str,
        params: list[tuple[str, str]] | None = None,
        json: dict[str, object] | None = None,
    ) -> dict[str, object]:
        assert method == "POST"
        assert path == "/api/attempts"
        assert params is None
        assert json == {"attempt": {"step": 501}}
        return {"attempts": [{"id": 42, "dataset": self._dataset}]}


def choice_task() -> TaskDTO:
    return TaskDTO("501", "2000", "42", "choice", "Question", None, False, False)


@pytest.mark.anyio
async def test_prepare_attempt_decodes_serialized_choice_dataset() -> None:
    client = AttemptClient('{"options": ["A", "B"], "is_multiple_choice": false}')
    repository = StepikAttemptRepository(cast("StepikApiClient", cast("object", client)))

    attempt = await repository.prepare_attempt(choice_task())

    assert attempt.id == "42"
    assert attempt.dataset is not None
    assert attempt.dataset.options == ("A", "B")
    assert attempt.dataset.is_multiple_choice is False


@pytest.mark.anyio
async def test_prepare_attempt_rejects_non_object_serialized_dataset() -> None:
    client = AttemptClient('["A", "B"]')
    repository = StepikAttemptRepository(cast("StepikApiClient", cast("object", client)))

    with pytest.raises(ExternalServiceError, match="Stepik attempt dataset is malformed"):
        await repository.prepare_attempt(choice_task())
