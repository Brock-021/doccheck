"""DocCheck · 权限控制测试（10条用例）"""

import pytest


class TestPermissions:
    """TC-PERM-001 ~ 010"""

    # ── TC-PERM-001：编写者不能访问规则管理 ────────────
    def test_writer_no_rules_page(self, client, login_writer):
        resp = client.get("/admin/rules", follow_redirects=False)
        assert resp.status_code in (302, 403)

    def test_writer_no_rules_api(self, client, login_writer):
        resp = client.get("/api/admin/rules")
        assert resp.status_code in (401, 403)

    # ── TC-PERM-002：编写者不能访问用户管理 ────────────
    def test_writer_no_users_page(self, client, login_writer):
        resp = client.get("/admin/users", follow_redirects=False)
        assert resp.status_code in (302, 403)

    def test_writer_no_users_api(self, client, login_writer):
        resp = client.get("/api/admin/users")
        assert resp.status_code in (401, 403)

    # ── TC-PERM-003：编写者不能访问 LLM 配置 ──────────
    def test_writer_no_llm_config(self, client, login_writer):
        resp = client.get("/admin/llm-config", follow_redirects=False)
        assert resp.status_code in (302, 403)

    # ── TC-PERM-004：审核人员不能上传文档 ──────────────
    def test_reviewer_no_upload_page(self, client, login_reviewer, seed_doc_types):
        resp = client.get("/documents/upload", follow_redirects=False)
        assert resp.status_code in (302, 403)

    def test_reviewer_no_upload_api(self, client, login_reviewer):
        resp = client.get("/api/documents/upload")
        assert resp.status_code in (401, 403)

    # ── TC-PERM-005：规则管理员不能审核 ────────────────
    def test_rule_admin_no_review(self, client, login_rule_admin, seed_doc_types, seed_rules):
        resp = client.get("/reviews/1", follow_redirects=False)
        assert resp.status_code in (302, 403)

    # ── TC-PERM-006：管理员拥有所有权限 ────────────────
    def test_admin_all_access(self, client, login_admin):
        # Can access admin pages
        for path in ["/admin/rules", "/admin/users", "/admin/llm-config",
                      "/admin/doc-types", "/documents/upload"]:
            resp = client.get(path, follow_redirects=False)
            assert resp.status_code == 200, f"Admin can't access {path}: {resp.status_code}"

        # Can access review
        resp = client.get("/reviews/1")
        assert resp.status_code in (200, 404)  # 404 is ok if report doesn't exist

    # ── TC-PERM-007：接口直接调用越权 ──────────────────
    def test_unauthorized_api_call(self, client, login_writer):
        # Writer trying to create a rule via API
        resp = client.post("/api/admin/rules", json={
            "name": "hack", "description": "hack",
            "severity": "must_fix", "doc_type_id": 1,
        })
        assert resp.status_code in (401, 403)

    # ── TC-PERM-008：多角色用户功能全面 ────────────────
    def test_multi_role_user(self, client, seed_users):
        # Login as multi-role user (writer + reviewer)
        resp = client.post("/api/auth/login", data={
            "username": "multi",
            "password": "multi123",
        })
        assert resp.status_code == 200

        # Should access both writer and reviewer pages
        resp = client.get("/documents/upload", follow_redirects=False)
        assert resp.status_code == 200, f"Multi-role can't access upload: {resp.status_code}"

        resp = client.get("/reviews", follow_redirects=False)
        assert resp.status_code in (200, 404)

    # ── TC-PERM-009：API Key 不在前端暴露 ──────────────
    def test_api_key_not_exposed(self, client, login_admin):
        resp = client.get("/admin/llm-config")
        assert resp.status_code == 200
        # API Key should not appear in HTML source
        html = resp.text.lower()
        assert "sk-" not in html, "API Key found in page source!"

    # ── TC-PERM-010：禁用用户不能登录 ──────────────────
    def test_disabled_user_login(self, client, seed_users):
        resp = client.post("/api/auth/login", data={
            "username": "disabled_user",
            "password": "disabled123",
        })
        assert resp.status_code == 403
