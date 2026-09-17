from dataclasses import replace
from typing import Any, cast

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from stepik_autopilot.application.dto import (
    AttemptDTO,
    BatchDTO,
    ChoiceTaskDTO,
    CollectResultsInputDTO,
    CommitAnswerDTO,
    CommitBatchInputDTO,
    CourseContentDTO,
    ItemDTO,
    NextBatchInputDTO,
    NumberReplyDTO,
    OperationDTO,
    ReadInputDTO,
    RemoteSubmissionDTO,
    RunControlInputDTO,
    RunDTO,
    StartRunInputDTO,
    SubmissionDTO,
    TaskDTO,
    TextAnswerDTO,
    TextReplyDTO,
)
from stepik_autopilot.application.replies import ReplyDTO, hash_reply
from stepik_autopilot.application.use_cases.catalog import ReadRunData
from stepik_autopilot.application.use_cases.run import (
    CollectResults,
    CommitBatch,
    ControlRun,
    NextBatch,
    StartRun,
    hash_text,
)
from stepik_autopilot.core.enums import (
    DeliveryState,
    Grading,
    ItemState,
    OperationState,
    RunMode,
    RunState,
    Selection,
    Strategy,
    Target,
)
from stepik_autopilot.core.exceptions import ExternalServiceError, ValidationError
from stepik_autopilot.core.task_adapters import AdapterRegistry
from stepik_autopilot.infra.repositories import (
    BatchRepository,
    IdempotencyRepository,
    ItemRepository,
    OperationRepository,
    RunRepository,
    SubmissionRepository,
)
from stepik_autopilot.infra.tables import idempotency, metadata, operations
from stepik_autopilot.infra.tables import items as run_items
from stepik_autopilot.presentation.schemas import BatchOutput, ItemResourceOutput


class Gateway:
    def __init__(self) -> None:
        self.remote: dict[str, RemoteSubmissionDTO] = {}
        self.sent: list[tuple[str, ReplyDTO]] = []
        self.attempts: list[str] = []
        self.tasks: tuple[TaskDTO, ...] = ()
        self.quiz_data: dict[str, dict[str, object]] = {}
        self.template_reads: list[tuple[str, ...]] = []
        self.fail_after_send = False

    async def current_account(self) -> str:
        return "account"

    async def prepare_attempt(self, task: TaskDTO) -> AttemptDTO:
        self.attempts.append(task.step_id)
        return AttemptDTO(
            str(200 + len(self.attempts)),
            task.step_id,
            None,
            None,
            code_languages=task.code_languages,
            quiz_data=self.quiz_data.get(task.kind),
        )

    async def submit(self, attempt_id: str, reply: ReplyDTO) -> RemoteSubmissionDTO:
        self.sent.append((attempt_id, reply))
        result = RemoteSubmissionDTO(str(300 + len(self.sent)), ItemState.CORRECT, None, False)
        self.remote[result.id] = result
        if self.fail_after_send:
            msg = "simulated lost response"
            raise ExternalServiceError(msg)
        return result

    async def submissions(self, ids: tuple[str, ...]) -> tuple[RemoteSubmissionDTO, ...]:
        return tuple(self.remote[value] for value in ids if value in self.remote)

    async def find_submission(self, attempt_id: str, reply_hash: str) -> RemoteSubmissionDTO | None:
        for index, (attempt, reply) in enumerate(self.sent, 301):
            if attempt == attempt_id and hash_reply(reply) == reply_hash:
                return self.remote[str(index)]
        return None

    async def content(
        self,
        course_id: str,
        explicit_step_ids: tuple[str, ...] | None = None,
        section_numbers: tuple[int, ...] | None = None,
    ) -> CourseContentDTO:
        return CourseContentDTO(
            tuple(task for task in self.tasks if explicit_step_ids is None or task.step_id in explicit_step_ids), ()
        )

    async def code_templates(self, step_ids: tuple[str, ...]) -> dict[str, dict[str, str]]:
        self.template_reads.append(step_ids)
        return {task.step_id: task.code_templates or {} for task in self.tasks if task.step_id in step_ids}


