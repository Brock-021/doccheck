"""
DocCheck · 自动化测试脚本

使用方式：
  pip install pytest pytest-asyncio httpx pytest-cov
  pytest tests/ -v --cov=doccheck --cov-report=term-missing

结构：
  tests/
  ├── conftest.py              # 共享 fixtures（TestClient、测试数据）
  ├── test_auth.py             # 用户认证（8条）
  ├── test_doc_types.py        # 文档类型管理（6条）
  ├── test_rules.py            # 规则管理（14条）
  ├── test_upload.py           # 文档上传（10条）
  ├── test_checker.py          # AI 检查引擎（8条）
  ├── test_reports.py          # 检查报告（8条）
  ├── test_review.py           # 审核流程（10条）
  ├── test_history.py          # 历史记录（4条）
  ├── test_export.py           # 报告导出（4条）
  ├── test_llm_config.py       # LLM 配置（6条）
  ├── test_users.py            # 用户管理（8条）
  ├── test_audit.py            # 审计日志（4条）
  ├── test_permissions.py      # 权限控制（10条）
  └── fixtures/
      └── demo_docs.py         # 构造测试文档辅助
"""
