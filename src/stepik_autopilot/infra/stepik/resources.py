import hashlib
import json
from collections.abc import Mapping

from stepik_autopilot.application.dto import (
    AttemptDTO,
    ChoiceDatasetDTO,
    ChoiceReplyDTO,
    CodeReplyDTO,
    CourseContentDTO,
    CoursePageDTO,
    CourseSectionDTO,
    CourseSummaryDTO,
    RemoteSubmissionDTO,
    SqlReplyDTO,
    TaskDTO,
    TextReplyDTO,
)
from stepik_autopilot.core.enums import ItemState
from stepik_autopilot.core.exceptions import ExternalServiceError, UnsupportedTaskError, ValidationError

from .client import StepikApiClient


def _objects(payload: Mapping[str, object], key: str) -> tuple[Mapping[str, object], ...]:
    raw = payload.get(key)
    if not isinstance(raw, list):
        msg = f"Stepik response has no {key!r} list"
        raise ExternalServiceError(msg)
    return tuple(value for value in raw if isinstance(value, Mapping))


def _attempt_dataset(raw: object) -> Mapping[str, object]:
    """Return Stepik's inline dataset, decoding its serialized JSON form."""
    if isinstance(raw, Mapping):
        return raw
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, Mapping):
            return decoded
    msg = "Stepik attempt dataset is malformed"
    raise ExternalServiceError(msg)


class StepikAccountRepository:
    def __init__(self, client: StepikApiClient) -> None:
        self._client = client

    async def current_account(self) -> str:
        values = _objects(await self._client.request("GET", "/api/stepics/1"), "stepics")
        if not values or values[0].get("id") is None:
            msg = "Stepik identity response is malformed"
            raise ExternalServiceError(msg)
        return str(values[0]["id"])


