import json
from typing import Any, cast

import pytest

from stepik_autopilot.application.dto import TaskDTO
from stepik_autopilot.application.replies import hash_reply, reply_payload
from stepik_autopilot.core.exceptions import UnsupportedTaskError, ValidationError
from stepik_autopilot.core.task_adapters import AdapterRegistry
from stepik_autopilot.infra.repositories.operations import OperationRepository
from stepik_autopilot.infra.stepik.client import StepikApiClient
from stepik_autopilot.infra.stepik.resources import StepikAttemptRepository, StepikSubmissionRepository
from stepik_autopilot.presentation.schemas import CommitAnswerInput

CASES = [
    (
        "number",
        None,
        {"kind": "number", "value": "0.0000000000001"},
        {"number": "0.0000000000001"},
    ),
    ("string", None, {"kind": "string", "value": "5"}, {"text": "5"}),
    (
        "fill-blanks",
        {
            "components": [
                {"type": "text", "text": "print("},
                {"type": "input", "text": ""},
                {"type": "text", "text": ") is "},
                {"type": "select", "options": ["True", "False"]},
            ]
        },
        {"kind": "fill-blanks", "blanks": ["None == None", "True"]},
        {"blanks": ["None == None", "True"]},
    ),
    (
        "matching",
        {
            "pairs": [
                {"first": "один", "second": "two"},
                {"first": "два", "second": "one"},
            ]
        },
        {"kind": "matching", "ordering": [1, 0]},
        {"ordering": [1, 0]},
    ),
    (
        "table",
        {"rows": ["a", "b"], "columns": ["True", "False"], "is_checkbox": False},
        {"kind": "table", "selected_columns": [[1], [0]]},
        {
            "choices": [
                {"name_row": "a", "columns": [{"name": "True", "answer": False}, {"name": "False", "answer": True}]},
                {"name_row": "b", "columns": [{"name": "True", "answer": True}, {"name": "False", "answer": False}]},
            ]
        },
    ),
]


class WireClient:
    def __init__(self, dataset: object, expected: dict[str, object]) -> None:
        self.dataset, self.expected = dataset, expected
        self.posts: list[dict[str, object]] = []

    async def request(self, method: str, path: str, *, json: dict[str, object]) -> dict[str, Any]:
        assert method == "POST"
        if path == "/api/attempts":
            assert json == {"attempt": {"step": 501}}
            return {"attempts": [{"id": 42, "dataset": self.dataset}]}
        assert path == "/api/submissions"
        assert json == {"submission": {"attempt": 42, "reply": self.expected}}
        self.posts.append(json)
        return {"submissions": [{"id": 77, "status": "correct"}]}

    async def paged(self, path: str, key: str, params: list[tuple[str, str]]):
        assert (path, key, params) == ("/api/submissions", "submissions", [("attempt", "42")])
        # A historical text submission must not match the fixed number hash.
        yield {"id": 76, "status": "wrong", "reply": {"text": "0.0000000000001"}}
        yield {"id": 77, "status": "correct", "reply": self.expected}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.parametrize(("kind", "dataset", "answer", "expected"), CASES)
@pytest.mark.parametrize("serialized", [False, True])
async def test_answer_contract_through_attempt_wire_and_journal(kind, dataset, answer, expected, serialized):
    client = WireClient(json.dumps(dataset) if serialized else dataset, expected)
    attempts = StepikAttemptRepository(cast("StepikApiClient", client))
    attempt = await attempts.prepare_attempt(TaskDTO("501", "1", "2", kind, "question", None, False, False))
    parsed = CommitAnswerInput.model_validate({"item_id": "item", "answer": answer}).to_dto()
    reply = AdapterRegistry().build_reply(kind, parsed.answer, attempt.dataset, (), attempt.quiz_data)
    assert reply_payload(reply) == expected
    journal_reply = OperationRepository._reply(OperationRepository._reply_value(reply))
    assert journal_reply == reply
    assert hash_reply(journal_reply) == hash_reply(reply)
    gateway = StepikSubmissionRepository(cast("StepikApiClient", client))
    result = await gateway.submit("42", reply)
    assert result.id == "77"
    recovered = await gateway.find_submission("42", hash_reply(journal_reply))
    assert recovered is not None
    assert recovered.id == "77"


@pytest.mark.parametrize(
    ("case_index", "changes"),
    [
        (2, {"blanks": ["x"]}),
        (2, {"blanks": ["x", "missing"]}),
        (3, {"ordering": [0, 0]}),
        (3, {"ordering": [1, 2]}),
        (3, {"ordering": [1]}),
        (4, {"selected_columns": [[0]]}),
        (4, {"selected_columns": [[0, 1], [1]]}),
        (4, {"selected_columns": [[0], [2]]}),
        (4, {"selected_columns": [[0], []]}),
        (4, {"selected_columns": [[0], [1, 1]]}),
    ],
)
def test_invalid_answer_rejected_before_sending(case_index, changes):
    kind, dataset, answer, _ = CASES[case_index]
    parsed = CommitAnswerInput.model_validate({"item_id": "item", "answer": {**answer, **changes}}).to_dto()
    with pytest.raises(ValidationError):
        AdapterRegistry().build_reply(kind, parsed.answer, None, (), dataset)


def test_table_checkbox_allows_multiple_and_empty_selections():
    kind, dataset, answer, _ = CASES[4]
    parsed = CommitAnswerInput.model_validate(
        {
            "item_id": "item",
            "answer": {**answer, "selected_columns": [[0, 1], []]},
        }
    ).to_dto()
    reply = AdapterRegistry().build_reply(kind, parsed.answer, None, (), {**dataset, "is_checkbox": True})
    assert reply_payload(reply)["choices"] == [
        {"name_row": "a", "columns": [{"name": "True", "answer": True}, {"name": "False", "answer": True}]},
        {"name_row": "b", "columns": [{"name": "True", "answer": False}, {"name": "False", "answer": False}]},
    ]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("kind", "dataset"),
    [
        ("matching", {"pairs": [["one", "two"]]}),
        ("table", {"rows": ["a"], "columns": []}),
        ("fill-blanks", {"components": [{"type": "unknown"}]}),
        ("fill-blanks", {"components": [{"type": "select"}]}),
    ],
)
async def test_malformed_dataset_is_not_leased(kind, dataset):
    gateway = StepikAttemptRepository(cast("StepikApiClient", WireClient(dataset, {})))
    with pytest.raises(UnsupportedTaskError):
        await gateway.prepare_attempt(TaskDTO("501", "1", "2", kind, "question", None, False, False))
