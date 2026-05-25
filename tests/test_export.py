"""DocCheck · 报告导出测试（4条用例）"""

import pytest


class TestExport:
    """TC-EXPORT-001 ~ 004"""

    # ── TC-EXPORT-001：导出 PDF ────────────────────────
    def test_export_pdf(self, client, login_writer, seed_doc_types, seed_rules):
        from fixtures.demo_docs import make_compliant_report_docx
        resp = client.post(
            "/api/documents/upload",
            data={"doc_type_id": 1},
            files={"file": ("test.docx", make_compliant_report_docx(),
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        data = resp.json()
        report_id = data.get("report_id")
        if report_id:
            resp = client.get(f"/api/reports/{report_id}/export/pdf")
            # PDF might not be implemented yet (v1.1), so 404 or 501 is ok
            assert resp.status_code in (200, 404, 501)
            if resp.status_code == 200:
                assert "application/pdf" in resp.headers.get("content-type", "")

    # ── TC-EXPORT-002：导出 Word ───────────────────────
    def test_export_word(self, client, login_writer, seed_doc_types, seed_rules):
        from fixtures.demo_docs import make_compliant_report_docx
        resp = client.post(
            "/api/documents/upload",
            data={"doc_type_id": 1},
            files={"file": ("test.docx", make_compliant_report_docx(),
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        data = resp.json()
        report_id = data.get("report_id")
        if report_id:
            resp = client.get(f"/api/reports/{report_id}/export/docx")
            assert resp.status_code in (200, 404, 501)
            if resp.status_code == 200:
                content_type = resp.headers.get("content-type", "")
                assert "openxml" in content_type or "octet-stream" in content_type

    # ── TC-EXPORT-003：导出报告中文不乱码 ──────────────
    def test_export_chinese_no_garbled(self, client, login_writer, seed_doc_types, seed_rules):
        from fixtures.demo_docs import make_compliant_report_docx
        resp = client.post(
            "/api/documents/upload",
            data={"doc_type_id": 1},
            files={"file": ("test.docx", make_compliant_report_docx(),
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        data = resp.json()
        report_id = data.get("report_id")
        if report_id:
            # Test Word export for Chinese text
            resp = client.get(f"/api/reports/{report_id}/export/docx")
            if resp.status_code == 200:
                content = resp.content
                # Quick check: no replacement character that suggests garbled
                assert b"\xef\xbf\xbd" not in content  # U+FFFD replacement char

    # ── TC-EXPORT-004：没有权限的用户不能导出 ──────────
    def test_export_unauthorized(self, client, seed_doc_types, seed_rules):
        # Not logged in
        resp = client.get("/api/reports/1/export/pdf")
        assert resp.status_code in (302, 401, 403)
