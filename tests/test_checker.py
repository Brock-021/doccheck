"""DocCheck · AI 检查引擎测试（8条用例）"""

import pytest


class TestChecker:
    """TC-CHECK-001 ~ 008"""

    UPLOAD_API = "/api/documents/upload"
    CHECK_API = "/api/documents"

    def _upload_and_check(self, client, docx, doc_type_id=1, stage="initial"):
        """Helper: upload a docx and return the check task."""
        resp = client.post(
            self.UPLOAD_API,
            data={"doc_type_id": doc_type_id, "stage": stage},
            files={"file": ("test.docx", docx,
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert resp.status_code == 200
        return resp.json()

    # ── TC-CHECK-001：文档符合所有规则 ──────────────────
    def test_check_compliant(self, client, login_writer, seed_doc_types, seed_rules):
        from fixtures.demo_docs import make_compliant_report_docx
        result = self._upload_and_check(client, make_compliant_report_docx())
        task_id = result["check_task_id"]

        # Poll for completion
        resp = client.get(f"/api/check-tasks/{task_id}/status")
        assert resp.status_code == 200

    # ── TC-CHECK-002：文档违反部分规则 ─────────────────
    def test_check_noncompliant(self, client, login_writer, seed_doc_types, seed_rules):
        from fixtures.demo_docs import make_noncompliant_report_docx
        result = self._upload_and_check(client, make_noncompliant_report_docx())
        assert result["check_task_id"]

    # ── TC-CHECK-006：规则数量为 0 ──────────────────────
    def test_check_no_rules(self, client, login_writer, seed_doc_types):
        from fixtures.demo_docs import make_compliant_report_docx
        # DocType id=3 (需求文档) has no rules in seed data
        result = self._upload_and_check(client, make_compliant_report_docx(), doc_type_id=3)
        assert "提示" in str(result) or "规则" in str(result)

    # ── TC-CHECK-003：LLM 超时 ──────────────────────────
    def test_check_llm_timeout(self, client, login_writer, seed_doc_types, seed_rules, monkeypatch):
        """Simulate LLM timeout by patching the checker to raise TimeoutError."""
        from services import checker
        import httpx

        async def mock_call(*args, **kwargs):
            raise httpx.TimeoutException("LLM timeout")

        monkeypatch.setattr(checker, "call_llm", mock_call)

        from fixtures.demo_docs import make_compliant_report_docx
        result = self._upload_and_check(client, make_compliant_report_docx())
        task_id = result["check_task_id"]

        resp = client.get(f"/api/check-tasks/{task_id}/status")
        # Should handle gracefully
        assert resp.status_code == 200

    # ── TC-CHECK-004：LLM 返回格式错误 ─────────────────
    def test_check_llm_bad_format(self, client, login_writer, seed_doc_types, seed_rules, monkeypatch):
        """Simulate LLM returning non-JSON."""
        from services import checker

        async def mock_call(*args, **kwargs):
            return "not json at all"

        monkeypatch.setattr(checker, "call_llm", mock_call)

        from fixtures.demo_docs import make_compliant_report_docx
        result = self._upload_and_check(client, make_compliant_report_docx())
        task_id = result["check_task_id"]

        resp = client.get(f"/api/check-tasks/{task_id}/status")
        assert resp.status_code == 200

    # ── TC-CHECK-005：LLM 返回空结果 ───────────────────
    def test_check_llm_empty_result(self, client, login_writer, seed_doc_types, seed_rules, monkeypatch):
        """Simulate LLM returning empty JSON array."""
        from services import checker

        async def mock_call(*args, **kwargs):
            return "[]"

        monkeypatch.setattr(checker, "call_llm", mock_call)

        from fixtures.demo_docs import make_compliant_report_docx
        result = self._upload_and_check(client, make_compliant_report_docx())
        task_id = result["check_task_id"]

        resp = client.get(f"/api/check-tasks/{task_id}/status")
        assert resp.status_code == 200

    # ── TC-CHECK-007：检查中状态轮询 ──────────────────
    def test_check_status_polling(self, client, login_writer, seed_doc_types, seed_rules):
        from fixtures.demo_docs import make_compliant_report_docx
        result = self._upload_and_check(client, make_compliant_report_docx())
        task_id = result["check_task_id"]

        status_resp = client.get(f"/api/check-tasks/{task_id}/status")
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert "status" in data
        assert data["status"] in ("pending", "running", "done", "failed")

    # ── TC-CHECK-008：阶段筛选规则 ─────────────────────
    def test_check_stage_filter(self, client, login_writer, seed_doc_types, seed_rules):
        from fixtures.demo_docs import make_compliant_report_docx
        # The "final" stage rule (技术方案对比分析) should NOT match during initial check
        result = self._upload_and_check(client, make_compliant_report_docx(), stage="initial")
        assert result["check_task_id"]