class Scenario:
    def __init__(self, connection: AsyncConnection, gateway: Gateway) -> None:
        self.connection, self.gateway = connection, gateway
        self.runs = RunRepository(connection)
        self.items = ItemRepository(connection)
        self.batches = BatchRepository(connection)
        self.submissions = SubmissionRepository(connection)
        self.operations = OperationRepository(connection)
        self.idempotency = IdempotencyRepository(connection)
        # Concrete SQL repositories are exercised; only the network is replaced.
        self.commit = CommitBatch(
            gateway,
            gateway,
            self.runs,
            self.items,
            cast("Any", self.submissions),
            self.batches,
            self.operations,
            AdapterRegistry(),
            self.idempotency,
            gateway,
        )
        self.control = ControlRun(
            gateway,
            self.runs,
            self.items,
            self.operations,
            gateway,
            self.idempotency,
            cast("Any", self.submissions),
            cast("Any", gateway),
        )
        self.collect = CollectResults(gateway, gateway, self.items, cast("Any", self.submissions))
        self.next = NextBatch(
            gateway,
            gateway,
            self.runs,
            self.items,
            self.batches,
            self.idempotency,
            AdapterRegistry(),
            cast("Any", gateway),
        )

    async def seed_wrong_numbers(self) -> None:
        for index in (1, 2):
            item = ItemDTO(
                f"n{index}",
                "run",
                str(index),
                "1",
                "number",
                "question",
                ItemState.WRONG,
                attempt_id=str(index),
                batch_id="old",
            )
            await self.items.add_items((item,))
            old_reply = TextReplyDTO("5" if index == 1 else "15")
            await self.operations.create_operation(
                OperationDTO(
                    f"old{index}",
                    "account",
                    item.id,
                    str(index),
                    old_reply,
                    OperationState.ACCEPTED,
                    hash_reply(old_reply),
                    str(index),
                )
            )
            await self.submissions.create_submission(
                SubmissionDTO(
                    f"s{index}",
                    item.id,
                    DeliveryState.ACCEPTED,
                    ItemState.WRONG,
                    str(index),
                    hash_reply(old_reply),
                    f"old{index}",
                )
            )
            self.gateway.remote[str(index)] = RemoteSubmissionDTO(str(index), ItemState.WRONG, None, False)
        await self.batches.create_batch("run", "active")
        await self.items.add_items(
            tuple(
                ItemDTO(
                    f"leased{i}",
                    "run",
                    str(100 + i),
                    "1",
                    "number",
                    "question",
                    ItemState.LEASED,
                    attempt_id=str(100 + i),
                    batch_id="active",
                )
                for i in range(12)
            )
        )


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def scenario(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'state.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
    async with engine.connect() as connection:
        state = Scenario(connection, Gateway())
        await state.runs.create_run(
            RunDTO(
                "run",
                "account",
                "68343",
                RunMode.AUTOPILOT,
                Strategy.THROUGHPUT,
                Selection.EXPLICIT,
                Target.TASKS_COMPLETE,
                Grading.IMMEDIATE,
                RunState.DISPATCHING,
            )
        )
        yield state
    await engine.dispose()


def retry_input(request_id: str = "retry") -> CommitBatchInputDTO:
    return CommitBatchInputDTO(
        "run",
        request_id,
        "retry",
        (
            CommitAnswerDTO("n1", TextAnswerDTO("5")),
            CommitAnswerDTO("n2", TextAnswerDTO("15")),
        ),
        None,
    )


@pytest.mark.anyio
async def test_retry_keeps_run_leases_history_and_current_results(scenario):
    await scenario.seed_wrong_numbers()
    result = await scenario.commit.execute(retry_input())
    assert [receipt.submission_id for receipt in result.receipts] == ["301", "302"]
    assert scenario.gateway.sent == [("201", NumberReplyDTO("5")), ("202", NumberReplyDTO("15"))]
    assert await scenario.commit.execute(retry_input()) == result
    assert len(scenario.gateway.sent) == 2
    assert len(scenario.gateway.attempts) == 2
    assert await scenario.batches.active_batch("account", "run") == "active"
    assert len(await scenario.items.list_items("account", "run", frozenset({ItemState.LEASED}))) == 12
    collected = await scenario.collect.execute(CollectResultsInputDTO("run"))
    assert collected.counts.correct == 2
    assert collected.counts.wrong == 0
    assert len(await scenario.submissions.list_submissions("account", "run")) == 2
    rows = (await scenario.connection.execute(sa.select(operations))).mappings().all()
    assert len(rows) == 4
    assert rows[0]["request_payload"]["reply"] == {"kind": "text", "text": "5"}
    assert rows[2]["request_payload"]["reply"] == {"kind": "number", "number": "5"}


@pytest.mark.anyio
async def test_lost_retry_response_is_reconciled_without_resubmitting(scenario):
    await scenario.seed_wrong_numbers()
    scenario.gateway.fail_after_send = True
    with pytest.raises(ExternalServiceError, match="lost response"):
        await scenario.commit.execute(retry_input())
    await scenario.collect.execute(CollectResultsInputDTO("run"))
    assert (await scenario.items.get_item("account", "run", "n1")).state is ItemState.OUTCOME_UNKNOWN
    with pytest.raises(ValidationError):
        await scenario.commit.execute(retry_input("retry-again"))
    restarted = Scenario(scenario.connection, scenario.gateway)
    result = await restarted.control.execute(RunControlInputDTO("run", "resume", "resume"))
    assert result.reconciled == ("n1",)
    assert not result.recovery_required
    assert len(scenario.gateway.sent) == 1
    assert len(scenario.gateway.attempts) == 1
    collected = await restarted.collect.execute(CollectResultsInputDTO("run"))
    assert collected.counts.correct == 1
    assert collected.counts.wrong == 1
    assert (await restarted.submissions.list_submissions("account", "run"))[0].upstream_id == "301"


@pytest.mark.anyio
async def test_retry_checks_upstream_before_creating_any_attempt(scenario):
    await scenario.seed_wrong_numbers()
    scenario.gateway.remote["2"] = RemoteSubmissionDTO("2", ItemState.CORRECT, None, False)
    with pytest.raises(ValidationError, match="confirmed wrong"):
        await scenario.commit.execute(retry_input())
    assert scenario.gateway.attempts == scenario.gateway.sent == []


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["matching", "table", "fill-blanks"])
async def test_include_then_prepare_and_recover_structured_batch(scenario, kind):
    datasets = {
        "matching": {"pairs": [{"first": "A", "second": "B"}]},
        "table": {"rows": ["A"], "columns": ["B"], "is_checkbox": True},
        "fill-blanks": {"components": [{"type": "input", "text": ""}]},
    }
    scenario.gateway.quiz_data = datasets
    task = TaskDTO("501", "1", "68343", kind, "question", None, False, False)
    scenario.gateway.tasks = (
        task,
        replace(task, step_id="502", is_passed=True),
        replace(task, step_id="503", kind="text"),
    )
    request = RunControlInputDTO("run", "include", "include", ("501", "502", "503"))
    included = await scenario.control.execute(request)
    assert len(included.added_items) == 1
    assert await scenario.control.execute(request) == included
    assert scenario.gateway.attempts == []
    assert not (await scenario.control.execute(replace(request, request_id="include-again"))).added_items
    batch = await scenario.next.execute(NextBatchInputDTO("run", "next"))
    assert isinstance(batch, BatchDTO)
    assert BatchOutput.from_dto(batch).items[0].quiz_data == datasets[kind]
    restarted = Scenario(scenario.connection, scenario.gateway)
    cached = await restarted.next.execute(NextBatchInputDTO("run", "next"))
    recovered = await restarted.next.execute(NextBatchInputDTO("run", "next-recovered"))
    assert cached == batch
    assert isinstance(recovered, BatchDTO)
    assert recovered.recovered
    assert recovered.items[0].quiz_data == datasets[kind]
    assert scenario.gateway.attempts == ["501"]


