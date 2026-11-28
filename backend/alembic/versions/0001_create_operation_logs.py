"""Создание таблицы operation_logs для журнала операций.

Revision ID: 0001_create_operation_logs
Revises:
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_create_operation_logs"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operation_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="success"),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_operation_logs_operation", "operation_logs", ["operation"])
    op.create_index("ix_operation_logs_resource_type", "operation_logs", ["resource_type"])
    op.create_index("ix_operation_logs_resource_id", "operation_logs", ["resource_id"])
    op.create_index("ix_operation_logs_status", "operation_logs", ["status"])
    op.create_index("ix_operation_logs_created_at", "operation_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_operation_logs_created_at", table_name="operation_logs")
    op.drop_index("ix_operation_logs_status", table_name="operation_logs")
    op.drop_index("ix_operation_logs_resource_id", table_name="operation_logs")
    op.drop_index("ix_operation_logs_resource_type", table_name="operation_logs")
    op.drop_index("ix_operation_logs_operation", table_name="operation_logs")
    op.drop_table("operation_logs")
