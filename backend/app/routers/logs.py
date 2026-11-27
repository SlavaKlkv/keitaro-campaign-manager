"""Роутер просмотра журнала операций из PostgreSQL."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import OperationLog
from app.schemas import OperationLogItem

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("", response_model=list[OperationLogItem])
def list_operation_logs(
    limit: int = Query(default=50, ge=1, le=200),
    operation: str | None = Query(default=None, description="Фильтр по типу операции"),
    resource_id: int | None = Query(default=None, description="Фильтр по ID ресурса"),
    db: Session = Depends(get_db),
) -> list[OperationLogItem]:
    """Возвращает последние записи журнала операций в обратном хронологическом порядке."""
    stmt = select(OperationLog)
    if operation:
        stmt = stmt.where(OperationLog.operation == operation)
    if resource_id is not None:
        stmt = stmt.where(OperationLog.resource_id == resource_id)
    rows = db.scalars(stmt.order_by(desc(OperationLog.id)).limit(limit)).all()
    return [
        OperationLogItem(
            id=row.id,
            operation=row.operation,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            summary=row.summary,
            status=row.status,
            details=row.details,
            created_at=row.created_at,
        )
        for row in rows
    ]
