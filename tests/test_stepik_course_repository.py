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
        self.kind = "choice"
        self.templates: object = None
        self.step_batches: list[tuple[str, ...]] = []

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
        if path == "/api/steps":
            self.step_batches.append(identifiers)
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
                        "name": self.kind,
                        "text": f"Question {identifier}",
                        "options": {"choices": ["A", "B"], "code_templates": self.templates},
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


@pytest.mark.anyio
async def test_content_preserves_editor_templates_including_whitespace_and_empty_source() -> None:
    client = FakeStepikClient()
    client.kind = "code"
    client.templates = {"python3.12": "athletes = [('Дима', 10)]\n\ndef solve():\n    pass\n", "cpp": ""}
    repository = StepikCourseRepository(cast("Any", client))
    content = await repository.content("42", section_numbers=(2,))
    assert content.tasks[0].code_templates == client.templates
    assert content.tasks[0].code_languages == ("python3.12", "cpp")


@pytest.mark.anyio
async def test_template_lookup_reads_only_steps_in_bounded_deduplicated_batches() -> None:
    client = FakeStepikClient()
    client.kind = "code"
    client.templates = {"python3.12": "athletes = []\n"}
    repository = StepikCourseRepository(cast("Any", client))
    step_ids = tuple(map(str, range(31)))
    templates = await repository.code_templates((*step_ids, "0"))
    assert templates == dict.fromkeys(step_ids, client.templates)
    assert client.step_batches == [step_ids[:30], step_ids[30:]]
    assert not client.requests


@pytest.mark.anyio
@pytest.mark.parametrize("raw", [[], {"python3": None}, {1: "code"}])
async def test_template_lookup_rejects_malformed_source(raw) -> None:
    client = FakeStepikClient()
    client.kind, client.templates = "code", raw
    with pytest.raises(ExternalServiceError, match="code templates are malformed"):
        await StepikCourseRepository(cast("Any", client)).code_templates(("501",))


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


def task(kind: str, code_languages: tuple[str, ...] = ()) -> TaskDTO:
    return TaskDTO("501", "2000", "42", kind, "Question", None, False, False, code_languages=code_languages)


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


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["string", "number", "sql"])
async def test_prepare_attempt_allows_plugin_specific_dataset_when_it_is_not_needed(kind: str) -> None:
    client = AttemptClient(None)
    repository = StepikAttemptRepository(cast("StepikApiClient", cast("object", client)))

    attempt = await repository.prepare_attempt(task(kind))

    assert attempt.id == "42"
    assert attempt.dataset is None


@pytest.mark.anyio
async def test_prepare_code_attempt_uses_languages_from_step_options() -> None:
    client = AttemptClient("")
    repository = StepikAttemptRepository(cast("StepikApiClient", cast("object", client)))

    attempt = await repository.prepare_attempt(task("code", ("python3", "cpp")))

    assert attempt.id == "42"
    assert attempt.dataset is None
    assert attempt.code_languages == ("python3", "cpp")
