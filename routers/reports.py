"""
DocCheck routes - 检查报告
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import FileResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

import tempfile

from database import get_db
from models import CheckTask, CheckResult, Report, Rule, Document, DocType, User as UserModel
from schemas import CheckResultResponse
from services.audit import log_action

router = APIRouter(prefix="/api/reports", tags=["reports"])


async def _load_report_data(report_id: int, db: AsyncSession) -> dict | None:
    """Load full report data dict (shared by view + export)."""
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        return None

    ct_result = await db.execute(select(CheckTask).where(CheckTask.id == report.check_task_id))
    task = ct_result.scalar_one_or_none()
    if not task:
        return None

    doc_result = await db.execute(select(Document).where(Document.id == task.document_id))
    doc = doc_result.scalar_one_or_none()

    doc_type_name = None
    if doc:
        dt_result = await db.execute(select(DocType).where(DocType.id == doc.doc_type_id))
        dt = dt_result.scalar_one_or_none()
        doc_type_name = dt.name if dt else None

    cr_result = await db.execute(
        select(CheckResult).where(CheckResult.check_task_id == task.id)
    )
    results = cr_result.scalars().all()

    results_data = []
    for r in results:
        rule_result = await db.execute(select(Rule).where(Rule.id == r.rule_id))
        rule = rule_result.scalar_one_or_none()
        results_data.append({
            "id": r.id,
            "rule_id": r.rule_id,
            "rule_name": rule.name if rule else "未知规则",
            "rule_severity": rule.severity if rule else "must_fix",
            "compliant": r.compliant,
            "issue": r.issue,
            "location": r.location,
            "original_text": r.original_text,
            "suggestion": r.suggestion,
            "review_status": r.review_status,
            "review_remark": r.review_remark,
            "reviewer_id": r.reviewer_id,
            "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
        })

    upload_user = None
    if doc:
        u_result = await db.execute(select(UserModel).where(UserModel.id == doc.user_id))
        upload_user = u_result.scalar_one_or_none()

    return {
        "id": report.id,
        "check_task_id": report.check_task_id,
        "summary": report.summary_json,
        "conclusion": report.conclusion,
        "conclusion_remark": report.conclusion_remark,
        "concluded_at": report.concluded_at.isoformat() if report.concluded_at else None,
        "check_task": {
            "id": task.id,
            "document_id": task.document_id,
            "stage": task.stage,
            "rule_count": task.rule_count,
            "status": task.status,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        },
        "document": {
            "id": doc.id if doc else None,
            "filename": doc.original_filename or doc.filename if doc else None,
            "doc_type_name": doc_type_name,
            "uploader": upload_user.display_name if upload_user else None,
            "upload_time": doc.upload_time.isoformat() if doc else None,
        },
        "results": results_data,
    }


@router.get("/{report_id}/export/docx")
async def export_report_docx(
    report_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """导出 Word 格式报告。"""
    user = getattr(request.state, "current_user", None)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")

    report_data = await _load_report_data(report_id, db)
    if not report_data:
        raise HTTPException(status_code=404, detail="报告不存在")

    from services.exporter import export_docx
    tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
    tmp_path = tmp.name
    tmp.close()

    filename = report_data.get("document", {}).get("filename", "report").rsplit(".", 1)[0]
    export_docx(report_data, tmp_path)

    return FileResponse(
        tmp_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"{filename}_检查报告.docx",
    )


@router.get("/{report_id}/export/pdf")
async def export_report_pdf(
    report_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """导出 PDF 格式报告。"""
    user = getattr(request.state, "current_user", None)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")

    report_data = await _load_report_data(report_id, db)
    if not report_data:
        raise HTTPException(status_code=404, detail="报告不存在")

    try:
        from services.exporter import export_pdf
    except ImportError:
        raise HTTPException(status_code=500, detail="PDF 导出需要安装 reportlab: pip install reportlab")

    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp_path = tmp.name
    tmp.close()

    filename = report_data.get("document", {}).get("filename", "report").rsplit(".", 1)[0]
    export_pdf(report_data, tmp_path)

    return FileResponse(
        tmp_path,
        media_type="application/pdf",
        filename=f"{filename}_检查报告.pdf",
    )


@router.get("/{report_id}")
async def get_report(
    report_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """获取报告详情。"""
    user = getattr(request.state, "current_user", None)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")

    report_data = await _load_report_data(report_id, db)
    if not report_data:
        raise HTTPException(status_code=404, detail="报告不存在")

    return report_data


@router.post("/{report_id}/recheck")
async def recheck_report(report_id: int, db: AsyncSession = Depends(get_db)):
    """重新检查（复用文档）。"""
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")

    return {"message": "请使用 /api/documents/upload 重新上传", "report_id": report_id}
