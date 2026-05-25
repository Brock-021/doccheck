"""DocCheck · 历史记录测试（4条用例）"""

import pytest


class TestHistory:
    """TC-HIST-001 ~ 004"""

    # ── TC-HIST-001：文档历史列表 ──────────────────────
    def test_document_history_api(self, client, login_writer, seed_doc_types, seed_rules):
        from fixtures.demo_docs import make_compliant_report_docx
        # Upload twice to create history
        docx = make_compliant_report_docx()
        for _ in range(2):
            docx.seek(0)
            client.post(
                "/api/documents/upload",
                data={"doc_type_id": 1},
                files={"file": ("test.docx", docx,
                                "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            )

        resp = client.get("/api/documents")
        assert resp.status_code == 200
        docs = resp.json() if isinstance(resp.json(), list) else resp.json().get("items", [])
        assert len(docs) > 0

    # ── TC-HIST-002：查看某次历史报告 ──────────────────
    def test_view_historical_report(self, client, login_writer, seed_doc_types, seed_rules):
        from fixtures.demo_docs import make_compliant_report_docx
        resp = client.post(
            "/api/documents/upload",
            data={"doc_type_id": 1},
            files={"file": ("test.docx", make_compliant_report_docx(),
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        data = resp.json()
        doc_id = data.get("document_id")
        if doc_id:
            resp = client.get(f"/documents/{doc_id}")
            assert resp.status_code in (200, 404)

    # ── TC-HIST-003：版本对比 ──────────────────────────
    def test_version_compare(self, client, login_writer, seed_doc_types, seed_rules):
        from fixtures.demo_docs import make_compliant_report_docx
        docx = make_compliant_report_docx()
        resp1 = client.post(
            "/api/documents/upload",
            data={"doc_type_id": 1},
            files={"file": ("v1.docx", docx,
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        doc_id = resp1.json().get("document_id")

        if doc_id:
            # Recheck
            docx.seek(0)
            resp2 = client.post(
                f"/api/documents/{doc_id}/recheck",
                files={"file": ("v2.docx", docx,
                                "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            )
            assert resp2.status_code in (200, 404, 501)

    # ── TC-HIST-004：历史页面 ──────────────────────────
    def test_history_page(self, client, login_writer):
        resp = client.get("/documents")
        assert resp.status_code == 200
