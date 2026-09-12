from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection


class SQLAlchemyRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection
