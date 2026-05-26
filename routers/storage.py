"""
DocCheck - 存储空间管理（文档清理）
"""
from __future__ import annotations
from datetime import datetime, timedelta
import os

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Document, CheckTask, CheckResult, Report, AuditLog
from config import UPLOAD_DIR

router = APIRouter(prefix="/api/admin", tags=["storage"])


@router.get("/storage/info")
async def get_storage_info(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """获取存储信息，用于清理前的预览。"""
    user = getattr(request.state, "current_user", None)
    if not user or "admin" not in user.get("role", "").split(","):
        raise HTTPException(status_code=403, detail="权限不足")

    # 文件存储统计
    total_uploads = await db.execute(select(func.count(Document.id)))
    total_docs = total_uploads.scalar() or 0

    # 统计uploads目录占用
    uploads_size = 0
    uploads_count = 0
    if UPLOAD_DIR.exists():
        for f in UPLOAD_DIR.iterdir():
            if f.is_file():
                uploads_count += 1
                uploads_size += f.stat().st_size

    # 按时间范围统计旧文档（30天前）
    cutoff_30 = datetime.now() - timedelta(days=30)
    old_docs_30 = await db.execute(
        select(func.count(Document.id)).where(Document.upload_time < cutoff_30)
    )
    old_count_30 = old_docs_30.scalar() or 0

    # 60天前
    cutoff_60 = datetime.now() - timedelta(days=60)
    old_docs_60 = await db.execute(
        select(func.count(Document.id)).where(Document.upload_time < cutoff_60)
    )
    old_count_60 = old_docs_60.scalar() or 0

    # 90天前
    cutoff_90 = datetime.now() - timedelta(days=90)
    old_docs_90 = await db.execute(
        select(func.count(Document.id)).where(Document.upload_time < cutoff_90)
    )
    old_count_90 = old_docs_90.scalar() or 0

    # 180天前
    cutoff_180 = datetime.now() - timedelta(days=180)
    old_docs_180 = await db.execute(
        select(func.count(Document.id)).where(Document.upload_time < cutoff_180)
    )
    old_count_180 = old_docs_180.scalar() or 0

    # 查找上传了重复文档的文档类型分布
    type_query = (
        select(Document.doc_type_id, func.count(Document.id).label("cnt"))
        .group_by(Document.doc_type_id)
        .order_by(func.count(Document.id).desc())
        .limit(10)
    )
    type_result = await db.execute(type_query)

    return {
        "total_documents": total_docs,
        "uploads_count": uploads_count,
        "uploads_size": uploads_size,
        "uploads_size_human": _format_size(uploads_size),
        "old_documents": {
            "days_30": {"count": old_count_30, "cutoff": cutoff_30.isoformat()},
            "days_60": {"count": old_count_60, "cutoff": cutoff_60.isoformat()},
            "days_90": {"count": old_count_90, "cutoff": cutoff_90.isoformat()},
            "days_180": {"count": old_count_180, "cutoff": cutoff_180.isoformat()},
        },
    }


@router.post("/storage/cleanup")
async def cleanup_documents(
    request: Request,
    days: int = Query(90, description="清理多少天之前的文档"),
    db: AsyncSession = Depends(get_db),
):
    """按天数清理旧文档及其关联数据。"""
    user = getattr(request.state, "current_user", None)
    if not user or "admin" not in user.get("role", "").split(","):
        raise HTTPException(status_code=403, detail="权限不足")

    if days < 1:
        raise HTTPException(status_code=400, detail="天数必须大于0")

    cutoff = datetime.now() - timedelta(days=days)

    # 查找需要清理的文档
    doc_result = await db.execute(
        select(Document).where(Document.upload_time < cutoff)
    )
    docs = doc_result.scalars().all()

    if not docs:
        return {"message": f"没有 {days} 天前的文档需要清理", "deleted": 0}

    deleted_count = 0
    deleted_files = 0
    total_size = 0

    for doc in docs:
        # 删除关联的检查任务、检查结果、报告（级联删除）
        tasks = await db.execute(
            select(CheckTask).where(CheckTask.document_id == doc.id)
        )
        for task in tasks.scalars().all():
            # Report 由 cascade 自动删除
            # CheckResult 由 cascade 自动删除
            await db.delete(task)

        # 删除物理文件
        if doc.file_path and os.path.exists(doc.file_path):
            try:
                file_size = os.path.getsize(doc.file_path)
                os.remove(doc.file_path)
                deleted_files += 1
                total_size += file_size
            except OSError:
                pass  # 文件已被删除或权限问题

        # 删除文档记录
        await db.delete(doc)
        deleted_count += 1

    await db.commit()

    # 记录审计日志
    from services.audit import log_action
    await log_action(
        db, user["user_id"], user["username"],
        "storage_cleanup", "document", 0,
        f"清理 {deleted_count} 个 {days} 天前的文档，删除 {deleted_files} 个文件（{_format_size(total_size)}）"
    )

    return {
        "message": f"已清理 {deleted_count} 个文档，释放 {_format_size(total_size)}",
        "deleted": deleted_count,
        "files_deleted": deleted_files,
        "space_freed": total_size,
        "space_freed_human": _format_size(total_size),
        "cutoff_date": cutoff.isoformat(),
    }


def _format_size(size_bytes: int) -> str:
    """格式化文件大小。"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
