"""
DocCheck · FastAPI 主入口

启动方式：
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import logging
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import jinja2
from starlette.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import bcrypt as _bcrypt


def _hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def _verify_password(password: str, hashed: str) -> bool:
    return _bcrypt.checkpw(password.encode(), hashed.encode())

from database import init_db, get_db, async_session_factory
from models import User

# ── Logging ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("doccheck")

# ── Templates ────────────────────────────────────────────
import jinja2
from starlette.templating import Jinja2Templates
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Jinja2 3.1.6 compatibility: use directory-based Jinja2Templates
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App startup / shutdown."""
    logger.info("DocCheck starting up...")
    await init_db()
    await seed_default_admin()
    logger.info("DocCheck ready!")
    yield
    logger.info("DocCheck shutting down...")


app = FastAPI(title="DocCheck", version="1.0.0", lifespan=lifespan)
app.state.templates = templates

# ── Static files ─────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

# ── Session store ────────────────────────────────────────
app.state.sessions = {}


async def seed_default_admin():
    """Insert default admin if not exists."""
    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.username == "admin"))
        if not result.scalar_one_or_none():
            admin = User(
                username="admin",
                password_hash=_hash_password("admin123"),
                display_name="系统管理员",
                role="admin",
                is_active=True,
            )
            db.add(admin)
            await db.commit()
            logger.info("Default admin created: admin / admin123")


# ── Session middleware ────────────────────────────────────

@app.middleware("http")
async def session_middleware(request: Request, call_next):
    """Load user from session cookie."""
    session_id = request.cookies.get("session")
    request.state.current_user = None

    if session_id and hasattr(app.state, "sessions"):
        session = app.state.sessions.get(session_id)
        if session:
            if session["expires"] > datetime.utcnow():
                request.state.current_user = session["data"]
            else:
                app.state.sessions.pop(session_id, None)

    # Check authentication for protected paths
    protected_paths = ["/documents", "/admin", "/reports", "/reviews"]
    path = request.url.path
    is_protected = any(path.startswith(p) for p in protected_paths) or path == "/"

    if is_protected and not request.state.current_user and path != "/login":
        if path.startswith("/api/"):
            from fastapi.responses import JSONResponse
            if request.method != "GET" or not path.startswith("/api/auth/"):
                return JSONResponse(status_code=401, content={"detail": "未登录"})
        elif path not in ("/login", "/"):
            return RedirectResponse(url="/login")

    response = await call_next(request)
    return response


# ── Page routes ───────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """登录页面。"""
    if request.state.current_user:
        return RedirectResponse(url="/")
    return templates.TemplateResponse(request, "login.html", {
        "current_user": None,
    })


@app.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request, db: AsyncSession = Depends(get_db)):
    """工作台首页。"""
    user = request.state.current_user
    if not user:
        return RedirectResponse(url="/login")

    # Gather stats
    doc_count = 0
    pending_review = 0
    rule_count = 0
    recent_checks = 0
    recent_docs = []

    try:
        from models import Document, CheckTask, Rule, CheckResult, Report, DocType
        from sqlalchemy import func

        user_roles = user.get("role", "").split(",")

        # Document count
        doc_query = select(func.count(Document.id))
        if "admin" not in user_roles:
            doc_query = doc_query.where(Document.user_id == user["user_id"])
        dc_result = await db.execute(doc_query)
        doc_count = dc_result.scalar() or 0

        # Pending review count (only for reviewers/admin)
        if "reviewer" in user_roles or "admin" in user_roles:
            pr_result = await db.execute(
                select(func.count(CheckResult.id))
                .where(CheckResult.review_status == "pending")
            )
            pending_review = pr_result.scalar() or 0

        # Active rule count
        rl_result = await db.execute(
            select(func.count(Rule.id)).where(
                Rule.is_active == True, Rule.is_deprecated == False,
            )
        )
        rule_count = rl_result.scalar() or 0

        # Recent documents
        doc_query2 = select(Document)
        if "admin" not in user_roles:
            doc_query2 = doc_query2.where(Document.user_id == user["user_id"])
        doc_query2 = doc_query2.order_by(Document.upload_time.desc()).limit(10)
        docs_result = await db.execute(doc_query2)
        docs = docs_result.scalars().all()

        for doc in docs:
            dt_result = await db.execute(select(DocType).where(DocType.id == doc.doc_type_id))
            dt = dt_result.scalar_one_or_none()

            ct_result = await db.execute(
                select(CheckTask).where(CheckTask.document_id == doc.id)
                .order_by(CheckTask.created_at.desc()).limit(1)
            )
            ct = ct_result.scalar_one_or_none()

            report_id = None
            if ct:
                rp_result = await db.execute(
                    select(Report).where(Report.check_task_id == ct.id)
                )
                rp = rp_result.scalar_one_or_none()
                report_id = rp.id if rp else None

            recent_docs.append({
                "filename": doc.original_filename or doc.filename,
                "doc_type_name": dt.name if dt else "-",
                "last_check_time": ct.created_at.strftime("%Y-%m-%d %H:%M") if ct else doc.upload_time.strftime("%Y-%m-%d %H:%M"),
                "last_check_status": ct.status if ct else None,
                "last_report_id": report_id,
                "upload_time": doc.upload_time,
            })
            recent_checks += 1
    except Exception as e:
        logger.warning(f"Dashboard stats error: {e}")

    return templates.TemplateResponse(request, "dashboard.html", {
        "request": request,
        "current_user": user,
        "role_list": user.get("role", "").split(",") if user else [],
        "doc_count": doc_count,
        "pending_review": pending_review,
        "rule_count": rule_count,
        "recent_checks": recent_checks,
        "recent_docs": recent_docs,
    })


# ── Include routers ───────────────────────────────────────

from routers import auth, rules, documents, reports, reviews, admin

app.include_router(auth.router)
app.include_router(rules.router)
app.include_router(documents.router)
app.include_router(reports.router)
app.include_router(reviews.router)
app.include_router(admin.router)


# ── Health ────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "DocCheck", "version": "1.0.0"}


# ── Main ──────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