def code_task() -> TaskDTO:
    return TaskDTO(
        "2016603",
        "1",
        "68343",
        "code",
        "Сортируй как хочешь",
        None,
        False,
        False,
        code_languages=("python3.12",),
        code_templates={"python3.12": "athletes = [('Дима', 10, 130, 35)]\n\n# решение\n"},
    )


@pytest.mark.anyio
@pytest.mark.parametrize("entry", ["start", "include"])
async def test_code_templates_survive_storage_restart_and_repeated_requests(scenario, entry):
    task = code_task()
    scenario.gateway.tasks = (task,)
    if entry == "start":
        start = StartRun(
            scenario.gateway,
            cast("Any", scenario.gateway),
            scenario.gateway,
            scenario.runs,
            scenario.items,
            scenario.batches,
            scenario.idempotency,
            AdapterRegistry(),
        )
        request = StartRunInputDTO(
            "68343",
            RunMode.AUTOPILOT,
            Strategy.THROUGHPUT,
            Target.TASKS_COMPLETE,
            Selection.EXPLICIT,
            Grading.IMMEDIATE,
            (task.step_id,),
            None,
            "start-code",
        )
        started = await start.execute(request)
        assert await start.execute(request) == started
        run_id, batch = started.run_id, started.first_batch
    else:
        await scenario.control.execute(RunControlInputDTO("run", "include", "include-code", (task.step_id,)))
        run_id = "run"
        batch = await scenario.next.execute(NextBatchInputDTO(run_id, "next-code"))
    assert isinstance(batch, BatchDTO)
    assert BatchOutput.from_dto(batch).items[0].code_templates == task.code_templates
    stored = (await scenario.items.list_items("account", run_id))[0]
    assert stored.code_templates == task.code_templates
    restarted = Scenario(scenario.connection, scenario.gateway)
    recovered = await restarted.next.execute(NextBatchInputDTO(run_id, "recover-code"))
    assert isinstance(recovered, BatchDTO)
    assert recovered.recovered
    assert recovered.items == batch.items
    assert await restarted.next.execute(NextBatchInputDTO(run_id, "recover-code")) == recovered
    assert scenario.gateway.attempts == [task.step_id]
    assert not scenario.gateway.template_reads


