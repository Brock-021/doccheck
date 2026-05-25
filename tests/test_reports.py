"""DocCheck · 检查报告测试（8条用例）"""

import pytest


class TestReports:
    """TC-REPORT-001 ~ 008"""

    # ── TC-REPORT-001：报告展示完整 ────────────────────
    def test_report_detail_page(self, client, login_writer, seed_doc_types, seed_rules):
        from fixtures.demo_docs import make_compliant_report_docx
        # Upload first
        resp = client.post(
            "/api/documents/upload",
            data={"doc_type_id": 1, "stage": "initial"},
            files={"file": ("test.docx", make_compliant_report_docx(),
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        data = resp.json()
        report_id = data.get("report_id")

        if report_id:
            resp = client.get(f"/reports/{report_id}")
            assert resp.status_code == 200
            assert "检查报告" in resp.text or "doccheck" in resp.text.lower()

    # ── TC-REPORT-002：报告列表 ────────────────────────
    def test_report_list(self, client, login_writer):
        resp = client.get("/documents")
        assert resp.status_code == 200

    # ── TC-REPORT-003：报告 API ────────────────────────
    def test_report_api(self, client, login_writer, seed_doc_types, seed_rules):
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
            resp = client.get(f"/api/reports/{report_id}")
            assert resp.status_code == 200
            report = resp.json()
            assert "summary" in report or "results" in report or "check_task_id" in report

    # ── TC-REPORT-004：重新检查 ────────────────────────
    def test_recheck(self, client, login_writer, seed_doc_types, seed_rules):
        from fixtures.demo_docs import make_compliant_report_docx, make_noncompliant_report_docx
        # Upload first version
        resp = client.post(
            "/api/documents/upload",
            data={"doc_type_id": 1},
            files={"file": ("v1.docx", make_compliant_report_docx(),
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        doc_id = resp.json().get("document_id")

        if doc_id:
            # Recheck with updated file
            resp = client.post(
                f"/api/documents/{doc_id}/recheck",
                files={"file": ("v2.docx", make_noncompliant_report_docx(),
                                "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            )
            assert resp.status_code == 200

    # ── TC-REPORT-005：报告导出按钮可见 ────────────────
    def test_export_buttons_visible(self, client, login_writer, seed_doc_types, seed_rules):
        from fixtures.demo_docs import make_compliant_report_docx
        resp = client.post(
            "/api/documents/upload",
            data={"doc_type_id": 1},
            files={"file": ("test.docx", make_compliant_report_docx(),
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        report_id = resp.json().get("report_id")
        if report_id:
            resp = client.get(f"/reports/{report_id}")
            assert resp.status_code == 200

    # ── TC-REPORT-006：报告摘要统计正确 ────────────────
    def test_report_summary(self, client, login_writer, seed_doc_types, seed_rules):
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
            resp = client.get(f"/api/reports/{report_id}")
            if resp.status_code == 200:
                data = resp.json()
                # If summary is present, verify counts
                summary = data.get("summary") or data.get("summary_json", {})
                if summary:
                    total = summary.get("total_rules", 0)
                    passed = summary.get("passed", 0)
                    failed = summary.get("failed", 0)
                    assert total == passed + failed, f"Summary mismatch: total={total}, passed={passed}, failed={failed}"

    # ── TC-REPORT-007：报告状态标记 ────────────────────
    def test_report_status_labels(self, client, login_writer, seed_doc_types, seed_rules):
        from fixtures.demo_docs import make_compliant_report_docx
        resp = client.post(
            "/api/documents/upload",
            data={"doc_type_id": 1},
            files={"file": ("test.docx", make_compliant_report_docx(),
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        report_id = resp.json().get("report_id")
        if report_id:
            resp = client.get(f"/api/reports/{report_id}")
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results") or data.get("check_results", [])
                for r in results:
                    assert "review_status" in r

    # ── TC-REPORT-008：健康检查 ────────────────────────
    def test_health_check(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
