import sqlalchemy as sa

from .metadata import metadata

operations = sa.Table(
    "operations",
    metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("account_id", sa.String, nullable=False, index=True),
    sa.Column("item_id", sa.String, nullable=False, index=True),
    sa.Column("kind", sa.String, nullable=False),
    sa.Column("state", sa.String, nullable=False, index=True),
    sa.Column("reply_hash", sa.String, nullable=False),
    sa.Column("request_payload", sa.JSON, nullable=False),
    sa.Column("upstream_id", sa.String),
)
