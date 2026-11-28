"""Создание таблицы stream_offer_snapshots для отслеживания офферов, удалённых в Keitaro.

Revision ID: 0002_add_stream_offer_snapshots
Revises: 0001_create_operation_logs
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_add_stream_offer_snapshots"
down_revision: str | Sequence[str] | None = "0001_create_operation_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stream_offer_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("stream_id", sa.Integer(), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=False),
        sa.Column("offer_name", sa.String(length=255), nullable=False),
        sa.Column("last_share", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("stream_id", "offer_id", name="uq_stream_offer_snapshots_stream_offer"),
    )
    op.create_index("ix_stream_offer_snapshots_campaign_id", "stream_offer_snapshots", ["campaign_id"])
    op.create_index("ix_stream_offer_snapshots_stream_id", "stream_offer_snapshots", ["stream_id"])
    op.create_index("ix_stream_offer_snapshots_offer_id", "stream_offer_snapshots", ["offer_id"])


def downgrade() -> None:
    op.drop_index("ix_stream_offer_snapshots_offer_id", table_name="stream_offer_snapshots")
    op.drop_index("ix_stream_offer_snapshots_stream_id", table_name="stream_offer_snapshots")
    op.drop_index("ix_stream_offer_snapshots_campaign_id", table_name="stream_offer_snapshots")
    op.drop_table("stream_offer_snapshots")
