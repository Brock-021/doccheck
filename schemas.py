"""
DocCheck Pydantic schemas — 请求/响应模型
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field


# ── Auth ──────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    success: bool
    message: str
    user_id: int
    username: str
    display_name: str
    role: str


# ── DocType ──────────────────────────────────────────────

class DocTypeCreate(BaseModel):
    name: str
    sort_order: int = 0


class DocTypeUpdate(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None


class DocTypeResponse(BaseModel):
    id: int
    name: str
    sort_order: int
    rule_count: Optional[int] = 0

    class Config:
        from_attributes = True


# ── Rule ──────────────────────────────────────────────────

class RuleCreate(BaseModel):
    doc_type_ids: list[int]
    name: str
    description: str = ""
    severity: str = "must_fix"
    stage: str = "all"
    sort_order: int = 0
    is_active: bool = True


class RuleUpdate(BaseModel):
    doc_type_ids: Optional[list[int]] = None
    name: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[str] = None
    stage: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class RuleResponse(BaseModel):
    id: int
    doc_type_ids: Optional[list[int]] = None
    doc_type_names: Optional[list[str]] = None
    name: str
    description: str
    severity: str
    stage: str
    sort_order: int
    is_active: bool
    is_deprecated: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BatchToggleRequest(BaseModel):
    rule_ids: list[int]
    is_active: bool


# ── Document ──────────────────────────────────────────────

class DocumentResponse(BaseModel):
    id: int
    user_id: int
    doc_type_id: int
    doc_type_name: Optional[str] = None
    filename: str
    original_filename: Optional[str] = None
    file_size: int
    upload_time: datetime
    check_count: Optional[int] = 0
    last_check_status: Optional[str] = None
    last_check_time: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── CheckTask ─────────────────────────────────────────────

class CheckTaskResponse(BaseModel):
    id: int
    document_id: int
    stage: str
    rule_count: int
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── CheckResult ──────────────────────────────────────────

class CheckResultResponse(BaseModel):
    id: int
    check_task_id: int
    rule_id: int
    rule_name: Optional[str] = None
    rule_severity: Optional[str] = None
    compliant: Optional[str] = None
    issue: Optional[str] = None
    location: Optional[str] = None
    original_text: Optional[str] = None
    suggestion: Optional[str] = None
    review_status: str
    review_remark: Optional[str] = None

    class Config:
        from_attributes = True


# ── Report ────────────────────────────────────────────────

class ReportResponse(BaseModel):
    id: int
    check_task_id: int
    summary_json: Optional[Any] = None
    conclusion: Optional[str] = None
    conclusion_remark: Optional[str] = None
    concluded_by: Optional[int] = None
    concluded_at: Optional[datetime] = None

    # nested
    check_task: Optional[CheckTaskResponse] = None
    results: list[CheckResultResponse] = []

    class Config:
        from_attributes = True


class ReviewAction(BaseModel):
    remark: Optional[str] = None


class ConclusionRequest(BaseModel):
    conclusion: str  # pass | conditional_pass | fail
    remark: Optional[str] = None


# ── LLM Config ────────────────────────────────────────────

class LLMConfigRequest(BaseModel):
    api_base: str
    api_key: str = ""
    model: str = "gpt-3.5-turbo"
    timeout: int = 60
    max_retries: int = 3
    temperature: float = 0.1
    max_tokens: int = 4096


class LLMConfigResponse(BaseModel):
    api_base: str
    api_key: str  # masked
    model: str
    timeout: int
    max_retries: int
    temperature: float
    max_tokens: int


# ── User ──────────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str
    password: str
    display_name: str = ""
    role: str = "writer"


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    role: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    is_active: bool
    created_at: Optional[datetime] = None
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True


class ResetPasswordRequest(BaseModel):
    new_password: str


# ── Audit Log ─────────────────────────────────────────────

class AuditLogResponse(BaseModel):
    id: int
    user_id: int
    username: str
    action: str
    target_type: Optional[str] = None
    target_id: Optional[int] = None
    detail: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ── Pagination ────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int
    total_pages: int