class StepikCourseRepository:
    def __init__(self, client: StepikApiClient) -> None:
        self._client = client

    async def courses(self, query: str | None, enrolled_only: bool, cursor: int, limit: int) -> CoursePageDTO:
        params = [("page", str(cursor)), ("page_size", str(limit))]
        if query:
            params.append(("search", query))
        if enrolled_only:
            params.append(("enrolled", "true"))
        payload = await self._client.request("GET", "/api/courses", params=params)
        courses = tuple(
            CourseSummaryDTO(str(value["id"]), str(value.get("title", "")))
            for value in _objects(payload, "courses")
            if value.get("id") is not None
        )
        meta = payload.get("meta")
        next_cursor = cursor + 1 if isinstance(meta, Mapping) and bool(meta.get("has_next")) else None
        return CoursePageDTO(courses, next_cursor)

    async def content(
        self,
        course_id: str,
        explicit_step_ids: tuple[str, ...] | None = None,
        section_numbers: tuple[int, ...] | None = None,
    ) -> CourseContentDTO:
        requested = frozenset(explicit_step_ids) if explicit_step_ids is not None else None
        requested_sections = frozenset(section_numbers) if section_numbers is not None else None
        course = _objects(await self._client.request("GET", f"/api/courses/{course_id}"), "courses")
        if not course:
            msg = "Stepik course response is malformed"
            raise ExternalServiceError(msg)
        tasks: list[TaskDTO] = []
        selected_sections: list[CourseSectionDTO] = []
        resolved_steps: set[str] = set()
        course_section_ids = self._identifiers(course[0].get("sections"))
        for section_number, section_id in self._selected_sections(course_section_ids, requested_sections):
            sections = _objects(await self._client.request("GET", f"/api/sections/{section_id}"), "sections")
            if not sections:
                continue
            section = sections[0]
            section_step_ids: list[str] = []
            units = await self._by_ids("/api/units", "units", self._identifiers(section.get("units")))
            assignment_ids = tuple(
                assignment_id for unit in units for assignment_id in self._identifiers(unit.get("assignments"))
            )
            assignments = await self._by_ids("/api/assignments", "assignments", assignment_ids)
            selected_assignments = tuple(
                assignment
                for assignment in assignments
                if assignment.get("id") is not None
                and assignment.get("step") is not None
                and (requested is None or str(assignment["step"]) in requested)
            )
            for assignment in selected_assignments:
                step_id = str(assignment["step"])
                section_step_ids.append(step_id)
                resolved_steps.add(step_id)
            steps = await self._by_ids(
                "/api/steps", "steps", tuple(str(assignment["step"]) for assignment in selected_assignments)
            )
            progress_ids = tuple(
                str(assignment["progress"])
                for assignment in selected_assignments
                if assignment.get("progress") is not None
            )
            progresses = await self._by_ids("/api/progresses", "progresses", progress_ids)
            steps_by_id = {str(step["id"]): step for step in steps if step.get("id") is not None}
            passed_by_progress: dict[str, bool] = {}
            for progress in progresses:
                progress_id = progress.get("id")
                passed = progress.get("is_passed")
                if progress_id is not None and isinstance(passed, bool):
                    passed_by_progress[str(progress_id)] = passed
            for assignment in selected_assignments:
                step = steps_by_id.get(str(assignment["step"]))
                if step is None:
                    continue
                progress_id = str(assignment["progress"]) if assignment.get("progress") is not None else None
                tasks.append(
                    self._task(
                        step,
                        course_id,
                        str(assignment["id"]),
                        progress_id,
                        passed_by_progress.get(progress_id) if progress_id is not None else None,
                    )
                )
            if requested_sections is not None or (requested is not None and section_step_ids):
                selected_sections.append(
                    CourseSectionDTO(section_number, section_id, str(section.get("title", "")), tuple(section_step_ids))
                )
        if requested is not None and (missing_steps := requested.difference(resolved_steps)):
            missing = sorted(missing_steps)
            msg = f"course step ids not found: {', '.join(missing)}"
            raise ValidationError(msg)
        return CourseContentDTO(tuple(tasks), tuple(selected_sections))

    @staticmethod
    def _selected_sections(
        section_ids: tuple[str, ...], requested: frozenset[int] | None
    ) -> tuple[tuple[int, str], ...]:
        numbered = tuple(enumerate(section_ids, start=1))
        if requested is None:
            return numbered
        missing = sorted(requested - set(range(1, len(section_ids) + 1)))
        if missing:
            msg = f"course section numbers not found: {', '.join(map(str, missing))}"
            raise ValidationError(msg)
        return tuple(item for item in numbered if item[0] in requested)

    async def _by_ids(self, path: str, key: str, identifiers: tuple[str, ...]) -> tuple[Mapping[str, object], ...]:
        values: list[Mapping[str, object]] = []
        for offset in range(0, len(identifiers), 30):
            params = [("ids[]", identifier) for identifier in identifiers[offset : offset + 30]]
            async for value in self._client.paged(path, key, params):
                values.append(value)
        return tuple(values)

    @staticmethod
    def _identifiers(raw: object) -> tuple[str, ...]:
        return tuple(str(value) for value in raw) if isinstance(raw, list) else ()

    @staticmethod
    def _task(
        step: Mapping[str, object], course_id: str, assignment_id: str, progress_id: str | None, passed: bool | None
    ) -> TaskDTO:
        block = step.get("block")
        if not isinstance(block, Mapping) or not isinstance(block.get("name"), str) or step.get("id") is None:
            msg = "Stepik step response is malformed"
            raise ExternalServiceError(msg)
        kind = str(block["name"])
        options_raw = block.get("options")
        options = options_raw if isinstance(options_raw, Mapping) else {}
        choices_raw = options.get("choices")
        choices = tuple(str(choice) for choice in choices_raw) if isinstance(choices_raw, list) else ()
        return TaskDTO(
            step_id=str(step["id"]),
            assignment_id=assignment_id,
            course_id=course_id,
            kind=kind,
            question=str(block.get("text", "")),
            progress_id=progress_id,
            is_passed=passed,
            failed=False,
            choice_options=choices,
            is_multiple_choice=bool(options.get("is_multiple_choice", False)),
        )


