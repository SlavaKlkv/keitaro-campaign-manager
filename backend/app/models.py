"""ORM-модели базы данных."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OperationLog(Base):
    """Запись журнала операций над кампаниями и потоками Keitaro."""

    __tablename__ = "operation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    resource_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="success", index=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )


class StreamOfferSnapshot(Base):
    """Локальный снимок известных офферов потока для отслеживания внешних удалений в Keitaro."""

    __tablename__ = "stream_offer_snapshots"
    __table_args__ = (UniqueConstraint("stream_id", "offer_id", name="uq_stream_offer_snapshots_stream_offer"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    stream_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    offer_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    offer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_share: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
