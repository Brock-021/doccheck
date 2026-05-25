"""DocCheck · 用户管理测试（8条用例）"""

import pytest


class TestUsers:
    """TC-USER-001 ~ 008"""

    USERS_API = "/api/admin/users"

    # ── TC-USER-001：用户列表 ──────────────────────────
    def test_user_list(self, client, login_admin, seed_users):
        resp = client.get(self.USERS_API)
        assert resp.status_code == 200
        users = resp.json() if isinstance(resp.json(), list) else resp.json().get("items", [])
        assert len(users) >= 5

    # ── TC-USER-002：新增用户 ──────────────────────────
    def test_create_user(self, client, login_admin):
        resp = client.post(self.USERS_API, json={
            "username": "newuser",
            "password": "newpass123",
            "display_name": "新用户",
            "role": "writer",
        })
        assert resp.status_code == 200
        assert resp.json()["username"] == "newuser"

    # ── TC-USER-003：编辑用户 ──────────────────────────
    def test_edit_user(self, client, login_admin, seed_users):
        resp = client.put(f"{self.USERS_API}/1", json={
            "display_name": "管理员（已修改）",
            "role": "admin",
        })
        assert resp.status_code == 200

    # ── TC-USER-004：禁用用户 ──────────────────────────
    def test_disable_user(self, client, login_admin, seed_users):
        resp = client.patch(f"{self.USERS_API}/3/toggle")
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    # ── TC-USER-005：启用用户 ──────────────────────────
    def test_enable_user(self, client, login_admin, seed_users):
        # First disable
        client.patch(f"{self.USERS_API}/3/toggle")
        # Then enable
        resp = client.patch(f"{self.USERS_API}/3/toggle")
        assert resp.status_code == 200
        assert resp.json()["is_active"] is True

    # ── TC-USER-006：重置密码 ──────────────────────────
    def test_reset_password(self, client, login_admin, seed_users):
        resp = client.post(f"{self.USERS_API}/3/reset-password", json={
            "new_password": "newpass456",
        })
        assert resp.status_code == 200

        # Verify new password works
        client.cookies.clear()
        resp = client.post("/api/auth/login", data={
            "username": "writer",
            "password": "newpass456",
        })
        assert resp.status_code == 200

    # ── TC-USER-007：用户名重复 ────────────────────────
    def test_duplicate_username(self, client, login_admin, seed_users):
        resp = client.post(self.USERS_API, json={
            "username": "admin",
            "password": "anything",
            "display_name": "重复用户",
            "role": "writer",
        })
        assert resp.status_code == 409
        assert "已存在" in resp.text

    # ── TC-USER-008：用户管理页面 ──────────────────────
    def test_user_management_page(self, client, login_admin):
        resp = client.get("/admin/users")
        assert resp.status_code == 200
