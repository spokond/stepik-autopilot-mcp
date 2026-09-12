import sqlalchemy as sa

from .metadata import metadata

idempotency = sa.Table(
    "idempotency",
    metadata,
    sa.Column("account_id", sa.String, primary_key=True),
    sa.Column("tool", sa.String, primary_key=True),
    sa.Column("request_id", sa.String, primary_key=True),
    sa.Column("payload_hash", sa.String, nullable=False),
    sa.Column("result", sa.JSON, nullable=False),
)