class StepikAttemptRepository:
    def __init__(self, client: StepikApiClient) -> None:
        self._client = client

    async def prepare_attempt(self, task: TaskDTO) -> AttemptDTO:
        if task.kind not in {"choice", "string", "number", "sql", "code"}:
            msg = f"unsupported task {task.kind}"
            raise UnsupportedTaskError(msg)
        payload = await self._client.request("POST", "/api/attempts", json={"attempt": {"step": int(task.step_id)}})
        values = _objects(payload, "attempts")
        if not values or values[0].get("id") is None:
            msg = "Stepik attempt response is malformed"
            raise ExternalServiceError(msg)
        attempt = values[0]
        dataset_raw = _attempt_dataset(attempt.get("dataset"))
        options_raw = dataset_raw.get("options")
        if task.kind == "choice" and not isinstance(options_raw, list):
            msg = "choice attempt has no confirmed options"
            raise UnsupportedTaskError(msg)
        code_languages: tuple[str, ...] = ()
        if task.kind == "code":
            options = options_raw if isinstance(options_raw, Mapping) else {}
            templates = options.get("code_templates")
            if not isinstance(templates, Mapping) or not templates:
                msg = "code attempt has no confirmed languages"
                raise UnsupportedTaskError(msg)
            code_languages = tuple(str(language) for language in templates)
        return AttemptDTO(
            id=str(attempt["id"]),
            step_id=task.step_id,
            dataset=(
                ChoiceDatasetDTO(
                    tuple(str(option) for option in options_raw), bool(dataset_raw.get("is_multiple_choice", False))
                )
                if isinstance(options_raw, list)
                else None
            ),
            expires_at=str(attempt["time_left"]) if attempt.get("time_left") is not None else None,
            code_languages=code_languages,
        )


class StepikSubmissionRepository:
    def __init__(self, client: StepikApiClient) -> None:
        self._client = client

    async def submit(
        self, attempt_id: str, reply: ChoiceReplyDTO | TextReplyDTO | SqlReplyDTO | CodeReplyDTO
    ) -> RemoteSubmissionDTO:
        payload = (
            {"choices": list(reply.choices)}
            if isinstance(reply, ChoiceReplyDTO)
            else {"text": reply.text}
            if isinstance(reply, TextReplyDTO)
            else {"solve_sql": reply.solve_sql}
            if isinstance(reply, SqlReplyDTO)
            else {"language": reply.language, "code": reply.code}
        )
        payload = await self._client.request(
            "POST",
            "/api/submissions",
            json={"submission": {"attempt": int(attempt_id), "reply": payload}},
        )
        values = _objects(payload, "submissions")
        if not values:
            msg = "Stepik submission response is malformed"
            raise ExternalServiceError(msg)
        return self._submission(values[0])

    async def submissions(self, ids: tuple[str, ...]) -> tuple[RemoteSubmissionDTO, ...]:
        result: list[RemoteSubmissionDTO] = []
        for offset in range(0, len(ids), 30):
            async for value in self._client.paged(
                "/api/submissions", "submissions", [("ids[]", item) for item in ids[offset : offset + 30]]
            ):
                result.append(self._submission(value))
        return tuple(result)

    async def find_submission(self, attempt_id: str, reply_hash: str) -> RemoteSubmissionDTO | None:
        async for value in self._client.paged("/api/submissions", "submissions", [("attempt", attempt_id)]):
            reply = value.get("reply")
            if isinstance(reply, Mapping):
                digest = hashlib.sha256(
                    json.dumps(dict(reply), sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                if digest == reply_hash:
                    return self._submission(value)
        return None

    @staticmethod
    def _submission(value: Mapping[str, object]) -> RemoteSubmissionDTO:
        if value.get("id") is None:
            msg = "Stepik submission has no id"
            raise ExternalServiceError(msg)
        status = str(value.get("status", "evaluation"))
        state = {"correct": ItemState.CORRECT, "wrong": ItemState.WRONG, "evaluation": ItemState.EVALUATION}.get(
            status, ItemState.EVALUATION
        )
        hint = value.get("hint")
        return RemoteSubmissionDTO(str(value["id"]), state, str(hint) if hint is not None else None, status == "review")
