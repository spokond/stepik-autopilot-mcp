import sqlalchemy as sa

from .metadata import metadata

submissions = sa.Table(
    "submissions",
    metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("item_id", sa.String, nullable=False, unique=True),
    sa.Column("delivery", sa.String, nullable=False),
    sa.Column("grading", sa.String, nullable=False),
    sa.Column("upstream_id", sa.String),
    sa.Column("reply_hash", sa.String),
    sa.Column("operation_id", sa.String),
)
