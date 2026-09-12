import hashlib
import json
from dataclasses import replace
from uuid import uuid4

from stepik_autopilot.application.dto import (
    BatchCommitDTO,
    BatchDTO,
    ChoiceReplyDTO,
    ChoiceTaskDTO,
    CollectResultsInputDTO,
    CommitBatchInputDTO,
    ItemDTO,
    NextBatchInputDTO,
    NextBatchStateDTO,
    OperationDTO,
    PlanCountsDTO,
    PlanDTO,
    PlanInputDTO,
    ResultsCountsDTO,
    ResultsDTO,
    RunControlDTO,
    RunControlInputDTO,
    RunDTO,
    RunStartedDTO,
    RunStatusDTO,
    RunStatusInputDTO,
    StartRunInputDTO,
    SubmissionDTO,
    SubmissionReceiptDTO,
    TaskDTO,
    TaskTypeCountDTO,
)
from stepik_autopilot.application.protocols import (
    BatchRepository,
    IdempotencyRepository,
    ItemRepository,
    OperationRepository,
    RunRepository,
    StepikAccountGateway,
    StepikAttemptGateway,
    StepikCourseGateway,
    StepikSubmissionGateway,
    SubmissionRepository,
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
)
from stepik_autopilot.core.exceptions import (
    ExternalServiceError,
    NotFoundError,
    RunStateError,
    UnsupportedTaskError,
    ValidationError,
)
from stepik_autopilot.core.task_adapters import AdapterRegistry


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hash_reply(reply: ChoiceReplyDTO) -> str:
    payload = {"choices": list(reply.choices)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def limit(strategy: Strategy) -> int:
    return 12 if strategy is Strategy.THROUGHPUT else 6 if strategy is Strategy.ECONOMY else 8


class PlanCourse:
    def __init__(self, courses: StepikCourseGateway, adapters: AdapterRegistry) -> None:
        self._courses, self._adapters = courses, adapters

    async def execute(self, input: PlanInputDTO) -> PlanDTO:
        tasks = await self._courses.tasks(input.course_id, input.explicit_step_ids)
        types = tuple(
            TaskTypeCountDTO(kind, sum(task.kind == kind for task in tasks))
            for kind in sorted({task.kind for task in tasks})
        )
        excluded = sum(self._adapters.is_theory(task.kind) for task in tasks)
        unknown = sum(not self._adapters.is_theory(task.kind) and task.is_passed is None for task in tasks)
        passed = sum(not self._adapters.is_theory(task.kind) and task.is_passed is True for task in tasks)
        unsupported = sum(
            not self._adapters.is_theory(task.kind) and task.is_passed is False and task.kind != "choice"
            for task in tasks
        )
        available = sum(task.kind == "choice" and task.is_passed is False for task in tasks)
        return PlanDTO(
            input.course_id, input.selection, PlanCountsDTO(available, passed, unknown, excluded, unsupported), types
        )


class StartRun:
    def __init__(
        self,
        accounts: StepikAccountGateway,
        courses: StepikCourseGateway,
        attempts: StepikAttemptGateway,
        runs: RunRepository,
        items: ItemRepository,
        batches: BatchRepository,
        idempotency: IdempotencyRepository,
        adapters: AdapterRegistry,
    ) -> None:
        (
            self._accounts,
            self._courses,
            self._attempts,
            self._runs,
            self._items,
            self._batches,
            self._idempotency,
            self._adapters,
        ) = accounts, courses, attempts, runs, items, batches, idempotency, adapters

    async def execute(self, input: StartRunInputDTO) -> RunStartedDTO:
        if input.mode is RunMode.INSPECT:
            msg = "inspect is read-only; use stepik_plan"
            raise ValidationError(msg)
        account = await self._accounts.current_account()
        digest = hash_text(
            f"{input.course_id}:{input.mode}:{input.strategy}:{input.target}:{input.selection}:{input.grading}:{input.explicit_step_ids}"
        )
        cached = await self._idempotency.get_start(account, input.request_id, digest)
        if cached is not None:
            return cached
        run = RunDTO(
            f"run_{uuid4().hex}",
            account,
            input.course_id,
            input.mode,
            input.strategy,
            input.selection,
            input.target,
            input.grading,
            RunState.DISPATCHING,
        )
        await self._runs.create_run(run)
        tasks = await self._courses.tasks(input.course_id, input.explicit_step_ids)
        eligible = tuple(
            task
            for task in tasks
            if task.kind == "choice"
            and task.is_passed is False
            and (input.selection is not Selection.FAILED or task.failed)
        )
        items = tuple(
            ItemDTO(
                f"item_{uuid4().hex}",
                run.id,
                task.step_id,
                task.assignment_id,
                task.kind,
                task.question,
                ItemState.READY,
            )
            for task in eligible
        )
        await self._items.add_items(items)
        batch = await self._issue(account, run, items)
        result = RunStartedDTO(run.id, run.state, batch)
        await self._idempotency.save_start(account, input.request_id, digest, result)
        return result

    async def _issue(self, account: str, run: RunDTO, ready: tuple[ItemDTO, ...]) -> BatchDTO:
        chosen = ready[: limit(run.strategy)]
        batch_id = f"batch_{uuid4().hex}"
        await self._batches.create_batch(run.id, batch_id)
        output: list[ChoiceTaskDTO] = []
        for item in chosen:
            if item.kind != "choice":
                msg = f"unsupported task {item.kind}"
                raise UnsupportedTaskError(msg)
            attempt = await self._attempts.prepare_attempt(
                TaskDTO(item.step_id, item.assignment_id, run.course_id, item.kind, item.question, None, False, False)
            )
            leased = replace(
                item,
                state=ItemState.LEASED,
                choice_dataset=attempt.dataset,
                attempt_id=attempt.id,
                expires_at=attempt.expires_at,
                batch_id=batch_id,
            )
            await self._items.save_item(account, leased)
            output.append(
                ChoiceTaskDTO(
                    item.id,
                    item.step_id,
                    attempt.id,
                    item.question,
                    attempt.dataset.options,
                    attempt.dataset.is_multiple_choice,
                    attempt.expires_at,
                )
            )
        return BatchDTO(batch_id, tuple(output), len(ready) > len(chosen))


class NextBatch:
    def __init__(
        self,
        accounts: StepikAccountGateway,
        attempts: StepikAttemptGateway,
        runs: RunRepository,
        items: ItemRepository,
        batches: BatchRepository,
        idempotency: IdempotencyRepository,
        adapters: AdapterRegistry,
    ) -> None:
        self._accounts = accounts
        self._attempts = attempts
        self._runs = runs
        self._items = items
        self._batches = batches
        self._idempotency = idempotency
        self._adapters = adapters

    async def execute(self, input: NextBatchInputDTO) -> BatchDTO | NextBatchStateDTO:
        account = await self._accounts.current_account()
        digest = hash_text(input.run_id)
        cached = await self._idempotency.get_next(account, input.request_id, digest)
        if cached is not None:
            return cached
        run = await self._runs.get_run(account, input.run_id)
        if run is None:
            msg = "run not found"
            raise NotFoundError(msg)
        if run.state in {RunState.PAUSED, RunState.CANCELLED, RunState.FINISHED}:
            result = NextBatchStateDTO(run.id, run.state, True, False, run.state is RunState.FINISHED)
            await self._idempotency.save_next(account, input.request_id, digest, result)
            return result
        active = await self._batches.active_batch(account, run.id)
        if active is not None:
            leased = tuple(
                item
                for item in await self._items.list_items(account, run.id, frozenset({ItemState.LEASED}))
                if item.batch_id == active
            )
            if leased:
                tasks = tuple(
                    ChoiceTaskDTO(
                        item.id,
                        item.step_id,
                        item.attempt_id or "",
                        item.question,
                        item.choice_dataset.options if item.choice_dataset else (),
                        item.choice_dataset.is_multiple_choice if item.choice_dataset else False,
                        item.expires_at,
                    )
                    for item in leased
                )
                result = BatchDTO(active, tasks, True, True)
                await self._idempotency.save_next(account, input.request_id, digest, result)
                return result
        ready = await self._items.list_items(account, run.id, frozenset({ItemState.READY}))
        if not ready:
            pending = await self._items.list_items(
                account,
                run.id,
                frozenset(
                    {
                        ItemState.QUEUED,
                        ItemState.SENDING,
                        ItemState.ACCEPTED,
                        ItemState.EVALUATION,
                        ItemState.OUTCOME_UNKNOWN,
                    }
                ),
            )
            result = NextBatchStateDTO(run.id, None, False, bool(pending), not pending)
            await self._idempotency.save_next(account, input.request_id, digest, result)
            return result
        result = await self._issue(account, run, ready)
        await self._idempotency.save_next(account, input.request_id, digest, result)
        return result

    async def _issue(self, account: str, run: RunDTO, ready: tuple[ItemDTO, ...]) -> BatchDTO:
        chosen = ready[: limit(run.strategy)]
        batch_id = f"batch_{uuid4().hex}"
        await self._batches.create_batch(run.id, batch_id)
        output: list[ChoiceTaskDTO] = []
        for item in chosen:
            if item.kind != "choice":
                msg = f"unsupported task {item.kind}"
                raise UnsupportedTaskError(msg)
            task = TaskDTO(
                step_id=item.step_id,
                assignment_id=item.assignment_id,
                course_id=run.course_id,
                kind=item.kind,
                question=item.question,
                progress_id=None,
                is_passed=False,
                failed=False,
            )
            attempt = await self._attempts.prepare_attempt(task)
            leased = replace(
                item,
                state=ItemState.LEASED,
                choice_dataset=attempt.dataset,
                attempt_id=attempt.id,
                expires_at=attempt.expires_at,
                batch_id=batch_id,
            )
            await self._items.save_item(account, leased)
            output.append(
                ChoiceTaskDTO(
                    item.id,
                    item.step_id,
                    attempt.id,
                    item.question,
                    attempt.dataset.options,
                    attempt.dataset.is_multiple_choice,
                    attempt.expires_at,
                )
            )
        return BatchDTO(batch_id, tuple(output), len(ready) > len(chosen))


class CommitBatch:
    def __init__(
        self,
        accounts: StepikAccountGateway,
        submissions_gateway: StepikSubmissionGateway,
        runs: RunRepository,
        items: ItemRepository,
        submissions: SubmissionRepository,
        batches: BatchRepository,
        operations: OperationRepository,
        adapters: AdapterRegistry,
        idempotency: IdempotencyRepository,
    ) -> None:
        (
            self._accounts,
            self._gateway,
            self._runs,
            self._items,
            self._submissions,
            self._batches,
            self._operations,
            self._adapters,
            self._idempotency,
        ) = accounts, submissions_gateway, runs, items, submissions, batches, operations, adapters, idempotency

    async def execute(self, input: CommitBatchInputDTO) -> BatchCommitDTO:
        account = await self._accounts.current_account()
        digest = hash_text(f"{input.run_id}:{input.action}:{input.answers}:{input.draft_revision}")
        cached = await self._idempotency.get_commit(account, input.request_id, digest)
        if cached is not None:
            return cached
        run = await self._runs.get_run(account, input.run_id)
        if run is None:
            msg = "run not found"
            raise NotFoundError(msg)
        if run.state in {RunState.PAUSED, RunState.CANCELLED, RunState.FINISHED}:
            msg = f"cannot commit a {run.state.value} run"
            raise RunStateError(msg)
        available = {
            item.id: item
            for item in await self._items.list_items(account, run.id, frozenset({ItemState.LEASED, ItemState.DRAFT}))
        }
        if (
            not input.answers
            or len({answer.item_id for answer in input.answers}) != len(input.answers)
            or not all(answer.item_id in available for answer in input.answers)
        ):
            msg = "answers must contain each available item at most once"
            raise ValidationError(msg)
        receipts: list[SubmissionReceiptDTO] = []
        for answer in input.answers:
            item = available[answer.item_id]
            if item.choice_dataset is None:
                msg = "item is not a prepared choice task"
                raise UnsupportedTaskError(msg)
            reply = self._adapters.choice(item.kind).build_reply(answer.answer, item.choice_dataset)
            if input.action == "save":
                saved = replace(item, state=ItemState.DRAFT, draft_revision=item.draft_revision + 1)
                await self._items.save_item(account, saved)
                receipts.append(SubmissionReceiptDTO(item.id, DeliveryState.QUEUED, None, saved.draft_revision))
                continue
            if input.action != "submit" or item.attempt_id is None:
                msg = "action must be save or submit"
                raise ValidationError(msg)
            if item.state is ItemState.DRAFT and input.draft_revision != item.draft_revision:
                msg = "draft_revision does not match the saved item"
                raise ValidationError(msg)
            reply_hash = hash_reply(reply)
            operation = OperationDTO(
                id=f"operation_{uuid4().hex}",
                account_id=account,
                item_id=item.id,
                attempt_id=item.attempt_id,
                reply=reply,
                state=OperationState.PREPARED,
                reply_hash=reply_hash,
            )
            await self._operations.create_operation(operation)
            await self._operations.update_operation(operation.id, OperationState.SENDING)
            await self._items.save_item(account, replace(item, state=ItemState.SENDING))
            try:
                remote = await self._gateway.submit(item.attempt_id, reply)
            except ExternalServiceError:
                await self._operations.update_operation(operation.id, OperationState.OUTCOME_UNKNOWN)
                await self._items.save_item(account, replace(item, state=ItemState.OUTCOME_UNKNOWN))
                raise
            delivery = DeliveryState.ACCEPTED if remote.id else DeliveryState.OUTCOME_UNKNOWN
            await self._operations.update_operation(operation.id, OperationState.ACCEPTED, remote.id)
            await self._submissions.create_submission(
                SubmissionDTO(
                    f"submission_{uuid4().hex}",
                    item.id,
                    delivery,
                    remote.state,
                    remote.id,
                    reply_hash,
                    operation.id,
                )
            )
            await self._items.save_item(account, replace(item, state=remote.state))
            receipts.append(SubmissionReceiptDTO(item.id, delivery, remote.id or None, None))
        result = BatchCommitDTO(run.id, tuple(receipts), input.action == "submit" and run.grading is Grading.DEFERRED)
        if input.action == "submit":
            active = await self._batches.active_batch(account, run.id)
            if active is not None:
                await self._batches.close_batch(run.id, active)
        await self._idempotency.save_commit(account, input.request_id, digest, result)
        return result


class CollectResults:
    def __init__(
        self,
        accounts: StepikAccountGateway,
        gateway: StepikSubmissionGateway,
        items: ItemRepository,
        submissions: SubmissionRepository,
    ) -> None:
        self._accounts, self._gateway, self._items, self._submissions = accounts, gateway, items, submissions

    async def execute(self, input: CollectResultsInputDTO) -> ResultsDTO:
        account = await self._accounts.current_account()
        saved = await self._submissions.list_submissions(account, input.run_id)
        remote = {
            item.id: item
            for item in await self._gateway.submissions(
                tuple(item.upstream_id for item in saved if item.upstream_id is not None)
            )
        }
        correct = wrong = pending = review = 0
        for submission in saved:
            value = remote.get(submission.upstream_id or "")
            if value is None:
                continue
            state = ItemState.REVIEW_REQUIRED if value.review_required else value.state
            await self._submissions.update_submission(replace(submission, grading=state))
            item = await self._items.get_item(account, input.run_id, submission.item_id)
            if item is not None:
                await self._items.save_item(account, replace(item, state=state))
            correct += state is ItemState.CORRECT
            wrong += state is ItemState.WRONG
            pending += state is ItemState.EVALUATION
            review += state is ItemState.REVIEW_REQUIRED
        unknown = sum(
            item.state is ItemState.OUTCOME_UNKNOWN for item in await self._items.list_items(account, input.run_id)
        )
        counts = ResultsCountsDTO(correct, wrong, pending, review, unknown)
        return ResultsDTO(input.run_id, counts)


class ControlRun:
    def __init__(
        self,
        accounts: StepikAccountGateway,
        runs: RunRepository,
        items: ItemRepository,
        operations: OperationRepository,
        gateway: StepikSubmissionGateway,
        idempotency: IdempotencyRepository,
    ) -> None:
        self._accounts, self._runs, self._items, self._operations, self._gateway, self._idempotency = (
            accounts,
            runs,
            items,
            operations,
            gateway,
            idempotency,
        )

    async def execute(self, input: RunControlInputDTO) -> RunControlDTO:
        account = await self._accounts.current_account()
        digest = hash_text(f"{input.run_id}:{input.action}")
        cached = await self._idempotency.get_control(account, input.request_id, digest)
        if cached is not None:
            return cached
        run = await self._runs.get_run(account, input.run_id)
        if run is None:
            msg = "run not found"
            raise NotFoundError(msg)
        states = {"pause": RunState.PAUSED, "resume": RunState.DISPATCHING, "cancel": RunState.CANCELLED}
        if input.action not in states:
            msg = "action must be pause, resume or cancel"
            raise ValidationError(msg)
        unresolved = await self._items.list_items(
            account, run.id, frozenset({ItemState.SENDING, ItemState.OUTCOME_UNKNOWN})
        )
        reconciled: list[str] = []
        if input.action == "resume":
            for operation in await self._operations.unresolved_operations(account, run.id):
                remote = await self._gateway.find_submission(operation.attempt_id, operation.reply_hash)
                if remote is None:
                    continue
                await self._operations.update_operation(operation.id, OperationState.RECONCILED, remote.id)
                item = await self._items.get_item(account, run.id, operation.item_id)
                if item is not None:
                    await self._items.save_item(account, replace(item, state=remote.state))
                reconciled.append(operation.item_id)
        state = states[input.action]
        await self._runs.set_run_state(account, run.id, state)
        recovery = tuple(item.id for item in unresolved if item.id not in reconciled)
        result = RunControlDTO(run.id, state, recovery if input.action == "resume" else (), tuple(reconciled))
        await self._idempotency.save_control(account, input.request_id, digest, result)
        return result


class RunStatus:
    def __init__(
        self,
        accounts: StepikAccountGateway,
        runs: RunRepository,
    ) -> None:
        self._accounts, self._runs = accounts, runs

    async def execute(self, input: RunStatusInputDTO) -> RunStatusDTO:
        account = await self._accounts.current_account()
        run = await self._runs.get_run(account, input.run_id)
        if run is None:
            msg = "run not found"
            raise NotFoundError(msg)
        return RunStatusDTO(run.id, run.state)
