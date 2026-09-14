import sqlalchemy as sa

from stepik_autopilot.application.dto import SubmissionDTO
from stepik_autopilot.core.enums import DeliveryState, ItemState
from stepik_autopilot.infra.tables import items, runs, submissions

from .base import SQLAlchemyRepository


class SubmissionRepository(SQLAlchemyRepository):
    async def create_submission(self, submission: SubmissionDTO) -> None:
        stmt = sa.insert(submissions).values(
            id=submission.id,
            item_id=submission.item_id,
            delivery=submission.delivery.value,
            grading=submission.grading.value,
            upstream_id=submission.upstream_id,
            reply_hash=submission.reply_hash,
            operation_id=submission.operation_id,
        )
        await self._connection.execute(stmt)
        await self._connection.commit()

    async def list_submissions(self, account_id: str, run_id: str) -> list[SubmissionDTO]:
        stmt = (
            sa.select(submissions)
            .join(items, submissions.c.item_id == items.c.id)
            .join(runs, items.c.run_id == runs.c.id)
            .where(runs.c.account_id == account_id, runs.c.id == run_id)
        )
        rows = (await self._connection.execute(stmt)).mappings().all()
        return [
            SubmissionDTO(
                row["id"],
                row["item_id"],
                DeliveryState(row["delivery"]),
                ItemState(row["grading"]),
                row["upstream_id"],
                row["reply_hash"],
                row["operation_id"],
            )
            for row in rows
        ]

    async def get_submission(self, account_id: str, run_id: str, submission_id: str) -> SubmissionDTO | None:
        stmt = (
            sa.select(submissions)
            .join(items, submissions.c.item_id == items.c.id)
            .join(runs, items.c.run_id == runs.c.id)
            .where(runs.c.account_id == account_id, runs.c.id == run_id, submissions.c.id == submission_id)
        )
        row = (await self._connection.execute(stmt)).mappings().one_or_none()
        if row is None:
            return None
        return SubmissionDTO(
            row["id"],
            row["item_id"],
            DeliveryState(row["delivery"]),
            ItemState(row["grading"]),
            row["upstream_id"],
            row["reply_hash"],
            row["operation_id"],
        )

    async def update_submission(self, submission: SubmissionDTO) -> None:
        stmt = (
            sa.update(submissions)
            .where(submissions.c.id == submission.id)
            .values(
                delivery=submission.delivery.value,
                grading=submission.grading.value,
                upstream_id=submission.upstream_id,
                reply_hash=submission.reply_hash,
                operation_id=submission.operation_id,
            )
        )
        await self._connection.execute(stmt)
        await self._connection.commit()
