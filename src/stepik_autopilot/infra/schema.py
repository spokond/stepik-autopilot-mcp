from typing import TYPE_CHECKING

from sqlalchemy import MetaData, inspect

from stepik_autopilot.infra.tables import metadata

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection
    from sqlalchemy.ext.asyncio import AsyncEngine


class DatabaseInitializer:
    """Creates the disposable service-state schema without version migrations."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def initialize(self) -> None:
        async with self._engine.begin() as connection:
            await connection.run_sync(self._create_current_schema)

    @staticmethod
    def _create_current_schema(connection: Connection) -> None:
        # This database is a recovery journal, not user data.  A prior schema
        # must not be interpreted as compatible merely because create_all() can
        # add a missing table.
        inspector = inspect(connection)
        existing_names = set(inspector.get_table_names())
        expected_names = set(metadata.tables)
        compatible = existing_names == expected_names
        if compatible:
            for name, table in metadata.tables.items():
                actual = {column["name"] for column in inspector.get_columns(name)}
                if actual != set(table.c.keys()):
                    compatible = False
                    break
        if not compatible and existing_names:
            old_schema = MetaData()
            old_schema.reflect(bind=connection)
            old_schema.drop_all(bind=connection)
        metadata.create_all(bind=connection)
