from collections.abc import Mapping

import sqlalchemy as sa

from stepik_autopilot.application.dto import (
    BatchCommitDTO,
    BatchDTO,
    ChoiceTaskDTO,
    NextBatchStateDTO,
    RunControlDTO,
    RunStartedDTO,
    SubmissionReceiptDTO,
)
from stepik_autopilot.core.enums import DeliveryState, RunState
from stepik_autopilot.core.exceptions import ConflictError
from stepik_autopilot.infra.tables import idempotency

from .base import SQLAlchemyRepository


class IdempotencyRepository(SQLAlchemyRepository):
    async def get_start(self, account_id: str, request_id: str, payload_hash: str) -> RunStartedDTO | None:
        value = await self._get(account_id, "run_start", request_id, payload_hash)
        if value is None:
            return None
        return RunStartedDTO(str(value["run_id"]), RunState(str(value["state"])), self._batch(value["first_batch"]))

    async def save_start(self, account_id: str, request_id: str, payload_hash: str, value: RunStartedDTO) -> None:
        await self._save(
            account_id,
            "run_start",
            request_id,
            payload_hash,
            {
                "run_id": value.run_id,
                "state": value.state.value,
                "first_batch": self._batch_value(value.first_batch),
            },
        )

    async def get_next(
        self, account_id: str, request_id: str, payload_hash: str
    ) -> BatchDTO | NextBatchStateDTO | None:
        value = await self._get(account_id, "run_next", request_id, payload_hash)
        if value is None:
            return None
        if value["type"] == "batch":
            return self._batch(value["value"])
        return NextBatchStateDTO(
            run_id=str(value["run_id"]),
            state=RunState(str(value["state"])) if value["state"] is not None else None,
            blocked=bool(value["blocked"]),
            collect_required=bool(value["collect_required"]),
            finished=bool(value["finished"]),
        )

    async def save_next(
        self, account_id: str, request_id: str, payload_hash: str, value: BatchDTO | NextBatchStateDTO
    ) -> None:
        serialized: dict[str, object]
        if isinstance(value, BatchDTO):
            serialized = {"type": "batch", "value": self._batch_value(value)}
        else:
            serialized = {
                "type": "state",
                "run_id": value.run_id,
                "state": value.state.value if value.state else None,
                "blocked": value.blocked,
                "collect_required": value.collect_required,
                "finished": value.finished,
            }
        await self._save(account_id, "run_next", request_id, payload_hash, serialized)

    async def get_commit(self, account_id: str, request_id: str, payload_hash: str) -> BatchCommitDTO | None:
        value = await self._get(account_id, "batch_commit", request_id, payload_hash)
        if value is None:
            return None
        receipts_raw = value["receipts"]
        if not isinstance(receipts_raw, list):
            msg = "stored receipts are malformed"
            raise ConflictError(msg)
        receipts = tuple(self._receipt(receipt) for receipt in receipts_raw)
        return BatchCommitDTO(str(value["run_id"]), receipts, bool(value["collect_required"]))

    async def save_commit(self, account_id: str, request_id: str, payload_hash: str, value: BatchCommitDTO) -> None:
        await self._save(
            account_id,
            "batch_commit",
            request_id,
            payload_hash,
            {
                "run_id": value.run_id,
                "collect_required": value.collect_required,
                "receipts": [self._receipt_value(receipt) for receipt in value.receipts],
            },
        )

    async def get_control(self, account_id: str, request_id: str, payload_hash: str) -> RunControlDTO | None:
        value = await self._get(account_id, "run_control", request_id, payload_hash)
        if value is None:
            return None
        recovery = value["recovery_required"]
        reconciled = value["reconciled"]
        if not isinstance(recovery, list) or not isinstance(reconciled, list):
            msg = "stored control result is malformed"
            raise ConflictError(msg)
        return RunControlDTO(
            str(value["run_id"]),
            RunState(str(value["state"])),
            tuple(str(v) for v in recovery),
            tuple(str(v) for v in reconciled),
        )

    async def save_control(self, account_id: str, request_id: str, payload_hash: str, value: RunControlDTO) -> None:
        await self._save(
            account_id,
            "run_control",
            request_id,
            payload_hash,
            {
                "run_id": value.run_id,
                "state": value.state.value,
                "recovery_required": list(value.recovery_required),
                "reconciled": list(value.reconciled),
            },
        )

    async def _get(self, account_id: str, tool: str, request_id: str, payload_hash: str) -> Mapping[str, object] | None:
        stmt = sa.select(idempotency.c.payload_hash, idempotency.c.result).where(
            idempotency.c.account_id == account_id, idempotency.c.tool == tool, idempotency.c.request_id == request_id
        )
        row = (await self._connection.execute(stmt)).mappings().one_or_none()
        if row is None:
            return None
        if str(row["payload_hash"]) != payload_hash:
            msg = "request_id was already used with another payload"
            raise ConflictError(msg)
        result = row["result"]
        if not isinstance(result, Mapping):
            msg = "stored idempotency result is malformed"
            raise ConflictError(msg)
        return result

    async def _save(
        self, account_id: str, tool: str, request_id: str, payload_hash: str, result: dict[str, object]
    ) -> None:
        stmt = sa.insert(idempotency).values(
            account_id=account_id, tool=tool, request_id=request_id, payload_hash=payload_hash, result=result
        )
        await self._connection.execute(stmt)
        await self._connection.commit()

    @staticmethod
    def _batch(raw: object) -> BatchDTO:
        if not isinstance(raw, Mapping):
            msg = "stored batch is malformed"
            raise ConflictError(msg)
        items = raw["items"]
        if not isinstance(items, list):
            msg = "stored batch items are malformed"
            raise ConflictError(msg)
        tasks = tuple(IdempotencyRepository._task(item) for item in items)
        return BatchDTO(str(raw["batch_id"]), tasks, bool(raw["more_available"]), bool(raw["recovered"]))

    @staticmethod
    def _batch_value(value: BatchDTO) -> dict[str, object]:
        return {
            "batch_id": value.batch_id,
            "more_available": value.more_available,
            "recovered": value.recovered,
            "items": [IdempotencyRepository._task_value(item) for item in value.items],
        }

    @staticmethod
    def _task(raw: object) -> ChoiceTaskDTO:
        if not isinstance(raw, Mapping):
            msg = "stored batch task is malformed"
            raise ConflictError(msg)
        options = raw.get("options")
        if not isinstance(options, list):
            msg = "stored batch task options are malformed"
            raise ConflictError(msg)
        return ChoiceTaskDTO(
            str(raw["item_id"]),
            str(raw["step_id"]),
            str(raw["attempt_id"]),
            str(raw["question"]),
            tuple(str(option) for option in options),
            bool(raw["is_multiple_choice"]),
            str(raw["expires_at"]) if raw["expires_at"] is not None else None,
        )

    @staticmethod
    def _task_value(value: ChoiceTaskDTO) -> dict[str, object]:
        return {
            "item_id": value.item_id,
            "step_id": value.step_id,
            "attempt_id": value.attempt_id,
            "question": value.question,
            "options": list(value.options),
            "is_multiple_choice": value.is_multiple_choice,
            "expires_at": value.expires_at,
        }

    @staticmethod
    def _receipt(raw: object) -> SubmissionReceiptDTO:
        if not isinstance(raw, Mapping):
            msg = "stored receipt is malformed"
            raise ConflictError(msg)
        return SubmissionReceiptDTO(
            str(raw["item_id"]),
            DeliveryState(str(raw["delivery"])),
            str(raw["submission_id"]) if raw["submission_id"] is not None else None,
            int(str(raw["draft_revision"])) if raw["draft_revision"] is not None else None,
        )

    @staticmethod
    def _receipt_value(value: SubmissionReceiptDTO) -> dict[str, object]:
        return {
            "item_id": value.item_id,
            "delivery": value.delivery.value,
            "submission_id": value.submission_id,
            "draft_revision": value.draft_revision,
        }
