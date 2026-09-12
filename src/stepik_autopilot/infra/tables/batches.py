import sqlalchemy as sa

from .metadata import metadata

batches = sa.Table(
    "batches",
    metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("run_id", sa.String, nullable=False, index=True),
    sa.Column("state", sa.String, nullable=False),
)
