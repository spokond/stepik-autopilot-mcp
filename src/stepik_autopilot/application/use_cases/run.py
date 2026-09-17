import hashlib
from dataclasses import replace
from uuid import uuid4

from stepik_autopilot.application.code_templates import CodeTemplates
from stepik_autopilot.application.dto import (
    BatchCommitDTO,
    BatchDTO,
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
from stepik_autopilot.application.replies import ReplyDTO, hash_reply
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
    ValidationError,
)
from stepik_autopilot.core.task_adapters import AdapterRegistry


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def limit(strategy: Strategy) -> int:
    return 12 if strategy is Strategy.THROUGHPUT else 6 if strategy is Strategy.ECONOMY else 8


class PlanCourse:
    def __init__(self, courses: StepikCourseGateway, adapters: AdapterRegistry) -> None:
        self._courses, self._adapters = courses, adapters

    async def execute(self, input: PlanInputDTO) -> PlanDTO:
        content = await self._courses.content(input.course_id, input.explicit_step_ids, input.section_numbers)
        tasks = content.tasks
        types = tuple(
            TaskTypeCountDTO(kind, sum(task.kind == kind for task in tasks))
            for kind in sorted({task.kind for task in tasks if not self._adapters.is_theory(task.kind)})
        )
        excluded = sum(self._adapters.is_theory(task.kind) for task in tasks)
        unknown = sum(not self._adapters.is_theory(task.kind) and task.is_passed is None for task in tasks)
        passed = sum(not self._adapters.is_theory(task.kind) and task.is_passed is True for task in tasks)
        unsupported = sum(
            not self._adapters.is_theory(task.kind)
            and task.is_passed is False
            and not self._adapters.is_supported(task.kind)
            for task in tasks
        )
        available = sum(not self._adapters.is_theory(task.kind) and task.is_passed is False for task in tasks)
        return PlanDTO(
            input.course_id,
            input.selection,
            PlanCountsDTO(available, passed, unknown, excluded, unsupported),
            types,
            content.sections,
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
        self._templates = CodeTemplates(courses)

    async def execute(self, input: StartRunInputDTO) -> RunStartedDTO:
        if input.mode is RunMode.INSPECT:
            msg = "inspect is read-only; use stepik_plan"
            raise ValidationError(msg)
        account = await self._accounts.current_account()
        payload = ":".join(
            (
                input.course_id,
                input.mode,
                input.strategy,
                input.target,
                input.selection,
                input.grading,
                str(input.explicit_step_ids),
            )
        )
        if input.section_numbers is not None:
            payload = f"{payload}:{input.section_numbers}"
        digest = hash_text(payload)
        cached = await self._idempotency.get_start(account, input.request_id, digest)
        if cached is not None:
            return replace(cached, first_batch=await self._templates.batch(cached.first_batch))
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
        tasks = (await self._courses.content(input.course_id, input.explicit_step_ids, input.section_numbers)).tasks
        eligible = tuple(
            task
            for task in tasks
            if self._adapters.is_supported(task.kind)
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
                code_languages=task.code_languages,
                code_templates=task.code_templates,
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
            attempt = await self._attempts.prepare_attempt(
                TaskDTO(
                    item.step_id,
                    item.assignment_id,
                    run.course_id,
                    item.kind,
                    item.question,
                    None,
                    False,
                    False,
                    code_languages=item.code_languages,
                    code_templates=item.code_templates,
                )
            )
            leased = replace(
                item,
                state=ItemState.LEASED,
                choice_dataset=attempt.dataset,
                quiz_data=attempt.quiz_data,
                code_languages=attempt.code_languages,
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
                    attempt.dataset.options if attempt.dataset else (),
                    attempt.dataset.is_multiple_choice if attempt.dataset else False,
                    attempt.expires_at,
                    item.kind,
                    attempt.code_languages,
                    attempt.quiz_data,
                    item.code_templates,
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
        courses: StepikCourseGateway,
    ) -> None:
        self._accounts = accounts
        self._attempts = attempts
        self._runs = runs
        self._items = items
        self._batches = batches
        self._idempotency = idempotency
        self._adapters = adapters
        self._templates = CodeTemplates(courses)

    async def execute(self, input: NextBatchInputDTO) -> BatchDTO | NextBatchStateDTO:
        account = await self._accounts.current_account()
        digest = hash_text(input.run_id)
        cached = await self._idempotency.get_next(account, input.request_id, digest)
        if cached is not None:
            return await self._templates.batch(cached) if isinstance(cached, BatchDTO) else cached
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
                leased = await self._templates.enrich(leased)
                tasks = tuple(
                    ChoiceTaskDTO(
                        item.id,
                        item.step_id,
                        item.attempt_id or "",
                        item.question,
                        item.choice_dataset.options if item.choice_dataset else (),
                        item.choice_dataset.is_multiple_choice if item.choice_dataset else False,
                        item.expires_at,
                        item.kind,
                        item.code_languages,
                        item.quiz_data,
                        item.code_templates,
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
        chosen = await self._templates.enrich(ready[: limit(run.strategy)])
        batch_id = f"batch_{uuid4().hex}"
        await self._batches.create_batch(run.id, batch_id)
        output: list[ChoiceTaskDTO] = []
        for item in chosen:
            task = TaskDTO(
                step_id=item.step_id,
                assignment_id=item.assignment_id,
                course_id=run.course_id,
                kind=item.kind,
                question=item.question,
                progress_id=None,
                is_passed=False,
                failed=False,
                code_languages=item.code_languages,
                code_templates=item.code_templates,
            )
            attempt = await self._attempts.prepare_attempt(task)
            leased = replace(
                item,
                state=ItemState.LEASED,
                choice_dataset=attempt.dataset,
                quiz_data=attempt.quiz_data,
                code_languages=attempt.code_languages,
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
                    attempt.dataset.options if attempt.dataset else (),
                    attempt.dataset.is_multiple_choice if attempt.dataset else False,
                    attempt.expires_at,
                    item.kind,
                    attempt.code_languages,
                    attempt.quiz_data,
                    item.code_templates,
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
        attempts: StepikAttemptGateway,
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
        self._attempts = attempts

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
        if input.action not in {"save", "submit", "retry"}:
            msg = "action must be save, submit or retry"
            raise ValidationError(msg)
        states = {ItemState.WRONG} if input.action == "retry" else {ItemState.LEASED, ItemState.DRAFT}
        available = {item.id: item for item in await self._items.list_items(account, run.id, frozenset(states))}
        if (
            not input.answers
            or len({answer.item_id for answer in input.answers}) != len(input.answers)
            or not all(answer.item_id in available for answer in input.answers)
        ):
            msg = "answers must contain each available item at most once"
            raise ValidationError(msg)
        previous = {item.item_id: item for item in await self._submissions.list_submissions(account, run.id)}
        selected = tuple(available[answer.item_id] for answer in input.answers)
        if input.action == "retry":
            await self._validate_retry(account, run.id, selected, previous)
        # Validate the complete batch before any attempt or submission is sent.
        replies = {
            answer.item_id: self._adapters.build_reply(
                available[answer.item_id].kind,
                answer.answer,
                available[answer.item_id].choice_dataset,
                available[answer.item_id].code_languages,
                available[answer.item_id].quiz_data,
            )
            for answer in input.answers
        }
        self._validate_submission(input, selected)
        receipts: list[SubmissionReceiptDTO] = []
        for answer in input.answers:
            item = available[answer.item_id]
            reply = replies[item.id]
            if input.action == "save":
                saved = replace(item, state=ItemState.DRAFT, draft_revision=item.draft_revision + 1)
                await self._items.save_item(account, saved)
                receipts.append(SubmissionReceiptDTO(item.id, DeliveryState.QUEUED, None, saved.draft_revision))
                continue
            receipts.append(await self._submit_item(account, run, item, reply, input.action, previous.get(item.id)))
        result = BatchCommitDTO(run.id, tuple(receipts), input.action != "save" and run.grading is Grading.DEFERRED)
        if input.action != "save":
            active = await self._batches.active_batch(account, run.id)
            unfinished = await self._items.list_items(account, run.id, frozenset({ItemState.LEASED, ItemState.DRAFT}))
            if active is not None and not any(item.batch_id == active for item in unfinished):
                await self._batches.close_batch(run.id, active)
        await self._idempotency.save_commit(account, input.request_id, digest, result)
        return result

    @staticmethod
    def _validate_submission(input: CommitBatchInputDTO, selected: tuple[ItemDTO, ...]) -> None:
        for item in selected:
            if input.action == "submit" and item.attempt_id is None:
                msg = "submit requires a prepared attempt"
                raise ValidationError(msg)
            if (
                input.action == "submit"
                and item.state is ItemState.DRAFT
                and input.draft_revision != item.draft_revision
            ):
                msg = "draft_revision does not match the saved item"
                raise ValidationError(msg)

    async def _submit_item(
        self,
        account: str,
        run: RunDTO,
        item: ItemDTO,
        reply: ReplyDTO,
        action: str,
        previous: SubmissionDTO | None,
    ) -> SubmissionReceiptDTO:
        if action == "retry":
            attempt = await self._attempts.prepare_attempt(
                TaskDTO(item.step_id, item.assignment_id, run.course_id, item.kind, item.question, None, False, True)
            )
            item = replace(
                item,
                state=ItemState.LEASED,
                attempt_id=attempt.id,
                expires_at=attempt.expires_at,
                draft_revision=0,
            )
            await self._items.save_item(account, item)
        if item.attempt_id is None:
            msg = "submit requires a prepared attempt"
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
        await record_submission(
            self._submissions,
            SubmissionDTO(
                f"submission_{uuid4().hex}",
                item.id,
                delivery,
                remote.state,
                remote.id,
                reply_hash,
                operation.id,
            ),
            previous,
        )
        await self._items.save_item(account, replace(item, state=remote.state))
        await self._operations.update_operation(operation.id, OperationState.ACCEPTED, remote.id)
        return SubmissionReceiptDTO(item.id, delivery, remote.id or None, None)

    async def _validate_retry(
        self, account: str, run_id: str, selected: tuple[ItemDTO, ...], previous: dict[str, SubmissionDTO]
    ) -> None:
        if any(item.kind != "number" for item in selected):
            msg = "retry currently supports only confirmed wrong number items"
            raise ValidationError(msg)
        ids = {item.id for item in selected}
        unresolved = await self._operations.unresolved_operations(account, run_id)
        if any(operation.item_id in ids for operation in unresolved):
            msg = "resume and reconcile unresolved submissions before retrying"
            raise RunStateError(msg)
        upstream_ids = tuple(
            submission.upstream_id
            for item_id, submission in previous.items()
            if item_id in ids and submission.upstream_id is not None
        )
        if len(upstream_ids) != len(selected):
            msg = "retry requires a recorded submission for every item"
            raise ValidationError(msg)
        remote = {submission.id: submission for submission in await self._gateway.submissions(upstream_ids)}
        if any(
            (result := remote.get(upstream_id)) is None or result.state is not ItemState.WRONG or result.review_required
            for upstream_id in upstream_ids
        ):
            msg = "retry requires a confirmed wrong Stepik result for every item"
            raise ValidationError(msg)


async def record_submission(
    repository: SubmissionRepository, submission: SubmissionDTO, previous: SubmissionDTO | None
) -> None:
    # One current submission per item; operation records retain the original payloads.
    if previous is None:
        await repository.create_submission(submission)
    else:
        await repository.update_submission(replace(submission, id=previous.id))


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
            item = await self._items.get_item(account, input.run_id, submission.item_id)
            if item is not None and item.state in {
                ItemState.READY,
                ItemState.LEASED,
                ItemState.DRAFT,
                ItemState.SENDING,
                ItemState.OUTCOME_UNKNOWN,
            }:
                # An old result must not overwrite a prepared or unresolved retry.
                continue
            value = remote.get(submission.upstream_id or "")
            if value is None:
                continue
            state = ItemState.REVIEW_REQUIRED if value.review_required else value.state
            await self._submissions.update_submission(replace(submission, grading=state))
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
        submissions: SubmissionRepository,
        courses: StepikCourseGateway,
    ) -> None:
        self._accounts, self._runs, self._items, self._operations, self._gateway, self._idempotency = (
            accounts,
            runs,
            items,
            operations,
            gateway,
            idempotency,
        )
        self._submissions = submissions
        self._courses = courses

    async def execute(self, input: RunControlInputDTO) -> RunControlDTO:
        account = await self._accounts.current_account()
        digest = hash_text(f"{input.run_id}:{input.action}")
        if input.explicit_step_ids is not None:
            digest = hash_text(f"{input.run_id}:{input.action}:{input.explicit_step_ids}")
        cached = await self._idempotency.get_control(account, input.request_id, digest)
        if cached is not None:
            return cached
        run = await self._runs.get_run(account, input.run_id)
        if run is None:
            msg = "run not found"
            raise NotFoundError(msg)
        if input.action == "include":
            result = await self._include(account, run, input.explicit_step_ids)
            await self._idempotency.save_control(account, input.request_id, digest, result)
            return result
        if input.explicit_step_ids is not None:
            msg = "explicit_step_ids are only valid for action=include"
            raise ValidationError(msg)
        states = {"pause": RunState.PAUSED, "resume": RunState.DISPATCHING, "cancel": RunState.CANCELLED}
        if input.action not in states:
            msg = "action must be pause, resume or cancel"
            raise ValidationError(msg)
        unresolved = await self._items.list_items(
            account, run.id, frozenset({ItemState.SENDING, ItemState.OUTCOME_UNKNOWN})
        )
        reconciled: list[str] = []
        if input.action == "resume":
            previous = {item.item_id: item for item in await self._submissions.list_submissions(account, run.id)}
            for operation in await self._operations.unresolved_operations(account, run.id):
                remote = await self._gateway.find_submission(operation.attempt_id, operation.reply_hash)
                if remote is None:
                    continue
                state = ItemState.REVIEW_REQUIRED if remote.review_required else remote.state
                await record_submission(
                    self._submissions,
                    SubmissionDTO(
                        f"submission_{uuid4().hex}",
                        operation.item_id,
                        DeliveryState.ACCEPTED,
                        state,
                        remote.id,
                        operation.reply_hash,
                        operation.id,
                    ),
                    previous.get(operation.item_id),
                )
                item = await self._items.get_item(account, run.id, operation.item_id)
                if item is not None:
                    await self._items.save_item(account, replace(item, state=state))
                await self._operations.update_operation(operation.id, OperationState.RECONCILED, remote.id)
                reconciled.append(operation.item_id)
        state = states[input.action]
        await self._runs.set_run_state(account, run.id, state)
        recovery = tuple(item.id for item in unresolved if item.id not in reconciled)
        result = RunControlDTO(run.id, state, recovery if input.action == "resume" else (), tuple(reconciled))
        await self._idempotency.save_control(account, input.request_id, digest, result)
        return result

    async def _include(self, account: str, run: RunDTO, step_ids: tuple[str, ...] | None) -> RunControlDTO:
        if not step_ids or len(step_ids) != len(set(step_ids)):
            msg = "include requires unique explicit_step_ids"
            raise ValidationError(msg)
        if run.state in {RunState.CANCELLED, RunState.FINISHED}:
            msg = f"cannot add items to a {run.state.value} run"
            raise RunStateError(msg)
        content = await self._courses.content(run.course_id, explicit_step_ids=step_ids)
        existing = {item.step_id for item in await self._items.list_items(account, run.id)}
        added: list[ItemDTO] = []
        for task in content.tasks:
            if (
                task.step_id in step_ids
                and task.step_id not in existing
                and AdapterRegistry.is_supported(task.kind)
                and task.is_passed is False
            ):
                added.append(
                    ItemDTO(
                        f"item_{uuid4().hex}",
                        run.id,
                        task.step_id,
                        task.assignment_id,
                        task.kind,
                        task.question,
                        ItemState.READY,
                        code_languages=task.code_languages,
                        code_templates=task.code_templates,
                    )
                )
                existing.add(task.step_id)
        await self._items.add_items(tuple(added))
        return RunControlDTO(run.id, run.state, (), (), tuple(item.id for item in added))


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
