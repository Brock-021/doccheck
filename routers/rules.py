"""DocCheck routes - 规则管理 + 文档类型管理"""

from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import DocType, Rule, CheckResult, rule_doc_types
from schemas import (
    DocTypeCreate, DocTypeUpdate, DocTypeResponse,
    RuleCreate, RuleUpdate, RuleResponse, BatchToggleRequest,
)
from services.audit import log_action

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ── 辅助函数 ──────────────────────────────────────────────

async def _build_rule_response(db: AsyncSession, rule: Rule) -> RuleResponse:
    """从 Rule 对象构建 RuleResponse，填充多对多关联的文档类型信息。"""
    dt_ids_result = await db.execute(
        select(rule_doc_types.c.doc_type_id).where(
            rule_doc_types.c.rule_id == rule.id
        )
    )
    dt_ids = [row[0] for row in dt_ids_result.all()]
    dt_names = []
    for dt_id in dt_ids:
        dt_result = await db.execute(select(DocType).where(DocType.id == dt_id))
        dt = dt_result.scalar_one_or_none()
        if dt:
            dt_names.append(dt.name)
    return RuleResponse(
        id=rule.id, doc_type_ids=dt_ids,
        doc_type_names=dt_names if dt_names else None,
        name=rule.name, description=rule.description,
        severity=rule.severity, stage=rule.stage,
        sort_order=rule.sort_order, is_active=rule.is_active,
        is_deprecated=rule.is_deprecated, created_at=rule.created_at,
    )


async def _sync_rule_doc_types(db: AsyncSession, rule_id: int, doc_type_ids: list[int]):
    """同步规则关联的文档类型（先删后插）。"""
    await db.execute(
        delete(rule_doc_types).where(rule_doc_types.c.rule_id == rule_id)
    )
    for dt_id in doc_type_ids:
        await db.execute(
            rule_doc_types.insert().values(rule_id=rule_id, doc_type_id=dt_id)
        )


# ═══════════════════════════════════════════════════════════
# 文档类型管理
# ═══════════════════════════════════════════════════════════

@router.get("/doc-types", response_model=list[DocTypeResponse])
async def list_doc_types(db: AsyncSession = Depends(get_db)):
    """获取文档类型列表（按排序号升序）。"""
    result = await db.execute(
        select(DocType).order_by(DocType.sort_order)
    )
    types = result.scalars().all()
    # Attach rule count via association table
    resp = []
    for t in types:
        count_result = await db.execute(
            select(func.count(rule_doc_types.c.rule_id)).where(
                rule_doc_types.c.doc_type_id == t.id,
            )
        )
        rule_count = count_result.scalar() or 0
        resp.append(DocTypeResponse(
            id=t.id, name=t.name, sort_order=t.sort_order,
            rule_count=rule_count,
        ))
    return resp


@router.post("/doc-types", response_model=DocTypeResponse)
async def create_doc_type(
    data: DocTypeCreate,
    db: AsyncSession = Depends(get_db),
):
    """新增文档类型。"""
    # Check duplicate
    existing = await db.execute(
        select(DocType).where(DocType.name == data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="文档类型名称已存在")

    doc_type = DocType(name=data.name, sort_order=data.sort_order)
    db.add(doc_type)
    await db.commit()
    await db.refresh(doc_type)
    return DocTypeResponse(id=doc_type.id, name=doc_type.name,
                           sort_order=doc_type.sort_order, rule_count=0)


@router.put("/doc-types/{type_id}", response_model=DocTypeResponse)
async def update_doc_type(
    type_id: int,
    data: DocTypeUpdate,
    db: AsyncSession = Depends(get_db),
):
    """编辑文档类型。"""
    result = await db.execute(select(DocType).where(DocType.id == type_id))
    doc_type = result.scalar_one_or_none()
    if not doc_type:
        raise HTTPException(status_code=404, detail="文档类型不存在")

    if data.name is not None:
        # Check duplicate
        dup = await db.execute(
            select(DocType).where(DocType.name == data.name, DocType.id != type_id)
        )
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="文档类型名称已存在")
        doc_type.name = data.name
    if data.sort_order is not None:
        doc_type.sort_order = data.sort_order

    await db.commit()
    await db.refresh(doc_type)

    count_result = await db.execute(
        select(func.count(rule_doc_types.c.rule_id)).where(
            rule_doc_types.c.doc_type_id == type_id,
        )
    )
    return DocTypeResponse(id=doc_type.id, name=doc_type.name,
                           sort_order=doc_type.sort_order,
                           rule_count=count_result.scalar() or 0)


@router.delete("/doc-types/{type_id}")
async def delete_doc_type(type_id: int, db: AsyncSession = Depends(get_db)):
    """删除文档类型（有关联规则时拒绝）。"""
    result = await db.execute(select(DocType).where(DocType.id == type_id))
    doc_type = result.scalar_one_or_none()
    if not doc_type:
        raise HTTPException(status_code=404, detail="文档类型不存在")

    # Check rules via association table
    count_result = await db.execute(
        select(func.count(rule_doc_types.c.rule_id)).where(
            rule_doc_types.c.doc_type_id == type_id,
        )
    )
    if count_result.scalar() > 0:
        raise HTTPException(
            status_code=409,
            detail=f"该文档类型下还有 {count_result.scalar()} 条规则，请先处理规则再删除",
        )

    await db.delete(doc_type)
    await db.commit()
    return {"message": "删除成功"}


