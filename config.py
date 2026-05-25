"""
DocCheck 配置模块
从环境变量或配置文件读取设置。
"""

import os
import json
from pathlib import Path

# ── 基础路径 ────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
REPORT_DIR = BASE_DIR / "reports"
DB_PATH = BASE_DIR / "doccheck.db"
CONFIG_FILE = BASE_DIR / "config.json"

# ── 创建目录 ────────────────────────────────────────────
UPLOAD_DIR.mkdir(exist_ok=True)
REPORT_DIR.mkdir(exist_ok=True)

# ── Session ─────────────────────────────────────────────
SECRET_KEY = os.getenv("DOCCHECK_SECRET_KEY", "doccheck-dev-secret-key-change-in-production")
SESSION_EXPIRE_MINUTES = int(os.getenv("DOCCHECK_SESSION_EXPIRE", 60 * 8))  # 8h default

# ── 数据库 ──────────────────────────────────────────────
DATABASE_URL = os.getenv("DOCCHECK_DATABASE_URL", f"sqlite+aiosqlite:///{DB_PATH}")

# ── 上传限制 ───────────────────────────────────────────
MAX_UPLOAD_SIZE = int(os.getenv("DOCCHECK_MAX_UPLOAD_SIZE", 50 * 1024 * 1024))  # 50MB
ALLOWED_EXTENSIONS = {".docx"}

# ── LLM 配置（从 system_config 表读取，此为默认值）──────
DEFAULT_LLM_CONFIG = {
    "api_base": "http://localhost:8000/v1",
    "api_key": "",
    "model": "gpt-3.5-turbo",
    "timeout": 60,
    "max_retries": 3,
    "temperature": 0.1,
    "max_tokens": 4096,
}


def load_llm_config() -> dict:
    """从 system_config 表加载 LLM 配置（开发阶段返回默认值）。"""
    # 实际项目启动时会通过 DB 加载，这里先返回默认
    return dict(DEFAULT_LLM_CONFIG)


def save_llm_config(config: dict):
    """保存 LLM 配置到 system_config 表。"""
    # 实际写入 DB，由 routers/admin.py 调用
    pass
