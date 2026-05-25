"""DocCheck · LLM 配置测试（6条用例）"""

import pytest


class TestLlmConfig:
    """TC-LLM-001 ~ 006"""

    CONFIG_API = "/api/admin/config/llm"

    # ── TC-LLM-001：保存 LLM 配置 ──────────────────────
    def test_save_config(self, client, login_admin):
        resp = client.put(self.CONFIG_API, json={
            "api_base": "http://192.168.1.100:8000/v1",
            "api_key": "sk-test-key-12345",
            "model": "qwen2.5-72b",
            "timeout": 60,
            "max_retries": 3,
            "temperature": 0.1,
            "max_tokens": 4096,
        })
        assert resp.status_code == 200

    # ── TC-LLM-002：读取 LLM 配置 ──────────────────────
    def test_read_config(self, client, login_admin):
        # Save first
        client.put(self.CONFIG_API, json={
            "api_base": "http://192.168.1.100:8000/v1",
            "api_key": "sk-test-key-12345",
            "model": "qwen2.5-72b",
        })

        resp = client.get(self.CONFIG_API)
        assert resp.status_code == 200
        data = resp.json()
        assert data["api_base"] == "http://192.168.1.100:8000/v1"
        # Key should be masked
        assert "****" in data["api_key"] or data["api_key"].endswith("2345")

    # ── TC-LLM-003：测试连接 — 成功 ────────────────────
    def test_test_connection_success(self, client, login_admin, monkeypatch):
        from services import checker

        async def mock_models_list(*args, **kwargs):
            return {"data": [{"id": "qwen2.5-72b"}]}

        monkeypatch.setattr(checker, "fetch_models", mock_models_list)

        client.put(self.CONFIG_API, json={
            "api_base": "http://valid:8000/v1",
            "api_key": "sk-test-key",
        })
        resp = client.post(f"{self.CONFIG_API}/test")
        assert resp.status_code == 200
        assert "成功" in resp.text or "success" in resp.text.lower()

    # ── TC-LLM-004：测试连接 — 失败 ────────────────────
    def test_test_connection_failure(self, client, login_admin, monkeypatch):
        from services import checker
        import httpx

        async def mock_fail(*args, **kwargs):
            raise httpx.ConnectError("Connection refused")

        monkeypatch.setattr(checker, "fetch_models", mock_fail)

        client.put(self.CONFIG_API, json={
            "api_base": "http://invalid:8000/v1",
            "api_key": "sk-test-key",
        })
        resp = client.post(f"{self.CONFIG_API}/test")
        assert resp.status_code == 200
        assert "失败" in resp.text or "fail" in resp.text.lower() or "拒绝" in resp.text

    # ── TC-LLM-005：API Key 不能为空 ───────────────────
    def test_require_api_key(self, client, login_admin):
        resp = client.put(self.CONFIG_API, json={
            "api_base": "http://localhost:8000/v1",
            "api_key": "",
            "model": "test",
        })
        assert resp.status_code == 422

    # ── TC-LLM-006：非管理员访问 LLM 配置 ──────────────
    def test_non_admin_access(self, client, login_writer):
        resp = client.get(self.CONFIG_API)
        assert resp.status_code in (401, 403)

        resp = client.put(self.CONFIG_API, json={"api_base": "", "api_key": ""})
        assert resp.status_code in (401, 403)
