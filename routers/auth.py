"""DocCheck routes - 认证模块"""

import secrets
from datetime import datetime, timedelta

import bcrypt as _bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User
from services.audit import log_action
from config import SESSION_EXPIRE_MINUTES

router = APIRouter(tags=["auth"])


def get_current_user(request: Request):
    """从 session 获取当前用户（同步 helper，用于模板渲染）。"""
    user = getattr(request.state, "current_user", None)
    return user


def require_role(*roles):
    """权限校验装饰器，返回依赖函数。"""
    async def role_checker(request: Request):
        user = get_current_user(request)
        if not user:
            raise HTTPException(status_code=302, headers={"Location": "/login"})
        user_roles = user.get("role", "").split(",")
        if "admin" not in user_roles and not any(r in user_roles for r in roles):
            raise HTTPException(status_code=403, detail="权限不足")
        return user
    return role_checker


@router.post("/api/auth/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """用户登录。"""
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if not user:
        return templates_login(request, error="用户名或密码错误")

    if not user.is_active:
        return templates_login(request, error="账户已被禁用，请联系管理员")

    if not _bcrypt.checkpw(password.encode(), user.password_hash.encode()):
        return templates_login(request, error="用户名或密码错误")

    # Update last login
    user.last_login = datetime.now()
    await db.commit()

    # Create session
    session_id = secrets.token_hex(32)
    session_data = {
        "user_id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
    }

    # Store in request.app state (simple in-memory session)
    if not hasattr(request.app.state, "sessions"):
        request.app.state.sessions = {}
    request.app.state.sessions[session_id] = {
        "data": session_data,
        "expires": datetime.now() + timedelta(minutes=SESSION_EXPIRE_MINUTES),
    }

    from config import UPLOAD_DIR
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key="session",
        value=session_id,
        max_age=SESSION_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="lax",
    )

    await log_action(db, user.id, user.username, "login", "user", user.id,
                     f"用户 {user.username} 登录")
    return response


def templates_login(request: Request, error: str = None) -> HTMLResponse:
    """渲染登录页。"""
    from starlette.templating import _TemplateResponse
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "login.html", {
        "error": error,
        "current_user": None,
    })


@router.post("/api/auth/logout")
@router.get("/api/auth/logout")
async def logout(request: Request, db: AsyncSession = Depends(get_db)):
    """登出。"""
    session_id = request.cookies.get("session")
    if session_id and hasattr(request.app.state, "sessions"):
        request.app.state.sessions.pop(session_id, None)

    user = get_current_user(request)
    if user:
        await log_action(db, user["user_id"], user["username"], "logout")

    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session")
    return response