@pytest.mark.anyio
async def test_legacy_run_read_and_cached_batch_fetch_templates_without_new_attempts(scenario):
    task = code_task()
    scenario.gateway.tasks = (task,)
    await scenario.batches.create_batch("run", "active-code")
    item = ItemDTO(
        "code",
        "run",
        task.step_id,
        "1",
        "code",
        task.question,
        ItemState.LEASED,
        code_languages=task.code_languages,
        attempt_id="old-attempt",
        batch_id="active-code",
    )
    await scenario.items.add_items((item,))
    # Reproduce the persisted JSON shape from the old server, with no template field.
    payload = (await scenario.connection.execute(sa.select(run_items.c.payload))).scalar_one()
    payload.pop("code_templates")
    await scenario.connection.execute(sa.update(run_items).values(payload=payload))
    await scenario.connection.commit()
    old_batch = BatchDTO(
        "active-code",
        (
            ChoiceTaskDTO(
                item.id,
                task.step_id,
                "old-attempt",
                task.question,
                (),
                False,
                None,
                "code",
                task.code_languages,
            ),
        ),
        False,
    )
    await scenario.idempotency.save_next("account", "cached-code", hash_text("run"), old_batch)
    result = (await scenario.connection.execute(sa.select(idempotency.c.result))).scalar_one()
    result["value"]["items"][0].pop("code_templates")
    await scenario.connection.execute(sa.update(idempotency).values(result=result))
    await scenario.connection.commit()
    read = ReadRunData(
        scenario.gateway,
        scenario.runs,
        scenario.items,
        cast("Any", scenario.submissions),
        cast("Any", scenario.gateway),
    )
    resource = await read.execute(ReadInputDTO("run", "code", None))
    assert ItemResourceOutput.from_dto(resource.item).code_templates == task.code_templates
    root = await read.execute(ReadInputDTO("run", None, None))
    assert root.run.items[0].code_templates == task.code_templates
    for request_id in ("cached-code", "recover-code"):
        batch = await scenario.next.execute(NextBatchInputDTO("run", request_id))
        assert batch.items[0].code_templates == task.code_templates
        assert batch.items[0].attempt_id == "old-attempt"
    assert await scenario.items.get_item("account", "run", "code") == item
    assert scenario.gateway.attempts == scenario.gateway.sent == []
    assert scenario.gateway.template_reads == [(task.step_id,)] * 4
