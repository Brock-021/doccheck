# DocCheck · 实施计划

**版本：** v0.1  
**日期：** 2026-05-25  
**对应需求：** DocCheck-需求文档.md v1.0  

---

## 一、总体阶段划分

| 阶段 | 周期 | 产出 |
|:----|:-----|:------|
| **P0 · 基建** | 2天 | 项目骨架 + 数据库 + 登录认证 |
| **P1 · MVP 核心** | 5天 | 规则CRUD + 上传检查 + 报告展示 |
| **P2 · 审核完善** | 3天 | 审核流程 + 报告导出 + 历史记录 |
| **P3 · 管理面** | 2天 | 用户管理 + LLM配置 + 审计日志 |
| **P4 · 交付** | 1天 | 部署文档 + 打测试数据 + 验证 |

**合计：约13个工作日**

---

## 二、P0 · 基建（2天）

### Day 1 — 项目骨架

**创建目录结构：**
```
doccheck/
├── main.py                  # FastAPI 入口
├── config.py                # 配置（LLM/DB/上传限制）
├── database.py              # SQLAlchemy 引擎 + Session
├── models.py                # 所有表模型
├── schemas.py               # Pydantic 请求/响应模型
├── routers/
│   ├── __init__.py
│   ├── auth.py              # 登录/登出
│   ├── rules.py             # 规则 CRUD（桩）
│   ├── documents.py         # 文档上传（桩）
│   └── reports.py           # 报告查看（桩）
├── services/
│   ├── __init__.py
│   ├── doc_parser.py        # Word 解析（桩）
│   ├── checker.py           # AI 检查引擎（桩）
│   └── exporter.py          # 导出（桩）
├── templates/
│   ├── base.html            # 基础模板
│   ├── login.html
│   ├── dashboard.html
│   ├── rules/
│   │   ├── list.html
│   │   └── form.html
│   ├── documents/
│   │   └── upload.html
│   └── reports/
│       ├── detail.html
│       └── review.html
├── static/
│   └── style.css
├── requirements.txt
└── README.md
```

**任务清单：**

| # | 任务 | 文件 |
|:-:|:----|:-----|
| 1.1 | `main.py` — FastAPI app 初始化，挂载路由、静态文件、模板引擎 | `main.py` |
| 1.2 | `config.py` — 读取环境变量/配置文件（DB路径、LLM地址、上传限制） | `config.py` |
| 1.3 | `database.py` — SQLAlchemy async engine + sessionmaker + init_db() | `database.py` |
| 1.4 | `models.py` — 全部8张表：users, doc_types, rules, documents, check_tasks, check_results, reports, system_config | `models.py` |
| 1.5 | `schemas.py` — 各模块的 Pydantic 模型（Create/Update/Response） | `schemas.py` |
| 1.6 | `templates/base.html` — 基础布局：侧边栏 + 顶部导航 + 内容区 | `templates/base.html` |
| 1.7 | `static/style.css` — 基础样式（参考方案文档的简洁风格） | `static/style.css` |
| 1.8 | `requirements.txt` — 锁定依赖版本 | `requirements.txt` |

### Day 2 — 登录认证 + Dashboard

| # | 任务 | 文件 |
|:-:|:----|:-----|
| 2.1 | 登录页面 HTML | `templates/login.html` |
| 2.2 | 登录接口（用户名+密码，session 管理） | `routers/auth.py` |
| 2.3 | 登出接口 | `routers/auth.py` |
| 2.4 | 登录拦截中间件（未登录跳转 /login） | `main.py` |
| 2.5 | Dashboard 首页（按角色展示不同内容） | `templates/dashboard.html` |
| 2.6 | 验证：能登录/登出，跳转正常 | 手动测试 |

**用户表预置：** 初始化时插入 admin/admin123 管理员账号。

---

## 三、P1 · MVP 核心（5天）

### Day 3 — 文档类型 + 规则管理

| # | 任务 | 文件 |
|:-:|:----|:-----|
| 3.1 | 文档类型 CRUD（列表/新增/编辑/删除） | `routers/rules.py` |
| 3.2 | 文档类型管理页面 | `templates/rules/doc_types.html` |
| 3.3 | 规则列表页（按文档类型筛选，分页） | `templates/rules/list.html` |
| 3.4 | 规则新增/编辑页 + 表单 | `templates/rules/form.html` |
| 3.5 | 规则启用/禁用（Ajax 切换） | `routers/rules.py` |
| 3.6 | 规则复制功能 | `routers/rules.py` |
| 3.7 | 规则排序（拖拽或排序号调整） | `routers/rules.py` |

