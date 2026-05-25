# DocCheck · AI 文档合规检查系统

基于 AI 大模型的文档合规性自动检查工具。上传 .docx 文档，AI 自动逐条检查是否符合预设规则，人工审核确认后出具报告。

---

## 功能特性

- 🤖 **AI 自动检查** — 接入大模型 API（支持所有 OpenAI 兼容接口），对文档逐条检查
- 📏 **自然语言规则** — 业务人员直接用中文编写检查规则，AI 理解判断
- 📚 **多文档类型** — 支持分组管理不同业务场景的检查规则
- 🔍 **人工审核** — 确认/驳回/忽略逐条检查结果，出具审核结论
- 📄 **报告导出** — 支持导出 PDF / Word 格式检查报告
- 📊 **历史对比** — 对比两次检查结果，标记已解决/新增/仍存在的问题
- 👥 **多角色** — 管理员、审核员、普通用户三级权限
- ⚙️ **可配置模型** — 随时切换 API 地址和模型，无需重启

## 快速开始

### 方式一：一键部署

```bash
# 以 root 或 sudo 执行
sudo bash deploy.sh
```

脚本会自动完成：系统依赖 → 虚拟环境 → 安装包 → 初始化数据 → 创建 systemd 服务。

### 方式二：手动部署

```bash
# 1. 进入项目目录
cd doccheck

# 2. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install reportlab -i https://pypi.tuna.tsinghua.edu.cn/simple

# 4. 初始化种子数据
python3 scripts/seed.py

# 5. 启动服务
uvicorn main:app --host 0.0.0.0 --port 8000
```

访问 `http://localhost:8000` 即可使用。

## 默认账号

| 角色 | 用户名 | 密码 | 说明 |
|:----|:-------|:-----|:-----|
| 管理员 | `admin` | `admin123` | 所有权限（规则管理、用户管理、LLM 配置） |
| 审核员 | `reviewer` | `review123` | 审核检查结果、出具结论 |
| 普通用户 | `zhangsan` | `doc123456` | 上传文档、查看报告 |

## 配置 LLM

登录管理员账号后，进入 **LLM 配置** 页面，填入：
- **API 地址**：兼容 OpenAI 格式的接口地址（如 `https://api.deepseek.com/v1`）
- **API Key**：您的 API 密钥
- **模型名称**：如 `deepseek-chat`、`qwen-max`、`gpt-4o-mini`
- 其他参数（超时、温度等）使用默认值即可

配置完成后，上传文档即可自动触发 AI 检查。

## 项目结构

```
doccheck/
├── main.py                 # FastAPI 入口 + 页面路由
├── config.py               # 配置（上传大小、session 过期等）
├── database.py             # SQLAlchemy 引擎 + Session
├── models.py               # 数据表模型（9张表）
├── schemas.py              # Pydantic 请求/响应模型
├── deploy.sh               # 一键部署脚本
├── requirements.txt        # Python 依赖
├── routers/
│   ├── auth.py             # 登录/登出
│   ├── rules.py            # 规则 + 文档类型 CRUD
│   ├── documents.py        # 文档上传 + 检查任务
│   ├── reports.py          # 报告查看 + 导出
│   ├── reviews.py          # 审核流程
│   └── admin.py            # 用户管理 + LLM 配置 + 审计日志
├── services/
│   ├── doc_parser.py       # Word 文档解析
│   ├── checker.py          # AI 检查引擎
│   ├── exporter.py         # PDF / Word 导出
│   └── audit.py            # 审计日志服务
├── templates/              # Jinja2 模板
│   ├── base.html           # 基础布局（侧边栏 + 顶栏）
│   ├── login.html          # 登录页
│   ├── dashboard.html      # 工作台首页
│   ├── documents/          # 上传/列表/对比页面
│   ├── reports/            # 报告详情页
│   ├── reviews/            # 审核页
│   ├── rules/              # 规则管理页
│   └── admin/              # 用户管理/LLM配置/审计日志页
├── static/
│   └── style.css           # 样式
├── scripts/
│   └── seed.py             # 种子数据初始化
└── tests/                  # 测试用例（13个模块，98条用例）
```

## API 概览

### 认证
| 方法 | 路径 | 说明 |
|:----|:-----|:------|
| POST | `/api/auth/login` | 登录 |
| POST | `/api/auth/logout` | 登出 |

### 文档与检查
| 方法 | 路径 | 说明 |
|:----|:-----|:------|
| POST | `/api/documents/upload` | 上传文档并检查 |
| GET  | `/api/documents` | 文档列表 |
| GET  | `/api/documents/{id}/history` | 检查历史 |
| GET  | `/api/documents/{id}/compare` | 历史对比（v1, v2 参数） |
| GET  | `/api/documents/check-tasks/{id}/status` | 检查状态轮询 |

### 报告与审核
| 方法 | 路径 | 说明 |
|:----|:-----|:------|
| GET  | `/api/reports/{id}` | 报告详情 |
| GET  | `/api/reports/{id}/export/pdf` | 导出 PDF |
| GET  | `/api/reports/{id}/export/docx` | 导出 Word |
| POST | `/api/reviews/{id}/confirm` | 确认问题 |
| POST | `/api/reviews/{id}/reject` | 驳回问题 |
| POST | `/api/reviews/{id}/ignore` | 忽略问题 |
| POST | `/api/reviews/{id}/conclusion` | 出审核结论 |

### 管理
| 方法 | 路径 | 说明 |
|:----|:-----|:------|
| GET/POST/PUT | `/api/admin/users` | 用户管理 |
| GET/PUT | `/api/admin/config/llm` | LLM 配置 |
| POST | `/api/admin/config/llm/test` | 测试 LLM 连接 |
| GET | `/api/admin/audit-log` | 审计日志 |
| GET/POST/PUT | `/api/admin/doc-types` | 文档类型 |
| GET/POST/PUT | `/api/admin/rules` | 规则管理 |

## 维护命令

```bash
# 查看服务状态
sudo systemctl status doccheck

# 重启服务
sudo systemctl restart doccheck

# 查看实时日志
sudo journalctl -u doccheck -f

# 停止服务
sudo systemctl stop doccheck
```

## 技术栈

- **后端**: Python 3.11+ / FastAPI / SQLAlchemy (async) / SQLite
- **前端**: Jinja2 模板渲染（无前后端分离）
- **AI**: 兼容 OpenAI 格式的 LLM API（内网/外网均可）
- **文档解析**: python-docx
- **报告导出**: reportlab (PDF) / python-docx (Word)
- **部署**: uvicorn + systemd，2核2G 即可运行

## 许可证

MIT
