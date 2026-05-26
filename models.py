"""
DocCheck 数据库模型
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, Float, DateTime, ForeignKey, JSON
)
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    display_name = Column(String(128), nullable=False, default="")
    role = Column(String(64), nullable=False, default="writer")
    # role: admin | reviewer | writer | rule_admin | or comma-separated: "writer,reviewer"
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    last_login = Column(DateTime, nullable=True)

    documents = relationship("Document", back_populates="user")


class DocType(Base):
    __tablename__ = "doc_types"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), unique=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    rules = relationship("Rule", back_populates="doc_type")


class Rule(Base):
    __tablename__ = "rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_type_id = Column(Integer, ForeignKey("doc_types.id"), nullable=False)
    name = Column(String(256), nullable=False)
    description = Column(Text, nullable=False, default="")
    severity = Column(String(32), nullable=False, default="must_fix")
    # severity: must_fix | suggest
    stage = Column(String(32), nullable=False, default="all")
    # stage: all | initial | final
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_deprecated = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    doc_type = relationship("DocType", back_populates="rules")
    check_results = relationship("CheckResult", back_populates="rule")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    doc_type_id = Column(Integer, ForeignKey("doc_types.id"), nullable=False)
    filename = Column(String(256), nullable=False)
    file_path = Column(String(512), nullable=False)
    file_size = Column(Integer, default=0)
    upload_time = Column(DateTime, default=datetime.now)
    original_filename = Column(String(256), nullable=True)

    user = relationship("User", back_populates="documents")
    doc_type = relationship("DocType")
    check_tasks = relationship("CheckTask", back_populates="document",
                                order_by="CheckTask.created_at.desc()")


class CheckTask(Base):
    __tablename__ = "check_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    stage = Column(String(32), default="initial")
    rule_count = Column(Integer, default=0)
    status = Column(String(32), default="pending")
    # status: pending | running | done | failed
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    completed_at = Column(DateTime, nullable=True)

    document = relationship("Document", back_populates="check_tasks")
    check_results = relationship("CheckResult", back_populates="check_task",
                                  cascade="all, delete-orphan")
    report = relationship("Report", back_populates="check_task", uselist=False)


class CheckResult(Base):
    __tablename__ = "check_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    check_task_id = Column(Integer, ForeignKey("check_tasks.id"), nullable=False)
    rule_id = Column(Integer, ForeignKey("rules.id"), nullable=False)
    compliant = Column(String(32), nullable=True)
    # compliant: true | false | null(unknown)
    issue = Column(Text, nullable=True)
    location = Column(String(256), nullable=True)
    original_text = Column(Text, nullable=True)
    suggestion = Column(Text, nullable=True)
    review_status = Column(String(32), default="pending")
    # review_status: pending | confirmed | rejected | ignored
    review_remark = Column(Text, nullable=True)
    reviewer_id = Column(Integer, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    check_task = relationship("CheckTask", back_populates="check_results")
    rule = relationship("Rule", back_populates="check_results")


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    check_task_id = Column(Integer, ForeignKey("check_tasks.id"), nullable=False, unique=True)
    summary_json = Column(JSON, nullable=True)
    conclusion = Column(String(32), nullable=True)
    # conclusion: pass | conditional_pass | fail | null
    conclusion_remark = Column(Text, nullable=True)
    concluded_by = Column(Integer, nullable=True)
    concluded_at = Column(DateTime, nullable=True)
    exported = Column(Boolean, default=False)

    check_task = relationship("CheckTask", back_populates="report")


class SystemConfig(Base):
    __tablename__ = "system_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_key = Column(String(128), unique=True, nullable=False)
    config_value = Column(Text, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    username = Column(String(64), nullable=False)
    action = Column(String(64), nullable=False)
    target_type = Column(String(64), nullable=True)
    target_id = Column(Integer, nullable=True)
    detail = Column(Text, nullable=True)
    ip_address = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