**接口清单：**

| 方法 | 路径 | 说明 |
|:----|:-----|:------|
| GET | `/admin/doc-types` | 文档类型列表 |
| POST | `/admin/doc-types` | 新增文档类型 |
| PUT | `/admin/doc-types/{id}` | 编辑 |
| DELETE | `/admin/doc-types/{id}` | 删除 |
| GET | `/admin/rules` | 规则列表（参数：doc_type_id, page） |
| POST | `/admin/rules` | 新增规则 |
| PUT | `/admin/rules/{id}` | 编辑规则 |
| DELETE | `/admin/rules/{id}` | 删除规则 |
| PATCH | `/admin/rules/{id}/toggle` | 启用/禁用切换 |
| POST | `/admin/rules/{id}/copy` | 复制规则 |

### Day 4 — 文档上传 + 解析

| # | 任务 | 文件 |
|:-:|:----|:-----|
| 4.1 | 上传页面（文档类型下拉 + 阶段选择 + 文件拖拽上传） | `templates/documents/upload.html` |
| 4.2 | 文件上传接口（接收 .docx，校验类型+大小，保存到 uploads/） | `routers/documents.py` |
| 4.3 | `python-docx` 解析服务：提取全文文本 + 章节结构 | `services/doc_parser.py` |
| 4.4 | 创建 check_task 记录（状态 pending → running） | `routers/documents.py` |
| 4.5 | 匹配规则：查询该文档类型 + 适用阶段 + 已启用的规则 | `routers/documents.py` |
| 4.6 | 简单的 LLM 调用桩（先返回 mock 数据，方便前端调试） | `services/checker.py` |

**接口清单：**

| 方法 | 路径 | 说明 |
|:----|:-----|:------|
| GET | `/documents/upload` | 上传页面 |
| POST | `/api/documents/upload` | 上传文件接口 |
| GET | `/api/documents/{id}/check` | 发起检查（返回 check_task_id）|
| GET | `/api/check-tasks/{id}/status` | 检查任务状态轮询 |

### Day 5 — AI 检查引擎（对接 LLM）

| # | 任务 | 文件 |
|:-:|:----|:-----|
| 5.1 | LLM 调用模块：httpx 调 OpenAI 兼容 API | `services/checker.py` |
| 5.2 | 构造 prompt：系统指令 + 文档全文 + 规则列表 → 要求输出 JSON | `services/checker.py` |
| 5.3 | 解析 LLM 返回的 JSON，写入 check_results 表 | `services/checker.py` |
| 5.4 | 错误处理：LLM 超时、返回格式错误、空结果 | `services/checker.py` |
| 5.5 | 更新 check_task 状态 done/failed | `services/checker.py` |
| 5.6 | 异步执行（后台任务，不阻塞上传响应） | `routers/documents.py` |

**Prompt 设计（核心）：**

```
你是一个文档合规检查助手。请根据以下规则逐条检查文档是否符合要求。

文档类型：{doc_type_name}
文档全文：
{full_text}

规则列表：
{逐条列出规则的 name + description + severity}

请逐条判断，输出 JSON 数组，每条包含：
- rule_name: 规则名称
- compliant: true/false/null(无法判断)
- issue: 问题描述（compliant=true 时可为空）
- location: 原文位置（章节名或段落摘要）
- suggestion: 修改建议（compliant=true 时可为空）
```

### Day 6 — 报告展示

| # | 任务 | 文件 |
|:-:|:----|:-----|
| 6.1 | 报告详情页（摘要统计 + 逐条问题列表） | `templates/reports/detail.html` |
| 6.2 | 报告数据接口 | `routers/reports.py` |
| 6.3 | 问题项展示：严重程度颜色标记、原文位置高亮 | `templates/reports/detail.html` |
| 6.4 | 状态标签：待审核 / 已通过 / 已确认 / 已驳回 | `templates/reports/detail.html` |
| 6.5 | 重新检查按钮（上传新版本 → 新 check_task） | `routers/reports.py` |

**接口清单：**

| 方法 | 路径 | 说明 |
|:----|:-----|:------|
| GET | `/reports/{id}` | 报告详情页 |
| GET | `/api/reports/{id}` | 报告数据 JSON |
| POST | `/api/reports/{id}/recheck` | 重新检查 |

