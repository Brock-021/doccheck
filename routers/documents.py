"""DocCheck routes - 文档上传与检查"""

import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Document, DocType, CheckTask, CheckResult, Report, Rule, SystemConfig, rule_doc_types
from schemas import DocumentResponse, CheckTaskResponse, CheckResultResponse
from services.doc_parser import parse_docx
from services.checker import run_check
from config import UPLOAD_DIR, MAX_UPLOAD_SIZE, ALLOWED_EXTENSIONS

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/upload")
async def upload_document(
    request: Request,
    doc_type_id: int = Form(...),
    stage: str = Form("initial"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """上传文档并发起检查。"""
    # Verify user login
    user = getattr(request.state, "current_user", None)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")

    # Validate doc type
    dt_result = await db.execute(select(DocType).where(DocType.id == doc_type_id))
    if not dt_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="文档类型不存在")

    # Validate file
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"仅支持 .docx 格式，不支持 {ext}")

    # Check file size
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail=f"文件大小不能超过 {MAX_UPLOAD_SIZE // (1024*1024)}MB")

    # Save file
    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = UPLOAD_DIR / unique_name
    with open(file_path, "wb") as f:
        f.write(contents)

    # Create document record
    doc = Document(
        user_id=user["user_id"],
        doc_type_id=doc_type_id,
        filename=file.filename or unique_name,
        file_path=str(file_path),
        file_size=len(contents),
        original_filename=file.filename,
    )
    db.add(doc)
    await db.flush()

    # Count enabled rules for this doc type and stage (via association table)
    rule_query = select(func.count(Rule.id)).select_from(Rule).join(
        rule_doc_types, rule_doc_types.c.rule_id == Rule.id
    ).where(
        rule_doc_types.c.doc_type_id == doc_type_id,
        Rule.is_active == True,
        Rule.is_deprecated == False,
    )
    if stage and stage != "all":
        rule_query = rule_query.where(Rule.stage.in_([stage, "all"]))
    rule_count_result = await db.execute(rule_query)
    rule_count = rule_count_result.scalar() or 0

    # Create check task
    task = CheckTask(
        document_id=doc.id,
        stage=stage,
        rule_count=rule_count,
        status="pending",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # Load LLM config from DB
    llm_config = {
        "api_base": "http://localhost:8000/v1",
        "api_key": "",
        "model": "gpt-3.5-turbo",
        "timeout": 60,
        "max_retries": 3,
        "temperature": 0.1,
        "max_tokens": 4096,
    }
    for key in llm_config:
        cfg_result = await db.execute(
            select(SystemConfig).where(SystemConfig.config_key == f"llm_{key}")
        )
        cfg = cfg_result.scalar_one_or_none()
        if cfg:
            llm_config[key] = cfg.config_value

    # Run check asynchronously with a fresh session
    import asyncio
    from database import async_session_factory

    async def run_check_wrapper():
        async with async_session_factory() as fresh_db:
            from models import CheckTask as CT
            fresh_task_result = await fresh_db.execute(
                select(CT).where(CT.id == task.id)
            )
            fresh_task = fresh_task_result.scalar_one_or_none()
            if fresh_task:
                await run_check(
                    fresh_db, fresh_task,
                    api_base=str(llm_config["api_base"]),
                    api_key=str(llm_config["api_key"]),
                    model=str(llm_config["model"]),
                    llm_timeout=int(llm_config["timeout"]),
                    llm_retries=int(llm_config["max_retries"]),
                    temperature=float(llm_config["temperature"]),
                    max_tokens=int(llm_config["max_tokens"]),
                )

    asyncio.create_task(run_check_wrapper())

    # Return response
    resp_data = {
        "document_id": doc.id,
        "check_task_id": task.id,
        "filename": doc.filename,
        "rule_count": rule_count,
        "status": task.status,
    }

    return resp_data


@router.get("")
async def list_documents(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的文档列表。"""
    user = getattr(request.state, "current_user", None)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")

    user_roles = user.get("role", "").split(",")

    query = select(Document)
    if "admin" not in user_roles:
        query = query.where(Document.user_id == user["user_id"])

    query = query.order_by(Document.upload_time.desc())
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    docs = result.scalars().all()

    resp = []
    for doc in docs:
        dt_result = await db.execute(select(DocType).where(DocType.id == doc.doc_type_id))
        dt = dt_result.scalar_one_or_none()

        # Get latest check task
        ct_result = await db.execute(
            select(CheckTask).where(CheckTask.document_id == doc.id)
            .order_by(CheckTask.created_at.desc()).limit(1)
        )
        ct = ct_result.scalar_one_or_none()

        # Count check tasks
        count_result = await db.execute(
            select(func.count(CheckTask.id)).where(CheckTask.document_id == doc.id)
        )

        resp.append(DocumentResponse(
            id=doc.id, user_id=doc.user_id, doc_type_id=doc.doc_type_id,
            doc_type_name=dt.name if dt else None,
            filename=doc.original_filename or doc.filename,
            original_filename=doc.original_filename,
            file_size=doc.file_size, upload_time=doc.upload_time,
            check_count=count_result.scalar() or 0,
            last_check_status=ct.status if ct else None,
            last_check_time=ct.created_at if ct else None,
        ))

    return resp


@router.get("/{doc_id}")
async def get_document(doc_id: int, db: AsyncSession = Depends(get_db)):
    """获取单个文档详情。"""
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {
        "id": doc.id,
        "filename": doc.original_filename or doc.filename,
        "doc_type_id": doc.doc_type_id,
        "file_size": doc.file_size,
        "upload_time": doc.upload_time.isoformat(),
    }


@router.get("/{doc_id}/compare")
async def compare_checks(
    doc_id: int,
    v1: int = Query(..., description="第一个检查任务ID"),
    v2: int = Query(..., description="第二个检查任务ID"),
    db: AsyncSession = Depends(get_db),
):
    """比较同一文档的两次检查结果差异。"""
    # Verify doc exists
    doc_result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    # Load task v1
    t1_result = await db.execute(select(CheckTask).where(CheckTask.id == v1))
    t1 = t1_result.scalar_one_or_none()
    if not t1:
        raise HTTPException(status_code=404, detail=f"检查任务 {v1} 不存在")

    # Load task v2
    t2_result = await db.execute(select(CheckTask).where(CheckTask.id == v2))
    t2 = t2_result.scalar_one_or_none()
    if not t2:
        raise HTTPException(status_code=404, detail=f"检查任务 {v2} 不存在")

    # Get results for both
    r1_result = await db.execute(
        select(CheckResult).where(CheckResult.check_task_id == v1)
    )
    r1_list = r1_result.scalars().all()

    r2_result = await db.execute(
        select(CheckResult).where(CheckResult.check_task_id == v2)
    )
    r2_list = r2_result.scalars().all()

    # Build rule maps
    async def _get_rule_map(results_list):
        rule_map = {}
        for r in results_list:
            rule_r = await db.execute(select(Rule).where(Rule.id == r.rule_id))
            rule = rule_r.scalar_one_or_none()
            rule_name = rule.name if rule else f"规则#{r.rule_id}"
            rule_map[rule_name] = {
                "id": r.id,
                "compliant": r.compliant,
                "issue": r.issue,
                "suggestion": r.suggestion,
                "review_status": r.review_status,
                "rule_name": rule_name,
                "severity": rule.severity if rule else "suggest",
            }
        return rule_map

    v1_map = await _get_rule_map(r1_list)
    v2_map = await _get_rule_map(r2_list)

    # Compute diff
    all_rules = sorted(set(list(v1_map.keys()) + list(v2_map.keys())))

    diff_results = []
    new_issues = 0
    fixed_issues = 0
    still_issues = 0
    unchanged_pass = 0

    for rule_name in all_rules:
        v1_data = v1_map.get(rule_name)
        v2_data = v2_map.get(rule_name)

        v1_ok = v1_data["compliant"] == "true" if v1_data else None
        v2_ok = v2_data["compliant"] == "true" if v2_data else None

        if v1_ok is None and v2_ok is not None:
            status = "new_in_v2"
            new_issues += 1 if not v2_ok else 0
        elif v2_ok is None and v1_ok is not None:
            status = "removed_in_v2"
            fixed_issues += 1 if not v1_ok else 0
        elif v1_ok and not v2_ok:
            status = "regression"
            new_issues += 1
        elif not v1_ok and v2_ok:
            status = "fixed"
            fixed_issues += 1
        elif not v1_ok and not v2_ok:
            status = "still_issue"
            still_issues += 1
        else:
            status = "ok"
            unchanged_pass += 1

        data = (v2_data or v1_data).copy() if (v2_data or v1_data) else {}
        data["diff_status"] = status
        data["v1_compliant"] = v1_ok
        data["v2_compliant"] = v2_ok
        data["v1_issue"] = v1_data["issue"] if v1_data else ""
        data["v2_issue"] = v2_data["issue"] if v2_data else ""
        diff_results.append(data)

    # Get reports for both tasks
    rp1_result = await db.execute(select(Report).where(Report.check_task_id == v1))
    rp1 = rp1_result.scalar_one_or_none()
    rp2_result = await db.execute(select(Report).where(Report.check_task_id == v2))
    rp2 = rp2_result.scalar_one_or_none()

    return {
        "document_id": doc_id,
        "filename": doc.original_filename or doc.filename,
        "v1": {"task_id": v1, "created_at": t1.created_at.isoformat() if t1.created_at else None, "report_id": rp1.id if rp1 else None},
        "v2": {"task_id": v2, "created_at": t2.created_at.isoformat() if t2.created_at else None, "report_id": rp2.id if rp2 else None},
        "summary": {
            "new_issues": new_issues,
            "fixed_issues": fixed_issues,
            "still_issues": still_issues,
            "unchanged_pass": unchanged_pass,
            "total": len(diff_results),
        },
        "results": diff_results,
    }


@router.get("/{doc_id}/history")
async def get_document_history(doc_id: int, db: AsyncSession = Depends(get_db)):
    """获取某文档的历史检查记录。"""
    result = await db.execute(
        select(CheckTask).where(CheckTask.document_id == doc_id)
        .order_by(CheckTask.created_at.desc())
    )
    tasks = result.scalars().all()

    history = []
    for task in tasks:
        # Get report
        report_result = await db.execute(
            select(Report).where(Report.check_task_id == task.id)
        )
        report = report_result.scalar_one_or_none()

        history.append({
            "check_task_id": task.id,
            "report_id": report.id if report else None,
            "stage": task.stage,
            "rule_count": task.rule_count,
            "status": task.status,
            "error_message": task.error_message,
            "created_at": task.created_at.isoformat(),
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "conclusion": report.conclusion if report else None,
        })

    return history


@router.post("/{doc_id}/recheck")
async def recheck_document(
    doc_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """重新检查（上传新版本）。"""
    user = getattr(request.state, "current_user", None)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")

    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    # Save new version
    ext = os.path.splitext(file.filename or "doc.docx")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="仅支持 .docx 格式")

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="文件过大")

    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = UPLOAD_DIR / unique_name
    with open(file_path, "wb") as f:
        f.write(contents)

    # Update document file
    doc.file_path = str(file_path)
    doc.file_size = len(contents)
    doc.original_filename = file.filename

    # Create new check task
    task = CheckTask(
        document_id=doc.id,
        stage="initial",
        status="pending",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    return {
        "document_id": doc.id,
        "check_task_id": task.id,
        "status": task.status,
    }


# ═══════════════════════════════════════════════════════════
# Check Task endpoints
# ═══════════════════════════════════════════════════════════

@router.get("/check-tasks/{task_id}/status")
async def get_check_task_status(task_id: int, db: AsyncSession = Depends(get_db)):
    """获取检查任务状态。"""
    result = await db.execute(select(CheckTask).where(CheckTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="检查任务不存在")

    return {
        "id": task.id,
        "status": task.status,
        "rule_count": task.rule_count,
        "error_message": task.error_message,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }
