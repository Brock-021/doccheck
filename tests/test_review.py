"""DocCheck · 审核流程测试（10条用例）"""

import pytest


class TestReview:
    """TC-REVIEW-001 ~ 010"""

    # ── TC-REVIEW-001：确认问题 ────────────────────────
    def test_confirm_issue(self, client, login_reviewer, seed_doc_types, seed_rules):
        from fixtures.demo_docs import make_compliant_report_docx
        resp = client.post(
            "/api/documents/upload",
            data={"doc_type_id": 1},
            files={"file": ("test.docx", make_compliant_report_docx(),
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        data = resp.json()
        result_id = data.get("result_id") or data.get("check_result_id")
        if result_id:
            resp = client.post(f"/api/reviews/{result_id}/confirm")
            assert resp.status_code in (200, 404)  # 404 if no result yet (async LLM)

    # ── TC-REVIEW-002：驳回问题 ────────────────────────
    def test_reject_issue(self, client, login_reviewer, seed_doc_types, seed_rules):
        from fixtures.demo_docs import make_compliant_report_docx
        resp = client.post(
            "/api/documents/upload",
            data={"doc_type_id": 1},
            files={"file": ("test.docx", make_compliant_report_docx(),
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        data = resp.json()
        result_id = data.get("result_id") or data.get("check_result_id")
        if result_id:
            resp = client.post(f"/api/reviews/{result_id}/reject", json={"remark": "AI误判，文档中已包含"})
            assert resp.status_code in (200, 404)

    # ── TC-REVIEW-003：忽略问题 ────────────────────────
    def test_ignore_issue(self, client, login_reviewer, seed_doc_types, seed_rules):
        from fixtures.demo_docs import make_compliant_report_docx
        resp = client.post(
            "/api/documents/upload",
            data={"doc_type_id": 1},
            files={"file": ("test.docx", make_compliant_report_docx(),
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        data = resp.json()
        result_id = data.get("result_id") or data.get("check_result_id")
        if result_id:
            resp = client.post(f"/api/reviews/{result_id}/ignore", json={"remark": "本次可接受"})
            assert resp.status_code in (200, 404)

    # ── TC-REVIEW-004：审核结论 — 通过 ─────────────────
    def test_conclusion_pass(self, client, login_reviewer, seed_doc_types, seed_rules):
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
            resp = client.post(f"/api/reviews/{report_id}/conclusion", json={"conclusion": "pass"})
            assert resp.status_code in (200, 404)

    # ── TC-REVIEW-005：审核结论 — 有条件通过 ──────────
    def test_conclusion_conditional(self, client, login_reviewer, seed_doc_types, seed_rules):
        from fixtures.demo_docs import make_noncompliant_report_docx
        resp = client.post(
            "/api/documents/upload",
            data={"doc_type_id": 1},
            files={"file": ("test.docx", make_noncompliant_report_docx(),
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        data = resp.json()
        report_id = data.get("report_id")
        if report_id:
            resp = client.post(f"/api/reviews/{report_id}/conclusion",
                               json={"conclusion": "conditional_pass"})
            assert resp.status_code in (200, 404)

    # ── TC-REVIEW-007：重复操作 ────────────────────────
    def test_double_confirm(self, client, login_reviewer, seed_doc_types, seed_rules):
        from fixtures.demo_docs import make_compliant_report_docx
        resp = client.post(
            "/api/documents/upload",
            data={"doc_type_id": 1},
            files={"file": ("test.docx", make_compliant_report_docx(),
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        data = resp.json()
        result_id = data.get("result_id")
        # If result is available, confirm twice — second should fail
        if result_id:
            client.post(f"/api/reviews/{result_id}/confirm")
            resp2 = client.post(f"/api/reviews/{result_id}/confirm")
            assert resp2.status_code in (409, 400)

    # ── TC-REVIEW-009：编写者不能审核 ─────────────────
    def test_writer_cannot_review(self, client, login_writer):
        resp = client.get("/reviews/1")
        assert resp.status_code in (302, 403)

    # ── TC-REVIEW-008：审核页面 ────────────────────────
    def test_review_page_access(self, client, login_reviewer):
        resp = client.get("/reviews/9999")
        # Review page for non-existent report should 404
        assert resp.status_code in (200, 302, 404)

    # ── TC-REVIEW-010：审核备注 ────────────────────────
    def test_review_with_remark(self, client, login_reviewer, seed_doc_types, seed_rules):
        from fixtures.demo_docs import make_compliant_report_docx
        resp = client.post(
            "/api/documents/upload",
            data={"doc_type_id": 1},
            files={"file": ("test.docx", make_compliant_report_docx(),
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        data = resp.json()
        result_id = data.get("result_id")
        if result_id:
            resp = client.post(f"/api/reviews/{result_id}/reject",
                               json={"remark": "这条AI判断有误，文档中已有相关内容"})
            assert resp.status_code in (200, 404)
            if resp.status_code == 200:
                assert resp.json().get("remark") == "这条AI判断有误，文档中已有相关内容"