### Day 7 — 文档历史列表

| # | 任务 | 文件 |
|:-:|:----|:-----|
| 7.1 | 文档列表页（我的文档，分页，按时间倒序） | `templates/documents/list.html` |
| 7.2 | 文档列表接口 | `routers/documents.py` |
| 7.3 | 单个文档的历史版本查看 | `templates/documents/history.html` |
| 7.4 | 全量测试：上传 → 检查 → 出报告 → 查看，跑通全链路 | 手动测试 |

**接口清单：**

| 方法 | 路径 | 说明 |
|:----|:-----|:------|
| GET | `/documents` | 我的文档列表页 |
| GET | `/api/documents` | 文档列表 JSON（参数：page, status） |
| GET | `/documents/{id}/history` | 某文档的历史版本页 |
| GET | `/api/documents/{id}/history` | 历史版本 JSON |

---

## 四、P2 · 审核完善（3天）

### Day 8 — 审核流程

| # | 任务 | 文件 |
|:-:|:----|:-----|
| 8.1 | 审核页面（报告详情 + 逐条操作按钮） | `templates/reviews/review.html` |
| 8.2 | 确认操作接口 | `routers/reports.py` |
| 8.3 | 驳回操作接口（含备注） | `routers/reports.py` |
| 8.4 | 忽略操作接口（含备注） | `routers/reports.py` |
| 8.5 | 审核结论：通过/有条件通过/不通过 | `routers/reports.py` |
| 8.6 | 审核后的报告状态更新 | `routers/reports.py` |

**接口清单：**

| 方法 | 路径 | 说明 |
|:----|:-----|:------|
| GET | `/reviews/{report_id}` | 审核页面 |
| POST | `/api/reviews/{result_id}/confirm` | 确认问题 |
| POST | `/api/reviews/{result_id}/reject` | 驳回（body: remark） |
| POST | `/api/reviews/{result_id}/ignore` | 忽略（body: remark） |
| POST | `/api/reviews/{report_id}/conclusion` | 出审核结论（body: conclusion） |

### Day 9 — 报告导出

| # | 任务 | 文件 |
|:-:|:----|:-----|
| 9.1 | 导出 PDF 服务（用 reportlab 或 weasyprint） | `services/exporter.py` |
| 9.2 | 导出 Word 服务（用 python-docx 生成 .docx 报告） | `services/exporter.py` |
| 9.3 | 导出按钮 + 下载接口 | `routers/reports.py` |
| 9.4 | 导出报告缓存到 reports/ 目录 | `services/exporter.py` |

**接口清单：**

| 方法 | 路径 | 说明 |
|:----|:-----|:------|
| GET | `/api/reports/{id}/export/pdf` | 导出 PDF |
| GET | `/api/reports/{id}/export/docx` | 导出 Word |

### Day 10 — 历史对比

| # | 任务 | 文件 |
|:-:|:----|:-----|
| 10.1 | 历史对比页面（并排显示两次检查结果） | `templates/documents/compare.html` |
| 10.2 | 对比数据接口（两次 check_task 的结果差异） | `routers/documents.py` |
| 10.3 | 标记：新增问题 / 已解决问题 / 仍然存在的问题 | `templates/documents/compare.html` |

**接口清单：**

| 方法 | 路径 | 说明 |
|:----|:-----|:------|
| GET | `/documents/{id}/compare` | 对比页（参数：v1=task_id, v2=task_id） |
| GET | `/api/documents/{id}/compare` | 对比数据 JSON |

---

## 五、P3 · 管理面（2天）

### Day 11 — 用户管理 + LLM 配置

| # | 任务 | 文件 |
|:-:|:----|:-----|
| 11.1 | 用户列表页（分页、搜索、角色筛选） | `templates/admin/users.html` |
| 11.2 | 新增/编辑用户（用户名、姓名、密码、角色） | `routers/auth.py` |
| 11.3 | 禁用/启用用户 | `routers/auth.py` |
| 11.4 | 重置密码 | `routers/auth.py` |
| 11.5 | LLM 配置页面（地址/Key/模型/超时/温度） | `templates/admin/llm_config.html` |
| 11.6 | LLM 配置保存（写入 system_config 表） | `routers/admin.py` |
| 11.7 | 测试连接按钮 → 调 LLM 的 /models 接口验证 | `routers/admin.py` |

**接口清单：**

| 方法 | 路径 | 说明 |
|:----|:-----|:------|
| GET | `/admin/users` | 用户管理页 |
| GET | `/api/admin/users` | 用户列表 |
| POST | `/api/admin/users` | 新增用户 |
| PUT | `/api/admin/users/{id}` | 编辑用户 |
| PATCH | `/api/admin/users/{id}/toggle` | 启用/禁用 |
| POST | `/api/admin/users/{id}/reset-password` | 重置密码 |
| GET | `/admin/llm-config` | LLM 配置页 |
| GET | `/api/admin/config/llm` | 获取 LLM 配置 |
| PUT | `/api/admin/config/llm` | 保存 LLM 配置 |
| POST | `/api/admin/config/llm/test` | 测试连接 |

### Day 12 — 审核日志 + 收尾

| # | 任务 | 文件 |
|:-:|:----|:-----|
| 12.1 | 审计日志页面（操作时间、操作人、操作类型、详情） | `templates/admin/audit_log.html` |
| 12.2 | 审计日志写入中间件（关键操作自动记录） | `services/audit.py` |
| 12.3 | 审计日志查询接口（时间范围 + 操作人 + 类型 筛选） | `routers/admin.py` |
| 12.4 | 健康检查接口 `/health` | `main.py` |

**接口清单：**

| 方法 | 路径 | 说明 |
|:----|:-----|:------|
| GET | `/admin/audit-log` | 审计日志页 |
| GET | `/api/admin/audit-log` | 日志列表（参数：start, end, user, action） |
| GET | `/health` | 健康检查 |

---

## 六、P4 · 交付（1天）

### Day 13 — 部署文档 + 验证

| # | 任务 | 文件 |
|:-:|:----|:-----|
| 13.1 | `deploy.sh` — 一键部署脚本（安装依赖、初始化 DB、创建 systemd 服务） | `deploy.sh` |
| 13.2 | `README.md` — 项目说明、开发指南、维护指南 | `README.md` |
| 13.3 | 预置测试数据：admin 账号 + 2个文档类型 + 10条示范规则 | `scripts/seed.py` |
| 13.4 | 端到端验证：登录 → 加规则 → 上传文档 → 检查 → 审核 → 导出 | 手动测试 |
| 13.5 | 2核2G 部署验证：确认内存、CPU 占用在合理范围 | 手动测试 |
| 13.6 | 全量 commit + 通知旺财推送到 GitHub | git |

---

## 七、依赖清单

| 依赖 | 用途 | 安装 |
|:----|:-----|:-----|
| **fastapi** | Web 框架 | `pip install fastapi` |
| **uvicorn** | ASGI 服务器 | `pip install uvicorn` |
| **sqlalchemy** | ORM | `pip install sqlalchemy` |
| **aiosqlite** | SQLite 异步驱动 | `pip install aiosqlite` |
| **jinja2** | 模板引擎 | `pip install jinja2` |
| **python-docx** | Word 文档解析 | `pip install python-docx` |
| **httpx** | HTTP 客户端（调 LLM） | `pip install httpx` |
| **aiofiles** | 异步文件操作 | `pip install aiofiles` |
| **python-multipart** | 文件上传 | `pip install python-multipart` |
| **weasyprint** (可选) | PDF 导出 | `pip install weasyprint` |

---

## 八、风险与应对

| 风险 | 概率 | 影响 | 应对 |
|:----|:----:|:----:|:-----|
| LLM 返回格式不稳定 | 中 | 高 | prompt 加强约束 + 后处理校验 + 重试机制 |
| python-docx 解析复杂格式丢失 | 低 | 中 | 仅提取文本+章节结构，不解析表格/图片 |
| 大文档（>10MB）LLM 超时 | 中 | 中 | 分章节检查 + 超时重试 + 前端进度提示 |
| 规则数量增多后 LLM 判断变慢 | 低 | 低 | 批量检查模式，一次调用处理全部规则 |
| 2核2G 并发多任务卡顿 | 低 | 低 | 同一时间只处理一个检查任务（串行队列） |
| SQLite 并发写入冲突 | 低 | 低 | ~100人规模，写入频率低，无需迁移 PG |
| 报告导出 PDF 中文乱码 | 中 | 中 | 确保系统安装中文字体（Noto Sans CJK） |

---

> **计划状态：** ✅ 可执行  
> **建议启动顺序：** P0 → P1 → P2 → P3 → P4，每个阶段结束后验证再进入下一阶段。
