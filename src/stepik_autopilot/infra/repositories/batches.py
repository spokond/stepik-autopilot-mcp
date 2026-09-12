import sqlalchemy as sa

from stepik_autopilot.infra.tables import batches, runs

from .base import SQLAlchemyRepository


class BatchRepository(SQLAlchemyRepository):
    async def create_batch(self, run_id: str, batch_id: str) -> None:
        stmt = sa.insert(batches).values(id=batch_id, run_id=run_id, state="active")
        await self._connection.execute(stmt)
        await self._connection.commit()

    async def active_batch(self, account_id: str, run_id: str) -> str | None:
        stmt = (
            sa.select(batches.c.id)
            .join(runs, batches.c.run_id == runs.c.id)
            .where(runs.c.account_id == account_id, batches.c.run_id == run_id, batches.c.state == "active")
        )
        return (await self._connection.execute(stmt)).scalar_one_or_none()

    async def close_batch(self, run_id: str, batch_id: str) -> None:
        stmt = sa.update(batches).where(batches.c.id == batch_id, batches.c.run_id == run_id).values(state="closed")
        await self._connection.execute(stmt)
        await self._connection.commit()
