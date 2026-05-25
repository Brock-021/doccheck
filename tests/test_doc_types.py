"""DocCheck · 文档类型管理测试（6条用例）"""

import pytest


class TestDocTypes:
    """TC-DOCTYPE-001 ~ 006"""

    API = "/api/admin/doc-types"

    # ── TC-DOCTYPE-001：新增文档类型 ──────────────────
    def test_create_doc_type(self, client, login_rule_admin):
        resp = client.post(self.API, json={"name": "验收报告", "sort_order": 4})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "验收报告"

    # ── TC-DOCTYPE-002：编辑文档类型 ──────────────────
    def test_edit_doc_type(self, client, login_rule_admin, seed_doc_types):
        resp = client.put(f"{self.API}/1", json={"name": "立项报告（修订）"})
        assert resp.status_code == 200

    # ── TC-DOCTYPE-003：删除无关联的文档类型 ──────────
    def test_delete_unused_doc_type(self, client, login_rule_admin):
        # Create and then delete
        resp = client.post(self.API, json={"name": "测试类型", "sort_order": 99})
        type_id = resp.json()["id"]
        resp = client.delete(f"{self.API}/{type_id}")
        assert resp.status_code == 200

    # ── TC-DOCTYPE-004：删除有关联规则的文档类型 ──────
    def test_delete_doc_type_with_rules(self, client, login_rule_admin, seed_doc_types, seed_rules):
        # DocType id=1 has rules
        resp = client.delete(f"{self.API}/1")
        assert resp.status_code == 409
        assert "规则" in resp.text

    # ── TC-DOCTYPE-005：文档类型列表 ──────────────────
    def test_list_doc_types(self, client, login_rule_admin, seed_doc_types):
        resp = client.get(self.API)
        assert resp.status_code == 200
        types = resp.json()
        assert len(types) >= 3
        # Sorted by sort_order
        orders = [t["sort_order"] for t in types]
        assert orders == sorted(orders)

    # ── TC-DOCTYPE-006：文档类型名称重复 ──────────────
    def test_duplicate_name(self, client, login_rule_admin, seed_doc_types):
        resp = client.post(self.API, json={"name": "立项报告", "sort_order": 10})
        assert resp.status_code == 409
        assert "已存在" in resp.text
