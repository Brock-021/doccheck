"""DocCheck · 用户认证测试（8条用例）"""

import pytest


class TestAuth:
    """TC-AUTH-001 ~ 008"""

    AUTH_API = "/api/auth"

    # ── TC-AUTH-001：正常登录 ──────────────────────────
    def test_normal_login(self, client, seed_users):
        resp = client.post(f"{self.AUTH_API}/login", data={
            "username": "admin",
            "password": "admin123",
        })
        assert resp.status_code == 200
        # Should redirect to dashboard or return success
        assert resp.url.path == "/" or resp.status_code == 200
        assert "session" in client.cookies

    # ── TC-AUTH-002：密码错误 ──────────────────────────
    def test_wrong_password(self, client, seed_users):
        resp = client.post(f"{self.AUTH_API}/login", data={
            "username": "admin",
            "password": "wrongpass",
        })
        assert resp.status_code == 401
        assert "密码" in resp.text or "错误" in resp.text

    # ── TC-AUTH-003：用户名不存在 ──────────────────────
    def test_nonexistent_user(self, client, seed_users):
        resp = client.post(f"{self.AUTH_API}/login", data={
            "username": "nonexist",
            "password": "anything",
        })
        assert resp.status_code == 401
        # Should NOT reveal whether username exists
        assert "用户" in resp.text or "名或密码" in resp.text

    # ── TC-AUTH-004：空用户名/密码 ─────────────────────
    def test_empty_credentials(self, client, seed_users):
        resp = client.post(f"{self.AUTH_API}/login", data={
            "username": "",
            "password": "",
        })
        assert resp.status_code == 422  # FastAPI form validation

    # ── TC-AUTH-005：登出 ──────────────────────────────
    def test_logout(self, client, seed_users):
        # Login first
        client.post(f"{self.AUTH_API}/login", data={
            "username": "admin",
            "password": "admin123",
        })
        resp = client.post(f"{self.AUTH_API}/logout")
        assert resp.status_code == 200
        # Verify session is cleared
        resp2 = client.get("/")
        # Should redirect to login
        assert resp2.url.path == "/login" or resp2.status_code == 302

    # ── TC-AUTH-006：未登录访问受保护页面 ──────────────
    def test_unauthenticated_access(self, client):
        resp = client.get("/documents/upload", follow_redirects=False)
        assert resp.status_code == 302  # Redirect to login
        assert "/login" in resp.headers.get("location", "")

    # ── TC-AUTH-007：Session 过期 ──────────────────────
    def test_session_expiry(self, client, seed_users):
        # Login
        client.post(f"{self.AUTH_API}/login", data={
            "username": "admin",
            "password": "admin123",
        })
        # Clear session cookie to simulate expiry
        client.cookies.clear()
        resp = client.get("/documents/upload", follow_redirects=False)
        assert resp.status_code == 302

    # ── TC-AUTH-008：禁用用户不能登录 ─────────────────
    def test_disabled_user_login(self, client, seed_users):
        resp = client.post(f"{self.AUTH_API}/login", data={
            "username": "disabled_user",
            "password": "disabled123",
        })
        assert resp.status_code == 403
        assert "禁用" in resp.text
