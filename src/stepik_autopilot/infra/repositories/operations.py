from collections.abc import Mapping
from typing import TYPE_CHECKING

import sqlalchemy as sa

from stepik_autopilot.application.dto import ChoiceReplyDTO, OperationDTO
from stepik_autopilot.core.enums import OperationState
from stepik_autopilot.core.exceptions import ConflictError
from stepik_autopilot.infra.tables import items, operations, runs

from .base import SQLAlchemyRepository

if TYPE_CHECKING:
    from sqlalchemy.engine import RowMapping


class OperationRepository(SQLAlchemyRepository):
    async def create_operation(self, operation: OperationDTO) -> None:
        stmt = sa.insert(operations).values(
            id=operation.id,
            account_id=operation.account_id,
            item_id=operation.item_id,
            kind="choice_submission",
            state=operation.state.value,
            reply_hash=operation.reply_hash,
            request_payload={
                "attempt_id": operation.attempt_id,
                "choices": list(operation.reply.choices),
            },
            upstream_id=operation.upstream_id,
        )
        await self._connection.execute(stmt)
        await self._connection.commit()

    async def update_operation(self, operation_id: str, state: OperationState, upstream_id: str | None = None) -> None:
        values: dict[str, object] = {"state": state.value}
        if upstream_id is not None:
            values["upstream_id"] = upstream_id
        stmt = sa.update(operations).where(operations.c.id == operation_id).values(values)
        await self._connection.execute(stmt)
        await self._connection.commit()

    async def unresolved_operations(self, account_id: str, run_id: str) -> tuple[OperationDTO, ...]:
        stmt = (
            sa.select(operations)
            .join(items, operations.c.item_id == items.c.id)
            .join(runs, items.c.run_id == runs.c.id)
            .where(
                runs.c.account_id == account_id,
                runs.c.id == run_id,
                operations.c.state.in_([OperationState.SENDING.value, OperationState.OUTCOME_UNKNOWN.value]),
            )
        )
        rows = (await self._connection.execute(stmt)).mappings().all()
        return tuple(self._operation(row) for row in rows)

    @staticmethod
    def _operation(row: RowMapping) -> OperationDTO:
        payload = row["request_payload"]
        if not isinstance(payload, Mapping):
            msg = "stored operation payload is malformed"
            raise ConflictError(msg)
        choices = payload.get("choices")
        if not isinstance(choices, list):
            msg = "stored operation choices are malformed"
            raise ConflictError(msg)
        return OperationDTO(
            id=str(row["id"]),
            account_id=str(row["account_id"]),
            item_id=str(row["item_id"]),
            attempt_id=str(payload["attempt_id"]),
            reply=ChoiceReplyDTO(tuple(bool(choice) for choice in choices)),
            state=OperationState(str(row["state"])),
            reply_hash=str(row["reply_hash"]),
            upstream_id=str(row["upstream_id"]) if row["upstream_id"] is not None else None,
        )
