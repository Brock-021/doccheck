"""
DocCheck 审计日志服务
"""

from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models import AuditLog


async def log_action(
    db: AsyncSession,
    user_id: int,
    username: str,
    action: str,
    target_type: str = None,
    target_id: int = None,
    detail: str = None,
    ip_address: str = None,
):
    """记录一条审计日志。"""
    log = AuditLog(
        user_id=user_id,
        username=username,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
        ip_address=ip_address,
        created_at=datetime.utcnow(),
    )
    db.add(log)
    await db.commit()


async def get_audit_logs(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    action: str = None,
    start: str = None,
    end: str = None,
) -> tuple[list[AuditLog], int]:
    """分页查询审计日志。"""
    query = select(AuditLog).order_by(AuditLog.created_at.desc())

    if action:
        query = query.where(AuditLog.action == action)
    if start:
        query = query.where(AuditLog.created_at >= start)
    if end:
        query = query.where(AuditLog.created_at <= end)

    # Count
    count_query = select(AuditLog.id)
    if action:
        count_query = count_query.where(AuditLog.action == action)
    if start:
        count_query = count_query.where(AuditLog.created_at >= start)
    if end:
        count_query = count_query.where(AuditLog.created_at <= end)

    total_result = await db.execute(count_query)
    total = len(total_result.all())

    # Paginate
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    result = await db.execute(query)
    logs = result.scalars().all()

    return logs, total
