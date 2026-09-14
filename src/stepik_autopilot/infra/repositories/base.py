from sqlalchemy.ext.asyncio import AsyncConnection  # noqa: TC002 - Dishka resolves constructor annotations at runtime.


class SQLAlchemyRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection
