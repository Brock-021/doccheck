"""
DocCheck - 统计分析看板
"""

from __future__ import annotations
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy import select, func, distinct, case
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Document, CheckTask, CheckResult, Report, Rule, DocType, User

router = APIRouter(prefix="/api/admin", tags=["statistics"])


@router.get("/statistics")
async def get_statistics(
    request: Request,
    start: str = Query(None, description="开始日期 YYYY-MM-DD"),
    end: str = Query(None, description="结束日期 YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
):
    """获取统计分析数据。"""
    user = getattr(request.state, "current_user", None)
    if not user or "admin" not in user.get("role", "").split(","):
        raise HTTPException(status_code=403, detail="权限不足")

    # 构建时间筛选条件
    filters = []
    start_dt = None
    end_dt = None
    if start:
        try:
            start_dt = datetime.strptime(start, "%Y-%m-%d")
            filters.append(CheckTask.created_at >= start_dt)
        except ValueError:
            pass
    if end:
        try:
            end_dt = datetime.strptime(end + " 23:59:59", "%Y-%m-%d %H:%M:%S")
            filters.append(CheckTask.created_at <= end_dt)
        except ValueError:
            pass

    # ── 1. 概览统计 ──
    # 总文档数（有时间筛选则只算该时间段内上传的）
    doc_filters = []
    if start:
        try:
            doc_filters.append(Document.upload_time >= datetime.strptime(start, "%Y-%m-%d"))
        except ValueError:
            pass
    if end:
        try:
            doc_filters.append(Document.upload_time <= datetime.strptime(end + " 23:59:59", "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            pass

    doc_query = select(func.count(Document.id))
    if doc_filters:
        doc_query = doc_query.where(*doc_filters)
    doc_count = (await db.execute(doc_query)).scalar() or 0

    # 总检查次数
    check_query = select(func.count(CheckTask.id))
    if filters:
        check_query = check_query.where(*filters)
    check_count = (await db.execute(check_query)).scalar() or 0

    # 成功的检查次数
    done_query = select(func.count(CheckTask.id)).where(CheckTask.status == "done")
    if filters:
        done_query = done_query.where(*filters)
    done_count = (await db.execute(done_query)).scalar() or 0

    # 失败的检查次数
    failed_query = select(func.count(CheckTask.id)).where(CheckTask.status == "failed")
    if filters:
        failed_query = failed_query.where(*filters)
    failed_count = (await db.execute(failed_query)).scalar() or 0

    # ── 2. 按文档类型的检查分布 ──
    type_query = (
        select(
            DocType.name,
            func.count(distinct(Document.id)).label("doc_count"),
            func.count(CheckTask.id).label("check_count"),
        )
        .select_from(DocType)
        .outerjoin(Rule, Rule.doc_type_id == DocType.id)
        .outerjoin(Document, Document.doc_type_id == DocType.id)
        .outerjoin(CheckTask, CheckTask.document_id == Document.id)
        .group_by(DocType.id, DocType.name)
        .order_by(func.count(CheckTask.id).desc())
    )
    type_result = await db.execute(type_query)
    type_stats = [{"name": row[0], "doc_count": row[1], "check_count": row[2]} for row in type_result.all()]

    # ── 3. 用户活跃度（文档上传数 top10） ──
    user_query = (
        select(
            User.username,
            User.display_name,
            func.count(distinct(Document.id)).label("upload_count"),
            func.count(CheckTask.id).label("check_count"),
        )
        .select_from(User)
        .outerjoin(Document, Document.user_id == User.id)
        .outerjoin(CheckTask, CheckTask.document_id == Document.id)
        .group_by(User.id, User.username, User.display_name)
        .order_by(func.count(distinct(Document.id)).desc())
        .limit(10)
    )
    if filters:
        # 如果有时间筛选，关联的 check_task 也要筛选
        user_query = user_query.where(*filters)
    user_result = await db.execute(user_query)
    user_stats = [
        {
            "username": row[0],
            "display_name": row[1] or row[0],
            "upload_count": row[2],
            "check_count": row[3],
        }
        for row in user_result.all()
    ]

    # ── 4. 检查结果合规统计 ──
    # 各 compliant 状态的分布
    compliant_query = (
        select(
            CheckResult.compliant,
            func.count(CheckResult.id).label("cnt"),
        )
        .select_from(CheckResult)
        .join(CheckTask, CheckResult.check_task_id == CheckTask.id)
    )
    if filters:
        compliant_query = compliant_query.where(*filters)
    compliant_query = compliant_query.group_by(CheckResult.compliant)
    compliant_result = await db.execute(compliant_query)
    compliant_stats = {"pass": 0, "fail": 0, "unknown": 0, "total": 0}
    for row in compliant_result.all():
        val = str(row[0]).lower() if row[0] else "unknown"
        cnt = row[1]
        compliant_stats["total"] += cnt
        if val == "true":
            compliant_stats["pass"] += cnt
        elif val == "false":
            compliant_stats["fail"] += cnt
        else:
            compliant_stats["unknown"] += cnt
    compliant_stats["pass_rate"] = round(
        (compliant_stats["pass"] / compliant_stats["total"] * 100) if compliant_stats["total"] > 0 else 0, 1
    )
    compliant_stats["fail_rate"] = round(
        (compliant_stats["fail"] / compliant_stats["total"] * 100) if compliant_stats["total"] > 0 else 0, 1
    )

    # ── 5. 审核状态统计 ──
    review_query = (
        select(
            CheckResult.review_status,
            func.count(CheckResult.id).label("cnt"),
        )
        .select_from(CheckResult)
        .join(CheckTask, CheckResult.check_task_id == CheckTask.id)
    )
    if filters:
        review_query = review_query.where(*filters)
    review_query = review_query.group_by(CheckResult.review_status)
    review_result = await db.execute(review_query)
    review_stats = {"pending": 0, "confirmed": 0, "rejected": 0, "ignored": 0, "total": 0}
    for row in review_result.all():
        status = row[0] or "pending"
        cnt = row[1]
        review_stats["total"] += cnt
        if status in review_stats:
            review_stats[status] += cnt

    # ── 6. 报告结论分布 ──
    conclusion_query = (
        select(
            Report.conclusion,
            func.count(Report.id).label("cnt"),
        )
        .select_from(Report)
        .join(CheckTask, Report.check_task_id == CheckTask.id)
    )
    if filters:
        conclusion_query = conclusion_query.where(*filters)
    conclusion_query = conclusion_query.group_by(Report.conclusion)
    conclusion_result = await db.execute(conclusion_query)
    conclusion_stats = {"pass": 0, "conditional_pass": 0, "fail": 0, "pending": 0, "total": 0}
    for row in conclusion_result.all():
        c = row[0] or "pending"
        cnt = row[1]
        conclusion_stats["total"] += cnt
        if c in conclusion_stats:
            conclusion_stats[c] += cnt

    # ── 7. 按天检查趋势（近30天或按时间范围） ──
    from sqlalchemy import text
    trend_base = select(
        text("DATE(created_at) AS day"),
        func.count(CheckTask.id).label("cnt"),
    ).select_from(CheckTask)
    if start:
        trend_base = trend_base.where(CheckTask.created_at >= start_dt)
    if end:
        trend_base = trend_base.where(CheckTask.created_at <= end_dt)
    if not start and not end:
        from datetime import timedelta
        trend_base = trend_base.where(
            CheckTask.created_at >= datetime.now() - timedelta(days=30)
        )
    trend_query = trend_base.group_by(text("day")).order_by(text("day"))
    trend_result = await db.execute(trend_query)
    daily_trend = [{"date": str(row[0]), "count": row[1]} for row in trend_result.all()]

    # ── 8. 规则命中统计 ──
    rule_hit_query = (
        select(
            Rule.name,
            func.count(CheckResult.id).label("hit_count"),
            func.sum(
                case((CheckResult.compliant == "false", 1), else_=0)
            ).label("fail_count"),
        )
        .select_from(Rule)
        .join(CheckResult, CheckResult.rule_id == Rule.id)
        .join(CheckTask, CheckResult.check_task_id == CheckTask.id)
        .group_by(Rule.id, Rule.name)
        .order_by(func.count(CheckResult.id).desc())
        .limit(20)
    )
    if filters:
        rule_hit_query = rule_hit_query.where(*filters)
    rule_hit_result = await db.execute(rule_hit_query)
    rule_stats = [
        {
            "name": row[0],
            "hit_count": row[1],
            "fail_count": row[2] or 0,
        }
        for row in rule_hit_result.all()
    ]

    return {
        "overview": {
            "doc_count": doc_count,
            "check_count": check_count,
            "done_count": done_count,
            "failed_count": failed_count,
            "user_count": (await db.execute(select(func.count(User.id)))).scalar() or 0,
        },
        "doc_type_stats": type_stats,
        "user_stats": user_stats,
        "compliant_stats": compliant_stats,
        "review_stats": review_stats,
        "conclusion_stats": conclusion_stats,
        "daily_trend": daily_trend,
        "rule_stats": rule_stats,
    }
