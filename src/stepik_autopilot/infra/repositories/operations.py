from collections.abc import Mapping
from typing import TYPE_CHECKING

import sqlalchemy as sa

from stepik_autopilot.application.dto import (
    BlanksReplyDTO,
    ChoiceReplyDTO,
    CodeReplyDTO,
    MatchingReplyDTO,
    NumberReplyDTO,
    OperationDTO,
    SqlReplyDTO,
    TableCellDTO,
    TableReplyDTO,
    TableRowDTO,
    TextReplyDTO,
)
from stepik_autopilot.application.replies import ReplyDTO, reply_payload
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
            kind="submission",
            state=operation.state.value,
            reply_hash=operation.reply_hash,
            request_payload={
                "attempt_id": operation.attempt_id,
                "reply": self._reply_value(operation.reply),
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
        return OperationDTO(
            id=str(row["id"]),
            account_id=str(row["account_id"]),
            item_id=str(row["item_id"]),
            attempt_id=str(payload["attempt_id"]),
            reply=OperationRepository._reply(payload.get("reply")),
            state=OperationState(str(row["state"])),
            reply_hash=str(row["reply_hash"]),
            upstream_id=str(row["upstream_id"]) if row["upstream_id"] is not None else None,
        )

    @staticmethod
    def _reply_value(reply: ReplyDTO) -> dict[str, object]:
        kinds = {
            ChoiceReplyDTO: "choice",
            TextReplyDTO: "text",
            NumberReplyDTO: "number",
            SqlReplyDTO: "sql",
            CodeReplyDTO: "code",
            BlanksReplyDTO: "fill-blanks",
            MatchingReplyDTO: "matching",
            TableReplyDTO: "table",
        }
        return {"kind": kinds[type(reply)], **reply_payload(reply)}

    @staticmethod
    def _reply(raw: object) -> ReplyDTO:  # noqa: PLR0911 - One branch per persisted reply variant.
        msg = "stored operation reply is malformed"
        if not isinstance(raw, Mapping):
            raise ConflictError(msg)
        choices = raw.get("choices")
        text = raw.get("text")
        number = raw.get("number")
        language = raw.get("language")
        code = raw.get("code")
        solve_sql = raw.get("solve_sql")
        blanks = raw.get("blanks")
        ordering = raw.get("ordering")
        if raw.get("kind") == "fill-blanks" and isinstance(blanks, list) and all(isinstance(v, str) for v in blanks):
            return BlanksReplyDTO(tuple(blanks))
        if raw.get("kind") == "matching" and isinstance(ordering, list) and all(type(v) is int for v in ordering):
            return MatchingReplyDTO(tuple(ordering))
        if raw.get("kind") == "table" and isinstance(choices, list):
            return TableReplyDTO(tuple(OperationRepository._table_row(row) for row in choices))
        if raw.get("kind") == "choice" and isinstance(choices, list):
            return ChoiceReplyDTO(tuple(bool(value) for value in choices))
        if raw.get("kind") == "text" and isinstance(text, str):
            return TextReplyDTO(text)
        if raw.get("kind") == "number" and isinstance(number, str):
            return NumberReplyDTO(number)
        if raw.get("kind") == "sql" and isinstance(solve_sql, str):
            return SqlReplyDTO(solve_sql)
        if raw.get("kind") == "code" and isinstance(language, str) and isinstance(code, str):
            return CodeReplyDTO(language, code)
        raise ConflictError(msg)

    @staticmethod
    def _table_row(raw: object) -> TableRowDTO:
        msg = "stored table reply is malformed"
        if not isinstance(raw, Mapping) or not isinstance(raw.get("name_row"), str):
            raise ConflictError(msg)
        columns = raw.get("columns")
        if not isinstance(columns, list) or not all(
            isinstance(cell, Mapping) and isinstance(cell.get("name"), str) and isinstance(cell.get("answer"), bool)
            for cell in columns
        ):
            raise ConflictError(msg)
        return TableRowDTO(str(raw["name_row"]), tuple(TableCellDTO(cell["name"], cell["answer"]) for cell in columns))
