import sqlalchemy as sa

from .metadata import metadata

runs = sa.Table(
    "runs",
    metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("account_id", sa.String, nullable=False, index=True),
    sa.Column("course_id", sa.String, nullable=False),
    sa.Column("mode", sa.String, nullable=False),
    sa.Column("strategy", sa.String, nullable=False),
    sa.Column("selection", sa.String, nullable=False),
    sa.Column("target", sa.String, nullable=False),
    sa.Column("grading", sa.String, nullable=False),
    sa.Column("state", sa.String, nullable=False),
)