# ═══════════════════════════════════════════════════════════
# 规则管理
# ═══════════════════════════════════════════════════════════

@router.get("/rules", response_model=list[RuleResponse])
async def list_rules(
    doc_type_id: int = Query(None),
    stage: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """获取规则列表。"""
    query = select(Rule).where(Rule.is_deprecated == False).order_by(Rule.sort_order)

    if doc_type_id:
        # Filter by association table
        query = query.join(rule_doc_types).where(
            rule_doc_types.c.doc_type_id == doc_type_id,
            rule_doc_types.c.rule_id == Rule.id,
        )
    if stage:
        query = query.where(Rule.stage.in_([stage, "all"]))

    # Paginate
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    rules = result.scalars().all()

    resp = []
    for r in rules:
        resp.append(await _build_rule_response(db, r))
    return resp


@router.post("/rules", response_model=RuleResponse)
async def create_rule(data: RuleCreate, db: AsyncSession = Depends(get_db)):
    """新增规则。"""
    # Verify all doc types exist
    if not data.doc_type_ids:
        raise HTTPException(status_code=422, detail="至少选择一个文档类型")
    for dt_id in data.doc_type_ids:
        dt_result = await db.execute(select(DocType).where(DocType.id == dt_id))
        if not dt_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail=f"文档类型 {dt_id} 不存在")

    rule = Rule(
        name=data.name,
        description=data.description,
        severity=data.severity,
        stage=data.stage,
        sort_order=data.sort_order,
        is_active=data.is_active,
    )
    db.add(rule)
    await db.flush()

    # Insert association records
    for dt_id in data.doc_type_ids:
        await db.execute(
            rule_doc_types.insert().values(rule_id=rule.id, doc_type_id=dt_id)
        )
    await db.commit()
    await db.refresh(rule)

    return await _build_rule_response(db, rule)


@router.put("/rules/{rule_id}", response_model=RuleResponse)
async def update_rule(rule_id: int, data: RuleUpdate, db: AsyncSession = Depends(get_db)):
    """编辑规则。"""
    result = await db.execute(select(Rule).where(Rule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")

    if data.name is not None:
        rule.name = data.name
    if data.description is not None:
        rule.description = data.description
    if data.severity is not None:
        rule.severity = data.severity
    if data.stage is not None:
        rule.stage = data.stage
    if data.sort_order is not None:
        rule.sort_order = data.sort_order
    if data.is_active is not None:
        rule.is_active = data.is_active
    if data.doc_type_ids is not None:
        if not data.doc_type_ids:
            raise HTTPException(status_code=422, detail="至少选择一个文档类型")
        await _sync_rule_doc_types(db, rule.id, data.doc_type_ids)

    await db.commit()
    await db.refresh(rule)

    return await _build_rule_response(db, rule)


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    """删除规则（已被检查引用的规则标记为废弃）。"""
    result = await db.execute(select(Rule).where(Rule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")

    # Check if used in any check results
    cr_result = await db.execute(
        select(func.count(CheckResult.id)).where(CheckResult.rule_id == rule_id)
    )
    if cr_result.scalar() > 0:
        rule.is_deprecated = True
        rule.is_active = False
        await db.commit()
        return {"message": "规则已被检查任务引用，已标记为废弃", "deprecated": True}

    # Remove association records first
    await db.execute(
        delete(rule_doc_types).where(rule_doc_types.c.rule_id == rule_id)
    )
    await db.delete(rule)
    await db.commit()
    return {"message": "删除成功", "deprecated": False}


@router.patch("/rules/{rule_id}/toggle", response_model=RuleResponse)
async def toggle_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    """启用/禁用规则切换。"""
    result = await db.execute(select(Rule).where(Rule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")

    rule.is_active = not rule.is_active
    await db.commit()
    await db.refresh(rule)

    return await _build_rule_response(db, rule)


@router.post("/rules/{rule_id}/copy", response_model=RuleResponse)
async def copy_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    """复制规则（连带关联的文档类型）。"""
    result = await db.execute(select(Rule).where(Rule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")

    # Get associated doc types
    dt_ids_result = await db.execute(
        select(rule_doc_types.c.doc_type_id).where(
            rule_doc_types.c.rule_id == rule.id
        )
    )
    dt_ids = [row[0] for row in dt_ids_result.all()]

    new_rule = Rule(
        name=f"{rule.name}(副本)",
        description=rule.description,
        severity=rule.severity,
        stage=rule.stage,
        sort_order=rule.sort_order + 1,
        is_active=False,
    )
    db.add(new_rule)
    await db.flush()

    # Copy association records
    for dt_id in dt_ids:
        await db.execute(
            rule_doc_types.insert().values(rule_id=new_rule.id, doc_type_id=dt_id)
        )
    await db.commit()
    await db.refresh(new_rule)

    return await _build_rule_response(db, new_rule)


@router.patch("/rules/batch-toggle")
async def batch_toggle_rules(data: BatchToggleRequest, db: AsyncSession = Depends(get_db)):
    """批量启用/禁用规则。"""
    for rule_id in data.rule_ids:
        result = await db.execute(select(Rule).where(Rule.id == rule_id))
        rule = result.scalar_one_or_none()
        if rule:
            rule.is_active = data.is_active
    await db.commit()
    return {"message": f"已{'启用' if data.is_active else '禁用'} {len(data.rule_ids)} 条规则"}
