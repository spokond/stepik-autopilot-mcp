import sqlalchemy as sa

from stepik_autopilot.application.dto import RunDTO
from stepik_autopilot.core.enums import Grading, RunMode, RunState, Selection, Strategy, Target
from stepik_autopilot.infra.tables import runs

from .base import SQLAlchemyRepository


class RunRepository(SQLAlchemyRepository):
    async def create_run(self, run: RunDTO) -> None:
        stmt = sa.insert(runs).values(
            id=run.id,
            account_id=run.account_id,
            course_id=run.course_id,
            mode=run.mode.value,
            strategy=run.strategy.value,
            selection=run.selection.value,
            target=run.target.value,
            grading=run.grading.value,
            state=run.state.value,
        )
        await self._connection.execute(stmt)
        await self._connection.commit()

    async def get_run(self, account_id: str, run_id: str) -> RunDTO | None:
        stmt = sa.select(runs).where(runs.c.id == run_id, runs.c.account_id == account_id)
        row = (await self._connection.execute(stmt)).mappings().one_or_none()
        if row is None:
            return None
        return RunDTO(
            row["id"],
            row["account_id"],
            row["course_id"],
            RunMode(row["mode"]),
            Strategy(row["strategy"]),
            Selection(row["selection"]),
            Target(row["target"]),
            Grading(row["grading"]),
            RunState(row["state"]),
        )

    async def set_run_state(self, account_id: str, run_id: str, state: RunState) -> None:
        stmt = sa.update(runs).where(runs.c.id == run_id, runs.c.account_id == account_id).values(state=state.value)
        await self._connection.execute(stmt)
        await self._connection.commit()
