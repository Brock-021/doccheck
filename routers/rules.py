"""DocCheck routes - 规则管理 + 文档类型管理"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import DocType, Rule, CheckResult
from schemas import (
    DocTypeCreate, DocTypeUpdate, DocTypeResponse,
    RuleCreate, RuleUpdate, RuleResponse, BatchToggleRequest,
)
from services.audit import log_action

router = APIRouter(prefix="/api/admin", tags=["admin"])


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
    # Attach rule count
    resp = []
    for t in types:
        count_result = await db.execute(
            select(func.count(Rule.id)).where(
                Rule.doc_type_id == t.id,
                Rule.is_deprecated == False,
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
        select(func.count(Rule.id)).where(
            Rule.doc_type_id == type_id, Rule.is_deprecated == False,
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

    # Check rules
    count_result = await db.execute(
        select(func.count(Rule.id)).where(
            Rule.doc_type_id == type_id, Rule.is_deprecated == False,
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
        query = query.where(Rule.doc_type_id == doc_type_id)
    if stage:
        query = query.where(Rule.stage.in_([stage, "all"]))

    # Paginate
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    rules = result.scalars().all()

    resp = []
    for r in rules:
        dt_result = await db.execute(select(DocType).where(DocType.id == r.doc_type_id))
        dt = dt_result.scalar_one_or_none()
        resp.append(RuleResponse(
            id=r.id, doc_type_id=r.doc_type_id,
            doc_type_name=dt.name if dt else None,
            name=r.name, description=r.description,
            severity=r.severity, stage=r.stage,
            sort_order=r.sort_order, is_active=r.is_active,
            is_deprecated=r.is_deprecated, created_at=r.created_at,
        ))
    return resp


@router.post("/rules", response_model=RuleResponse)
async def create_rule(data: RuleCreate, db: AsyncSession = Depends(get_db)):
    """新增规则。"""
    # Verify doc type exists
    dt_result = await db.execute(select(DocType).where(DocType.id == data.doc_type_id))
    if not dt_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="文档类型不存在")

    rule = Rule(
        doc_type_id=data.doc_type_id,
        name=data.name,
        description=data.description,
        severity=data.severity,
        stage=data.stage,
        sort_order=data.sort_order,
        is_active=data.is_active,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)

    dt_result = await db.execute(select(DocType).where(DocType.id == rule.doc_type_id))
    dt = dt_result.scalar_one_or_none()
    return RuleResponse(
        id=rule.id, doc_type_id=rule.doc_type_id,
        doc_type_name=dt.name if dt else None,
        name=rule.name, description=rule.description,
        severity=rule.severity, stage=rule.stage,
        sort_order=rule.sort_order, is_active=rule.is_active,
        is_deprecated=rule.is_deprecated, created_at=rule.created_at,
    )


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
    if data.doc_type_id is not None:
        rule.doc_type_id = data.doc_type_id

    await db.commit()
    await db.refresh(rule)

    dt_result = await db.execute(select(DocType).where(DocType.id == rule.doc_type_id))
    dt = dt_result.scalar_one_or_none()
    return RuleResponse(
        id=rule.id, doc_type_id=rule.doc_type_id,
        doc_type_name=dt.name if dt else None,
        name=rule.name, description=rule.description,
        severity=rule.severity, stage=rule.stage,
        sort_order=rule.sort_order, is_active=rule.is_active,
        is_deprecated=rule.is_deprecated, created_at=rule.created_at,
    )


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

    dt_result = await db.execute(select(DocType).where(DocType.id == rule.doc_type_id))
    dt = dt_result.scalar_one_or_none()
    return RuleResponse(
        id=rule.id, doc_type_id=rule.doc_type_id,
        doc_type_name=dt.name if dt else None,
        name=rule.name, description=rule.description,
        severity=rule.severity, stage=rule.stage,
        sort_order=rule.sort_order, is_active=rule.is_active,
        is_deprecated=rule.is_deprecated, created_at=rule.created_at,
    )


@router.post("/rules/{rule_id}/copy", response_model=RuleResponse)
async def copy_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    """复制规则。"""
    result = await db.execute(select(Rule).where(Rule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")

    new_rule = Rule(
        doc_type_id=rule.doc_type_id,
        name=f"{rule.name}(副本)",
        description=rule.description,
        severity=rule.severity,
        stage=rule.stage,
        sort_order=rule.sort_order + 1,
        is_active=False,
    )
    db.add(new_rule)
    await db.commit()
    await db.refresh(new_rule)

    dt_result = await db.execute(select(DocType).where(DocType.id == new_rule.doc_type_id))
    dt = dt_result.scalar_one_or_none()
    return RuleResponse(
        id=new_rule.id, doc_type_id=new_rule.doc_type_id,
        doc_type_name=dt.name if dt else None,
        name=new_rule.name, description=new_rule.description,
        severity=new_rule.severity, stage=new_rule.stage,
        sort_order=new_rule.sort_order, is_active=new_rule.is_active,
        is_deprecated=new_rule.is_deprecated, created_at=new_rule.created_at,
    )


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
