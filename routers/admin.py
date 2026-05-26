"""DocCheck routes - 管理员模块（用户管理 + LLM配置 + 审计日志）"""

from __future__ import annotations
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

import bcrypt as _bcrypt


def _hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


from database import get_db
from models import User, SystemConfig, AuditLog
from schemas import (
    UserCreate, UserUpdate, UserResponse, ResetPasswordRequest,
    LLMConfigRequest, LLMConfigResponse,
    AuditLogResponse,
)
from services.audit import log_action, get_audit_logs

router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_admin(func):
    """Decorator to check admin role."""
    async def wrapper(*args, **kwargs):
        request = kwargs.get("request")
        if request:
            user = getattr(request.state, "current_user", None)
            if not user:
                raise HTTPException(status_code=401, detail="未登录")
            if "admin" not in user.get("role", "").split(","):
                raise HTTPException(status_code=403, detail="权限不足")
        return await func(*args, **kwargs)
    return wrapper


# ═══════════════════════════════════════════════════════════
# 用户管理
# ═══════════════════════════════════════════════════════════

@router.get("/users", response_model=list[UserResponse])
async def list_users(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """获取用户列表。"""
    user = getattr(request.state, "current_user", None)
    if not user or "admin" not in user.get("role", "").split(","):
        raise HTTPException(status_code=403, detail="权限不足")

    result = await db.execute(select(User).order_by(User.id))
    users = result.scalars().all()
    return [
        UserResponse(
            id=u.id, username=u.username, display_name=u.display_name,
            role=u.role, is_active=u.is_active,
            created_at=u.created_at, last_login=u.last_login,
        )
        for u in users
    ]


@router.post("/users", response_model=UserResponse)
async def create_user(
    request: Request,
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """新增用户。"""
    user = getattr(request.state, "current_user", None)
    if not user or "admin" not in user.get("role", "").split(","):
        raise HTTPException(status_code=403, detail="权限不足")

    # Check duplicate
    existing = await db.execute(select(User).where(User.username == data.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="用户名已存在")

    new_user = User(
        username=data.username,
        password_hash=_hash_password(data.password),
        display_name=data.display_name,
        role=data.role,
        is_active=True,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    await log_action(db, user["user_id"], user["username"],
                     "user_create", "user", new_user.id,
                     f"新增用户: {new_user.username}")

    return UserResponse(
        id=new_user.id, username=new_user.username,
        display_name=new_user.display_name, role=new_user.role,
        is_active=new_user.is_active,
        created_at=new_user.created_at,
    )


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    request: Request,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
):
    """编辑用户。"""
    user = getattr(request.state, "current_user", None)
    if not user or "admin" not in user.get("role", "").split(","):
        raise HTTPException(status_code=403, detail="权限不足")

    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")

    if data.display_name is not None:
        target.display_name = data.display_name
    if data.role is not None:
        target.role = data.role

    await db.commit()
    await db.refresh(target)

    return UserResponse(
        id=target.id, username=target.username,
        display_name=target.display_name, role=target.role,
        is_active=target.is_active,
        created_at=target.created_at, last_login=target.last_login,
    )


@router.patch("/users/{user_id}/toggle", response_model=UserResponse)
async def toggle_user(user_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """启用/禁用用户。"""
    user = getattr(request.state, "current_user", None)
    if not user or "admin" not in user.get("role", "").split(","):
        raise HTTPException(status_code=403, detail="权限不足")

    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")

    if target.id == user["user_id"]:
        raise HTTPException(status_code=400, detail="不能禁用自己")

    target.is_active = not target.is_active
    await db.commit()
    await db.refresh(target)

    return UserResponse(
        id=target.id, username=target.username,
        display_name=target.display_name, role=target.role,
        is_active=target.is_active,
        created_at=target.created_at, last_login=target.last_login,
    )


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    request: Request,
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """重置密码。"""
    user = getattr(request.state, "current_user", None)
    if not user or "admin" not in user.get("role", "").split(","):
        raise HTTPException(status_code=403, detail="权限不足")

    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")

    target.password_hash = _hash_password(data.new_password)
    await db.commit()

    return {"message": "密码已重置"}


# ═══════════════════════════════════════════════════════════
# LLM 配置
# ═══════════════════════════════════════════════════════════

@router.get("/config/llm", response_model=LLMConfigResponse)
async def get_llm_config(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """获取 LLM 配置。"""
    user = getattr(request.state, "current_user", None)
    if not user or "admin" not in user.get("role", "").split(","):
        raise HTTPException(status_code=403, detail="权限不足")

    config = {}
    for key in ["api_base", "api_key", "model", "timeout", "max_retries", "temperature", "max_tokens"]:
        result = await db.execute(
            select(SystemConfig).where(SystemConfig.config_key == f"llm_{key}")
        )
        cfg = result.scalar_one_or_none()
        config[key] = cfg.config_value if cfg else ""

    # Mask API key
    if config.get("api_key") and len(config["api_key"]) > 8:
        config["api_key"] = config["api_key"][:4] + "****" + config["api_key"][-4:]

    return LLMConfigResponse(
        api_base=config.get("api_base", ""),
        api_key=config.get("api_key", ""),
        model=config.get("model", ""),
        timeout=int(config.get("timeout", 60)) if config.get("timeout") else 60,
        max_retries=int(config.get("max_retries", 3)) if config.get("max_retries") else 3,
        temperature=float(config.get("temperature", 0.1)) if config.get("temperature") else 0.1,
        max_tokens=int(config.get("max_tokens", 4096)) if config.get("max_tokens") else 4096,
    )


@router.put("/config/llm")
async def save_llm_config(
    request: Request,
    data: LLMConfigRequest,
    db: AsyncSession = Depends(get_db),
):
    """保存 LLM 配置。"""
    user = getattr(request.state, "current_user", None)
    if not user or "admin" not in user.get("role", "").split(","):
        raise HTTPException(status_code=403, detail="权限不足")

    if not data.api_key and not data.api_base:
        raise HTTPException(status_code=422, detail="API Key 不能为空")

    config_map = {
        "llm_api_base": data.api_base,
        "llm_api_key": data.api_key,
        "llm_model": data.model,
        "llm_timeout": str(data.timeout),
        "llm_max_retries": str(data.max_retries),
        "llm_temperature": str(data.temperature),
        "llm_max_tokens": str(data.max_tokens),
    }

    for key, value in config_map.items():
        existing = await db.execute(
            select(SystemConfig).where(SystemConfig.config_key == key)
        )
        cfg = existing.scalar_one_or_none()
        if cfg:
            cfg.config_value = str(value)
        else:
            db.add(SystemConfig(config_key=key, config_value=str(value)))

    await db.commit()

    await log_action(db, user["user_id"], user["username"],
                     "llm_config_update", "system", 0,
                     "更新 LLM 配置")

    return {"message": "LLM 配置已保存"}


@router.post("/config/llm/test")
async def test_llm_connection(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """测试 LLM 连接。"""
    user = getattr(request.state, "current_user", None)
    if not user or "admin" not in user.get("role", "").split(","):
        raise HTTPException(status_code=403, detail="权限不足")

    # Load config
    api_base = ""
    api_key = ""
    for key in ["api_base", "api_key"]:
        result = await db.execute(
            select(SystemConfig).where(SystemConfig.config_key == f"llm_{key}")
        )
        cfg = result.scalar_one_or_none()
        if key == "api_base":
            api_base = cfg.config_value if cfg else ""
        elif key == "api_key":
            api_key = cfg.config_value if cfg else ""

    if not api_base or not api_key:
        return {"success": False, "message": "请先配置 API 地址和 Key"}

    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{api_base.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                models = [m["id"] for m in data.get("data", [])]
                return {
                    "success": True,
                    "message": "连接成功",
                    "models": models[:10],
                }
            else:
                return {
                    "success": False,
                    "message": f"连接失败: HTTP {resp.status_code}",
                }
    except Exception as e:
        return {
            "success": False,
            "message": f"连接失败: {str(e)}",
        }


# ═══════════════════════════════════════════════════════════
# 审计日志
# ═══════════════════════════════════════════════════════════

@router.get("/audit-log")
async def list_audit_logs(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action: str = Query(None),
    start: str = Query(None),
    end: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """获取审计日志。"""
    user = getattr(request.state, "current_user", None)
    if not user or "admin" not in user.get("role", "").split(","):
        raise HTTPException(status_code=403, detail="权限不足")

    logs, total = await get_audit_logs(
        db, page=page, page_size=page_size,
        action=action, start=start, end=end,
    )

    return {
        "items": [
            {
                "id": log.id,
                "user_id": log.user_id,
                "username": log.username,
                "action": log.action,
                "target_type": log.target_type,
                "target_id": log.target_id,
                "detail": log.detail,
                "ip_address": log.ip_address,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }
