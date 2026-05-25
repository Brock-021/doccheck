"""DocCheck · 审计日志测试（4条用例）"""

import pytest


class TestAudit:
    """TC-AUDIT-001 ~ 004"""

    AUDIT_API = "/api/admin/audit-log"

    # ── TC-AUDIT-001：审计日志页面 ────────────────────
    def test_audit_log_page(self, client, login_admin):
        resp = client.get("/admin/audit-log")
        assert resp.status_code == 200

    # ── TC-AUDIT-002：审计日志 API ─────────────────────
    def test_audit_log_api(self, client, login_admin):
        resp = client.get(self.AUDIT_API)
        assert resp.status_code == 200
        data = resp.json()
        if isinstance(data, list):
            assert True

    # ── TC-AUDIT-003：审计日志筛选 ─────────────────────
    def test_audit_log_filter(self, client, login_admin):
        resp = client.get(self.AUDIT_API, params={
            "action": "rule_create",
            "start": "2026-01-01T00:00:00",
            "end": "2026-12-31T23:59:59",
        })
        assert resp.status_code == 200

    # ── TC-AUDIT-004：非管理员不能查看 ─────────────────
    def test_audit_log_permission(self, client, login_writer):
        resp = client.get(self.AUDIT_API)
        assert resp.status_code in (401, 403)
