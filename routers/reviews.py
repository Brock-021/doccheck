"""DocCheck routes - 审核流程"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import CheckResult, Report, CheckTask, Document
from schemas import ReviewAction, ConclusionRequest
from services.audit import log_action

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


@router.post("/{result_id}/confirm")
async def confirm_issue(
    result_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """确认问题（认可 AI 判断）。"""
    user = getattr(request.state, "current_user", None)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")

    user_roles = user.get("role", "").split(",")
    if "admin" not in user_roles and "reviewer" not in user_roles:
        raise HTTPException(status_code=403, detail="权限不足")

    result = await db.execute(select(CheckResult).where(CheckResult.id == result_id))
    check_result = result.scalar_one_or_none()
    if not check_result:
        raise HTTPException(status_code=404, detail="检查结果不存在")

    if check_result.review_status != "pending":
        raise HTTPException(status_code=409, detail="该结果已审核，不能重复操作")

    check_result.review_status = "confirmed"
    check_result.reviewer_id = user["user_id"]
    check_result.reviewed_at = datetime.utcnow()
    await db.commit()

    await log_action(db, user["user_id"], user["username"],
                     "review_confirm", "check_result", result_id,
                     f"确认问题: {check_result.issue}")

    return {"message": "已确认", "review_status": "confirmed"}


@router.post("/{result_id}/reject")
async def reject_issue(
    result_id: int,
    request: Request,
    data: ReviewAction,
    db: AsyncSession = Depends(get_db),
):
    """驳回问题（AI 误判）。"""
    user = getattr(request.state, "current_user", None)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")

    user_roles = user.get("role", "").split(",")
    if "admin" not in user_roles and "reviewer" not in user_roles:
        raise HTTPException(status_code=403, detail="权限不足")

    result = await db.execute(select(CheckResult).where(CheckResult.id == result_id))
    check_result = result.scalar_one_or_none()
    if not check_result:
        raise HTTPException(status_code=404, detail="检查结果不存在")

    if check_result.review_status != "pending":
        raise HTTPException(status_code=409, detail="该结果已审核，不能重复操作")

    check_result.review_status = "rejected"
    check_result.review_remark = data.remark
    check_result.reviewer_id = user["user_id"]
    check_result.reviewed_at = datetime.utcnow()
    await db.commit()

    await log_action(db, user["user_id"], user["username"],
                     "review_reject", "check_result", result_id,
                     f"驳回: {data.remark}")

    return {"message": "已驳回", "review_status": "rejected", "remark": data.remark}


@router.post("/{result_id}/ignore")
async def ignore_issue(
    result_id: int,
    request: Request,
    data: ReviewAction,
    db: AsyncSession = Depends(get_db),
):
    """忽略问题（存在但本次可接受）。"""
    user = getattr(request.state, "current_user", None)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")

    user_roles = user.get("role", "").split(",")
    if "admin" not in user_roles and "reviewer" not in user_roles:
        raise HTTPException(status_code=403, detail="权限不足")

    result = await db.execute(select(CheckResult).where(CheckResult.id == result_id))
    check_result = result.scalar_one_or_none()
    if not check_result:
        raise HTTPException(status_code=404, detail="检查结果不存在")

    if check_result.review_status != "pending":
        raise HTTPException(status_code=409, detail="该结果已审核，不能重复操作")

    check_result.review_status = "ignored"
    check_result.review_remark = data.remark
    check_result.reviewer_id = user["user_id"]
    check_result.reviewed_at = datetime.utcnow()
    await db.commit()

    await log_action(db, user["user_id"], user["username"],
                     "review_ignore", "check_result", result_id,
                     f"忽略: {data.remark}")

    return {"message": "已忽略", "review_status": "ignored", "remark": data.remark}


@router.post("/{report_id}/conclusion")
async def conclude_report(
    report_id: int,
    request: Request,
    data: ConclusionRequest,
    db: AsyncSession = Depends(get_db),
):
    """出具审核结论。"""
    user = getattr(request.state, "current_user", None)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")

    user_roles = user.get("role", "").split(",")
    if "admin" not in user_roles and "reviewer" not in user_roles:
        raise HTTPException(status_code=403, detail="权限不足")

    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")

    if data.conclusion not in ("pass", "conditional_pass", "fail"):
        raise HTTPException(status_code=400, detail="无效的结论类型")

    report.conclusion = data.conclusion
    report.conclusion_remark = data.remark
    report.concluded_by = user["user_id"]
    report.concluded_at = datetime.utcnow()
    await db.commit()

    conclusion_labels = {
        "pass": "通过",
        "conditional_pass": "有条件通过",
        "fail": "不通过",
    }

    await log_action(db, user["user_id"], user["username"],
                     "conclude", "report", report_id,
                     f"审核结论: {conclusion_labels.get(data.conclusion, data.conclusion)}")

    return {
        "message": "审核结论已提交",
        "conclusion": data.conclusion,
        "conclusion_label": conclusion_labels.get(data.conclusion),
        "remark": data.remark,
    }
