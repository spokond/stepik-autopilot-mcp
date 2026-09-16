from collections.abc import Mapping
from typing import TYPE_CHECKING

import sqlalchemy as sa

from stepik_autopilot.application.dto import ChoiceDatasetDTO, ItemDTO
from stepik_autopilot.core.enums import ItemState
from stepik_autopilot.core.exceptions import ConflictError
from stepik_autopilot.infra.tables import items, runs

from .base import SQLAlchemyRepository

if TYPE_CHECKING:
    from sqlalchemy.engine import RowMapping


class ItemRepository(SQLAlchemyRepository):
    async def add_items(self, values: tuple[ItemDTO, ...]) -> None:
        if not values:
            return
        stmt = sa.insert(items).values([self._values(item) for item in values])
        await self._connection.execute(stmt)
        await self._connection.commit()

    async def list_items(
        self, account_id: str, run_id: str, states: frozenset[ItemState] | None = None
    ) -> tuple[ItemDTO, ...]:
        stmt = (
            sa.select(items)
            .join(runs, items.c.run_id == runs.c.id)
            .where(runs.c.account_id == account_id, items.c.run_id == run_id)
        )
        if states:
            stmt = stmt.where(items.c.state.in_([state.value for state in states]))
        rows = (await self._connection.execute(stmt)).mappings().all()
        return tuple(self._item(row) for row in rows)

    async def get_item(self, account_id: str, run_id: str, item_id: str) -> ItemDTO | None:
        stmt = (
            sa.select(items)
            .join(runs, items.c.run_id == runs.c.id)
            .where(runs.c.account_id == account_id, items.c.run_id == run_id, items.c.id == item_id)
        )
        row = (await self._connection.execute(stmt)).mappings().one_or_none()
        return None if row is None else self._item(row)

    async def save_item(self, account_id: str, item: ItemDTO) -> None:
        values = self._values(item)
        values.pop("id")
        values.pop("run_id")
        stmt = (
            sa.update(items)
            .where(
                items.c.id == item.id,
                items.c.run_id == item.run_id,
                items.c.run_id.in_(sa.select(runs.c.id).where(runs.c.account_id == account_id)),
            )
            .values(values)
        )
        await self._connection.execute(stmt)
        await self._connection.commit()

    @staticmethod
    def _values(item: ItemDTO) -> dict[str, object]:
        dataset = item.choice_dataset
        return {
            "id": item.id,
            "run_id": item.run_id,
            "step_id": item.step_id,
            "attempt_id": item.attempt_id,
            "kind": item.kind,
            "state": item.state.value,
            "payload": {
                "assignment_id": item.assignment_id,
                "question": item.question,
                "options": list(dataset.options) if dataset else [],
                "is_multiple_choice": dataset.is_multiple_choice if dataset else False,
                "code_languages": list(item.code_languages),
                "expires_at": item.expires_at,
            },
            "batch_id": item.batch_id,
            "lease_until": item.expires_at,
            "draft_revision": item.draft_revision,
        }

    @staticmethod
    def _item(row: RowMapping) -> ItemDTO:
        payload = row["payload"]
        if not isinstance(payload, Mapping):
            msg = "stored run item is malformed"
            raise ConflictError(msg)
        options = payload.get("options")
        if not isinstance(options, list):
            msg = "stored choice options are malformed"
            raise ConflictError(msg)
        attempt_id = row["attempt_id"]
        dataset = None
        if attempt_id is not None:
            dataset = ChoiceDatasetDTO(
                options=tuple(str(option) for option in options),
                is_multiple_choice=bool(payload["is_multiple_choice"]),
            )
        languages = payload.get("code_languages")
        code_languages = tuple(str(language) for language in languages) if isinstance(languages, list) else ()
        return ItemDTO(
            id=str(row["id"]),
            run_id=str(row["run_id"]),
            step_id=str(row["step_id"]),
            assignment_id=str(payload["assignment_id"]),
            kind=str(row["kind"]),
            question=str(payload["question"]),
            state=ItemState(str(row["state"])),
            choice_dataset=dataset,
            code_languages=code_languages,
            attempt_id=str(attempt_id) if attempt_id is not None else None,
            expires_at=str(payload["expires_at"]) if payload["expires_at"] is not None else None,
            batch_id=str(row["batch_id"]) if row["batch_id"] is not None else None,
            draft_revision=int(str(row["draft_revision"])),
        )
