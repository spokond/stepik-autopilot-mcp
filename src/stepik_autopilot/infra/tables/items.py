import sqlalchemy as sa

from .metadata import metadata

items = sa.Table(
    "run_items",
    metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("run_id", sa.String, nullable=False, index=True),
    sa.Column("step_id", sa.String, nullable=False),
    sa.Column("attempt_id", sa.String),
    sa.Column("kind", sa.String, nullable=False),
    sa.Column("state", sa.String, nullable=False, index=True),
    sa.Column("payload", sa.JSON, nullable=False),
    sa.Column("batch_id", sa.String, index=True),
    sa.Column("lease_until", sa.String),
    sa.Column("draft_revision", sa.Integer, nullable=False, server_default="0"),
)
