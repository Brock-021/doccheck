"""DocCheck · 文档上传测试（10条用例）"""

import pytest
from fixtures.demo_docs import (
    make_compliant_report_docx,
    make_noncompliant_report_docx,
    make_large_docx,
)


class TestUpload:
    """TC-UPLOAD-001 ~ 010"""

    API = "/api/documents/upload"

    # ── TC-UPLOAD-001：正常上传 .docx ──────────────────
    def test_upload_valid_docx(self, client, login_writer, seed_doc_types, seed_rules):
        docx = make_compliant_report_docx()
        resp = client.post(
            self.API,
            data={"doc_type_id": 1, "stage": "initial"},
            files={"file": ("test_report.docx", docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "document_id" in data
        assert "check_task_id" in data

    # ── TC-UPLOAD-002：上传非 .docx 文件 ───────────────
    def test_upload_invalid_format(self, client, login_writer, seed_doc_types):
        resp = client.post(
            self.API,
            data={"doc_type_id": 1},
            files={"file": ("test.pdf", b"%PDF-1.4 fake pdf", "application/pdf")},
        )
        assert resp.status_code == 400
        assert "docx" in resp.text.lower()

    # ── TC-UPLOAD-003：上传超限文件 ────────────────────
    def test_upload_oversized(self, client, login_writer, seed_doc_types):
        # Create a file > 50MB (or whatever limit is configured)
        big_content = b"x" * (51 * 1024 * 1024)
        resp = client.post(
            self.API,
            data={"doc_type_id": 1},
            files={"file": ("big.docx", big_content,
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert resp.status_code == 400
        assert "大小" in resp.text or "50MB" in resp.text

    # ── TC-UPLOAD-004：不上传文件直接开始 ──────────────
    def test_upload_no_file(self, client, login_writer):
        resp = client.post(self.API, data={"doc_type_id": 1})
        assert resp.status_code == 422

    # ── TC-UPLOAD-005：不选文档类型 ────────────────────
    def test_upload_no_doc_type(self, client, login_writer):
        docx = make_compliant_report_docx()
        resp = client.post(
            self.API,
            files={"file": ("test.docx", docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert resp.status_code == 422

    # ── TC-UPLOAD-006：空文档上传 ──────────────────────
    def test_upload_empty_docx(self, client, login_writer, seed_doc_types, seed_rules):
        from fixtures.demo_docs import make_docx
        empty = make_docx("")
        resp = client.post(
            self.API,
            data={"doc_type_id": 1, "stage": "initial"},
            files={"file": ("empty.docx", empty, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert resp.status_code == 200

    # ── TC-UPLOAD-007：中文文件名 ──────────────────────
    def test_upload_chinese_filename(self, client, login_writer, seed_doc_types, seed_rules):
        docx = make_compliant_report_docx()
        resp = client.post(
            self.API,
            data={"doc_type_id": 1},
            files={"file": ("XX项目立项报告_v2.1.docx", docx,
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert resp.status_code == 200

    # ── TC-UPLOAD-008：上传同名文件（多版本）───────────
    def test_upload_duplicate_filename(self, client, login_writer, seed_doc_types, seed_rules):
        docx = make_compliant_report_docx()
        for _ in range(2):
            docx.seek(0)
            resp = client.post(
                self.API,
                data={"doc_type_id": 1},
                files={"file": ("same.docx", docx,
                                "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            )
            assert resp.status_code == 200

    # ── TC-UPLOAD-009：上传页面可访问 ──────────────────
    def test_upload_page_access(self, client, login_writer):
        resp = client.get("/documents/upload")
        assert resp.status_code == 200

    # ── TC-UPLOAD-010：大文档 ──────────────────────────
    @pytest.mark.slow
    def test_upload_large_docx(self, client, login_writer, seed_doc_types, seed_rules):
        docx = make_large_docx(1000)  # ~1000 words, not huge but enough
        resp = client.post(
            self.API,
            data={"doc_type_id": 1},
            files={"file": ("large.docx", docx,
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert resp.status_code == 200
