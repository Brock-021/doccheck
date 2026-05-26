"""
DocCheck · FastAPI 主入口

启动方式：
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import logging
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends, Query
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


# ── Document upload page ──────────────────────────────────────

@app.get("/documents/upload", response_class=HTMLResponse)
async def document_upload_page(request: Request, db: AsyncSession = Depends(get_db)):
    """上传检查页面。"""
    user = request.state.current_user
    if not user:
        return RedirectResponse(url="/login")
    from models import DocType
    from sqlalchemy import select
    result = await db.execute(select(DocType).order_by(DocType.sort_order))
    doc_types = result.scalars().all()
    return templates.TemplateResponse(request, "documents/upload.html", {
        "current_user": user,
        "doc_types": [{"id": t.id, "name": t.name} for t in doc_types],
    })


# ── Document list page ────────────────────────────────────────

@app.get("/documents", response_class=HTMLResponse)
async def document_list_page(request: Request):
    """文档历史列表页面。"""
    user = request.state.current_user
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request, "documents/list.html", {
        "current_user": user,
    })


# ── Report detail page ────────────────────────────────────────

@app.get("/reports/{report_id}", response_class=HTMLResponse)
async def report_detail_page(request: Request, report_id: int, db: AsyncSession = Depends(get_db)):
    """报告详情页面。"""
    user = request.state.current_user
    if not user:
        return RedirectResponse(url="/login")

    from models import Report, CheckTask, Document, CheckResult, Rule, DocType, User as UserModel
    from sqlalchemy import select

    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        return templates.TemplateResponse(request, "base.html", {
            "current_user": user,
            "content": "<div class='empty-state'><p>报告不存在</p></div>",
        }, status_code=404)

    ct_result = await db.execute(select(CheckTask).where(CheckTask.id == report.check_task_id))
    task = ct_result.scalar_one_or_none()

    doc_result = await db.execute(select(Document).where(Document.id == task.document_id))
    doc = doc_result.scalar_one_or_none()

    dt_result = await db.execute(select(DocType).where(DocType.id == doc.doc_type_id))
    dt = dt_result.scalar_one_or_none()

    uploader_result = await db.execute(select(UserModel).where(UserModel.id == doc.user_id))
    uploader = uploader_result.scalar_one_or_none()

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
            "rule_name": rule.name if rule else "未知规则",
            "severity": rule.severity if rule else "must_fix",
            "compliant": r.compliant,
            "issue": r.issue,
            "location": r.location,
            "original_text": r.original_text,
            "suggestion": r.suggestion,
            "review_status": r.review_status,
            "review_remark": r.review_remark,
        })

    passed = sum(1 for r in results_data if r["compliant"])
    failed = sum(1 for r in results_data if not r["compliant"])
    confirmed = sum(1 for r in results_data if r["review_status"] == "confirmed")
    rejected = sum(1 for r in results_data if r["review_status"] == "rejected")

    return templates.TemplateResponse(request, "reports/detail.html", {
        "current_user": user,
        "report": {
            "id": report.id,
            "conclusion": report.conclusion,
            "conclusion_remark": report.conclusion_remark,
            "concluded_at": report.concluded_at,
        },
        "document": {
            "filename": doc.original_filename or doc.filename if doc else "未知",
            "doc_type_name": dt.name if dt else "-",
            "uploader": uploader.display_name if uploader else "未知",
            "upload_time": doc.upload_time if doc else None,
        },
        "task": {
            "id": task.id,
            "stage": task.stage,
            "rule_count": task.rule_count,
            "status": task.status,
            "created_at": task.created_at,
            "completed_at": task.completed_at,
        },
        "results": results_data,
        "summary": {
            "total": len(results_data),
            "passed": passed,
            "failed": failed,
            "confirmed": confirmed,
            "rejected": rejected,
        },
    })


# ── Admin: Rule management pages ──────────────────────────────

@app.get("/admin/rules", response_class=HTMLResponse)
async def admin_rules_page(request: Request, db: AsyncSession = Depends(get_db)):
    """规则管理列表页面。"""
    user = request.state.current_user
    if not user or "admin" not in user.get("role", "").split(","):
        return RedirectResponse(url="/login")
    from models import DocType
    from sqlalchemy import select
    dt_result = await db.execute(select(DocType).order_by(DocType.sort_order))
    doc_types = dt_result.scalars().all()
    return templates.TemplateResponse(request, "rules/list.html", {
        "current_user": user,
        "doc_types": [{"id": t.id, "name": t.name} for t in doc_types],
        "rules": [],
        "active_doc_type": None,
    })


@app.get("/admin/rules/new", response_class=HTMLResponse)
async def admin_rules_new_page(request: Request, db: AsyncSession = Depends(get_db)):
    """新增规则页面。"""
    user = request.state.current_user
    if not user or "admin" not in user.get("role", "").split(","):
        return RedirectResponse(url="/login")
    from models import DocType
    from sqlalchemy import select
    dt_result = await db.execute(select(DocType).order_by(DocType.sort_order))
    doc_types = dt_result.scalars().all()
    return templates.TemplateResponse(request, "rules/form.html", {
        "current_user": user,
        "doc_types": [{"id": t.id, "name": t.name} for t in doc_types],
        "rule": None,
        "is_edit": False,
    })


# ── Review page ─────────────────────────────────────────────

@app.get("/reviews/{report_id}", response_class=HTMLResponse)
async def review_page(request: Request, report_id: int, db: AsyncSession = Depends(get_db)):
    """审核页面。"""
    user = request.state.current_user
    if not user:
        return RedirectResponse(url="/login")
    user_roles = user.get("role", "").split(",")
    if "admin" not in user_roles and "reviewer" not in user_roles:
        return RedirectResponse(url="/")

    from models import Report, CheckTask, Document, CheckResult, Rule, DocType, User as UserModel
    from sqlalchemy import select

    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        return HTMLResponse("报告不存在", status_code=404)

    ct_result = await db.execute(select(CheckTask).where(CheckTask.id == report.check_task_id))
    task = ct_result.scalar_one_or_none()

    doc_result = await db.execute(select(Document).where(Document.id == task.document_id))
    doc = doc_result.scalar_one_or_none()

    dt_result = await db.execute(select(DocType).where(DocType.id == doc.doc_type_id))
    dt = dt_result.scalar_one_or_none()

    uploader_result = await db.execute(select(UserModel).where(UserModel.id == doc.user_id))
    uploader = uploader_result.scalar_one_or_none()

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
            "rule_name": rule.name if rule else "未知规则",
            "severity": rule.severity if rule else "must_fix",
            "compliant": r.compliant,
            "issue": r.issue,
            "location": r.location,
            "original_text": r.original_text,
            "suggestion": r.suggestion,
            "review_status": r.review_status,
            "review_remark": r.review_remark,
        })

    passed = sum(1 for r in results_data if r["compliant"] == "true")
    failed = sum(1 for r in results_data if r["compliant"] != "true")
    confirmed = sum(1 for r in results_data if r["review_status"] == "confirmed")
    rejected = sum(1 for r in results_data if r["review_status"] == "rejected")

    return templates.TemplateResponse(request, "reviews/review.html", {
        "current_user": user,
        "report": {
            "id": report.id,
            "conclusion": report.conclusion,
            "conclusion_remark": report.conclusion_remark,
            "concluded_at": report.concluded_at,
        },
        "document": {
            "filename": doc.original_filename or doc.filename if doc else "未知",
            "doc_type_name": dt.name if dt else "-",
            "uploader": uploader.display_name if uploader else "未知",
            "upload_time": doc.upload_time if doc else None,
        },
        "task": {
            "id": task.id,
            "stage": task.stage,
            "rule_count": task.rule_count,
            "status": task.status,
            "created_at": task.created_at,
            "completed_at": task.completed_at,
        },
        "summary": {
            "total": len(results_data),
            "passed": passed,
            "failed": failed,
            "confirmed": confirmed,
            "rejected": rejected,
        },
        "results": results_data,
    })


# ── Document compare page ──────────────────────────────────

@app.get("/documents/{doc_id}/compare", response_class=HTMLResponse)
async def document_compare_page(
    request: Request,
    doc_id: int,
    v1: int = Query(...),
    v2: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """历史检查对比页面。"""
    user = request.state.current_user
    if not user:
        return RedirectResponse(url="/login")

    import httpx
    session_id = request.cookies.get("session", "")
    api_url = f"http://127.0.0.1:8001/api/documents/{doc_id}/compare?v1={v1}&v2={v2}"
    try:
        resp = httpx.get(api_url, cookies={"session": session_id}, timeout=10)
        data = resp.json()
    except Exception as e:
        return templates.TemplateResponse(request, "documents/compare.html", {
            "current_user": user,
            "error": str(e),
            "filename": "加载失败",
            "v1": {"created_at": ""},
            "v2": {"created_at": ""},
            "summary": {"fixed_issues": 0, "new_issues": 0, "still_issues": 0, "unchanged_pass": 0, "total": 0},
            "results": [],
        })

    return templates.TemplateResponse(request, "documents/compare.html", {
        "current_user": user,
        "filename": data.get("filename", "未知"),
        "v1": data.get("v1", {}),
        "v2": data.get("v2", {}),
        "summary": data.get("summary", {}),
        "results": data.get("results", []),
    })


@app.get("/admin/rules/{rule_id}/edit", response_class=HTMLResponse)
async def admin_rules_edit_page(request: Request, rule_id: int, db: AsyncSession = Depends(get_db)):
    """编辑规则页面。"""
    user = request.state.current_user
    if not user or "admin" not in user.get("role", "").split(","):
        return RedirectResponse(url="/login")
    from models import Rule, DocType
    from sqlalchemy import select
    r_result = await db.execute(select(Rule).where(Rule.id == rule_id))
    rule = r_result.scalar_one_or_none()
    if not rule:
        return RedirectResponse(url="/admin/rules")
    dt_result = await db.execute(select(DocType).order_by(DocType.sort_order))
    doc_types = dt_result.scalars().all()
    return templates.TemplateResponse(request, "rules/form.html", {
        "current_user": user,
        "doc_types": [{"id": t.id, "name": t.name} for t in doc_types],
        "rule": {
            "id": rule.id,
            "name": rule.name,
            "description": rule.description,
            "doc_type_id": rule.doc_type_id,
            "severity": rule.severity,
            "stage": rule.stage,
            "sort_order": rule.sort_order,
            "is_active": rule.is_active,
        },
        "is_edit": True,
    })


# ── Admin: User management page ─────────────────────────

@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request):
    """用户管理页面。"""
    user = request.state.current_user
    if not user or "admin" not in user.get("role", "").split(","):
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request, "admin/users.html", {
        "current_user": user,
    })


# ── Admin: LLM config page ─────────────────────────────

@app.get("/admin/llm-config", response_class=HTMLResponse)
async def admin_llm_config_page(request: Request):
    """LLM 配置页面。"""
    user = request.state.current_user
    if not user or "admin" not in user.get("role", "").split(","):
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request, "admin/llm_config.html", {
        "current_user": user,
    })


# ── Admin: Doc types page ────────────────────────────

@app.get("/admin/doc-types", response_class=HTMLResponse)
async def admin_doc_types_page(request: Request):
    """文档类型管理页面。"""
    user = request.state.current_user
    if not user or "admin" not in user.get("role", "").split(","):
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request, "admin/doc_types.html", {
        "current_user": user,
    })


# ── Admin: Audit log page ──────────────────────────────

@app.get("/admin/audit-log", response_class=HTMLResponse)
async def admin_audit_log_page(request: Request):
    """审计日志页面。"""
    user = request.state.current_user
    if not user or "admin" not in user.get("role", "").split(","):
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request, "admin/audit_log.html", {
        "current_user": user,
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
