# DocCheck · 部署手册

**版本**: 2.0.0 | **更新时间**: 2026-05-25

DocCheck 是一款基于 AI 的文档合规检查工具，支持 .docx 文档上传、LLM 自动检查、人工审核闭环、统计分析看板、存储管理等完整功能。

---

## 目录

1. [环境要求](#1-环境要求)
2. [快速部署（一键脚本）](#2-快速部署一键脚本)
3. [手动部署（分步说明）](#3-手动部署分步说明)
4. [LLM 引擎配置](#4-llm-引擎配置)
5. [服务管理](#5-服务管理)
6. [HTTPS 配置](#6-https-配置可选)
7. [升级](#7-升级)
8. [存储管理](#8-存储管理)
9. [常见问题](#9-常见问题)

---

## 1. 环境要求

| 项目 | 最低配置 | 推荐配置 |
|:----|:---------|:---------|
| CPU | 2 核 | 4 核 |
| 内存 | 2 GB | 4 GB |
| 磁盘 | 10 GB | 20 GB（取决于文档量） |
| 操作系统 | Ubuntu 20.04+ / Debian 11+ | Ubuntu 22.04 |
| Python | 3.9+ | 3.11 |
| 网络 | 可访问 LLM API（需外网或内网 API） | |

> 💡 **磁盘建议**：文档原件存储在 `uploads/` 目录，长期运行可能积累较多数据。建议定期使用管理员侧 **存储管理** 功能清理旧文档（详见第8节）。

---

## 2. 快速部署（一键脚本）

### 2.1 有外网可连 git（开发环境/测试环境）

```bash
# 1. 获取代码
git clone https://github.com/Brock-021/doccheck.git
cd doccheck

# 2. 一键部署（需 sudo 权限）
sudo bash deploy.sh
```

### 2.2 内网无法连 git（生产环境/内网环境）

```bash
# 1. 在有外网的机器上打好完整源码包（含虚拟环境）
#    外网机器执行：
cd doccheck
tar czf doccheck-full.tar.gz \
    --exclude='venv' \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    .

# 2. 将 doccheck-full.tar.gz 通过 U盘/内网文件服务器/scp 传到目标服务器

# 3. 在目标服务器上解压
tar xzf doccheck-full.tar.gz
cd doccheck

# 4. 一键部署（需 sudo 权限）
sudo bash deploy.sh
```

> 💡 如外网也无法打包虚拟环境，可按 [第3.2节](#32-离线安装-Python-依赖) 的方式将 Python 包下载到本地后传入。

部署脚本会自动完成：

| 步骤 | 操作 |
|:----|:-----|
| 1/5 | 检查并安装系统依赖（python3、pip、venv） |
| 2/5 | 创建 Python 虚拟环境 |
| 3/5 | 安装 Python 依赖包（含 reportlab 用于 PDF 导出） |
| 4/5 | 初始化数据库 + 种子数据（管理员/审核员/编写者账号、文档类型、检查规则） |
| 5/5 | 创建 systemd 服务并启动，设置开机自启 |

部署完成后输出：

```
🎉 DocCheck 部署完成！
访问地址: http://<服务器IP>:8000
管理员:   admin / admin123
审核员:   reviewer / review123
编写员:   writer / writer123
普通用户: zhangsan / zhangsan
```

---

## 3. 手动部署（分步说明）

如果一键脚本不适用（如非 Ubuntu/Debian 系统，或已有 Python 环境），可按以下步骤手动部署。

### 3.1 安装系统依赖

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y python3 python3-pip python3-venv

# 如需 PDF 导出中文支持，安装中文字体
sudo apt install -y fonts-noto-cjk
```

### 3.2 创建虚拟环境并安装依赖

#### 3.2.1 有外网可连 PyPI

```bash
cd doccheck
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 如需 PDF 导出功能
pip install reportlab

# 内网但有外网镜像源
# pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

#### 3.2.2 离线安装（内网完全无外网）

`deploy.sh` 会自动检测网络状态：
- 有外网 → 自动用清华镜像源安装
- 无外网 → 跳过在线安装，提示引用下面的离线方案

**方案A：外网打包虚拟环境（推荐）**

在有外网的机器上，先安装好所有依赖，然后将整个 `venv/` 目录打包传入内网：

```bash
# 在外网机器上
cd doccheck
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install reportlab -i https://pypi.tuna.tsinghua.edu.cn/simple
cd ..
tar czf doccheck-venv.tar.gz doccheck/venv

# 将 doccheck-venv.tar.gz 传入内网目标服务器
# 在目标服务器上
cd /path/to/doccheck
tar xzf /path/to/doccheck-venv.tar.gz --strip-components=1
```

> ⚠️ 注意：需确保外网和内网的操作系统、Python 版本一致（如都是 Ubuntu 22.04 + Python 3.11），否则虚拟环境可能不兼容。

**方案B：下载 whl 包传入内网**

```bash
# 在外网机器上，下载所有依赖包到本地目录
cd doccheck
pip download -r requirements.txt -d ./pip-packages -i https://pypi.tuna.tsinghua.edu.cn/simple
pip download reportlab -d ./pip-packages -i https://pypi.tuna.tsinghua.edu.cn/simple

# 将 app/ 目录（源码）+ pip-packages/ 目录一起打包传入内网
cd ..
tar czf doccheck-offline.tar.gz doccheck

# 在目标服务器上解压后，从本地包安装
cd /path/to/doccheck
python3 -m venv venv
source venv/bin/activate
pip install --no-index --find-links=./pip-packages -r requirements.txt
pip install --no-index --find-links=./pip-packages reportlab
```

> 此时再运行 `deploy.sh`，脚本会自动检测到 `pip-packages/` 目录，直接使用离线模式安装，**不会**尝试连接外网。

### 3.3 初始化数据库

```bash
cd doccheck
python3 scripts/seed.py
```

种子数据会创建：

| 类型 | 内容 |
|:----|:-----|
| 用户 | admin(管理员)、reviewer(审核员)、writer/zhangsan/lisi(编写者) |
| 文档类型 | 管理制度、技术方案、操作手册（含排序） |
| 检查规则 | 每条文档类型绑定 3~6 条预置规则，共 12 条 |
| LLM 配置 | 默认 DeepSeek API 配置（不含 Key，需部署后手工填写） |

### 3.4 启动服务

```bash
# 前台启动（调试用，热重载模式）
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 后台启动（生产用）
nohup venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 > doccheck.log 2>&1 &
```

### 3.5 配置 systemd 服务（推荐生产用）

创建 `/etc/systemd/system/doccheck.service`：

```ini
[Unit]
Description=DocCheck - AI Document Compliance Checker
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/doccheck
ExecStart=/path/to/doccheck/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable doccheck
sudo systemctl start doccheck
```

> ⚠️ 服务默认使用 `Asia/Shanghai`（东八区）时区，无需额外配置。

---

## 4. LLM 引擎配置

### 4.1 通过 Web 页面配置

部署完成后，使用浏览器访问系统，用管理员账号登录：

1. 左侧导航栏 → **管理 → LLM 配置**
2. 填写以下配置项：

| 配置项 | 说明 | 示例值 |
|:------|:-----|:-------|
| API Base URL | LLM 服务的 API 地址（内网或外网） | `https://api.deepseek.com/v1` |
| API Key | 认证密钥 | `sk-xxx...xxxx` |
| Model | 模型名称 | `deepseek-chat` |
| Timeout | 单次调用超时时间（秒） | `120` |
| Max Retries | 失败重试次数 | `3` |
| Temperature | 生成温度（0.0~1.0，越低越严谨） | `0.1` |
| Max Tokens | 最大输出 Token 数 | `4096` |

3. 点击 **保存配置**
4. 上传一个文档测试，检查是否正常返回结果

### 4.2 支持的内外网场景

| 场景 | 配置方式 |
|:----|:---------|
| 外网 LLM API（DeepSeek / OpenAI / 通义千问等） | 填写对应 API 地址和 Key |
| 内网 LLM API（企业内部部署） | 填写内网 API 地址，无需外网 |
| 切换模型 | 直接在页面上修改 Model 字段，保存即可 |

> ⚠️ **安全提示**：API Key 保存在数据库 `system_config` 表中，请确保数据库文件访问权限正确设置。数据库默认路径为 `data/doccheck.db`。

---

## 5. 服务管理

```bash
# 查看服务状态
sudo systemctl status doccheck

# 重启服务
sudo systemctl restart doccheck

# 查看实时日志（Ctrl+C 退出）
sudo journalctl -u doccheck -f

# 停止服务
sudo systemctl stop doccheck

# 查看最近 100 条日志
sudo journalctl -u doccheck -n 100

# 启动服务
sudo systemctl start doccheck
```

---

## 6. HTTPS 配置（可选）

如需 HTTPS 访问，推荐使用 Nginx 反向代理：

```nginx
server {
    listen 443 ssl;
    server_name doccheck.example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

server {
    listen 80;
    server_name doccheck.example.com;
    return 301 https://$server_name$request_uri;
}
```

---

## 7. 升级

### 7.1 有外网（直接拉取最新代码）

```bash
cd /path/to/doccheck
git pull
source venv/bin/activate
pip install -r requirements.txt   # 更新依赖
sudo systemctl restart doccheck   # 重启服务
```

### 7.2 内网无外网（更换源码包）

1. 在外网机器上拉取最新代码
2. 打包源码（不含 `.git` 和 `venv`）：

```bash
cd doccheck
tar czf doccheck-update.tar.gz \
    --exclude='venv' \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    .
```

3. 将 `doccheck-update.tar.gz` 传入内网目标服务器
4. 在内网服务器上替换代码：

```bash
cd /path/to/doccheck

# 备份数据文件（数据库 + 上传的文档）
cp data/doccheck.db data/doccheck.db.bak   # 备份数据库
cp -r uploads uploads.bak                   # 备份上传的文件

# 解压新版本代码
tar xzf /path/to/doccheck-update.tar.gz

# 检查是否有 Python 依赖变更
source venv/bin/activate
pip install -r requirements.txt

# 重启服务
sudo systemctl restart doccheck
```

> 升级不涉及数据库迁移，数据（用户、规则、检查记录）保留不变。如因模型变更需要迁移，会随 Release Notes 说明。

---

## 8. 存储管理

文档上传后，原件保存在 `uploads/` 目录。随着使用时间增长，磁盘占用可能增长。系统内置了 **存储管理** 功能，由管理员在 Web 页面操作。

### 8.1 访问入口

管理员登录 → 左侧导航栏 → **管理 → 存储管理**

### 8.2 功能说明

| 功能 | 说明 |
|:----|:-----|
| 存储概览 | 显示文档记录数、存储文件数、已用空间大小 |
| 按时间清理 | 支持清理 30天前 / 60天前 / 90天前 / 180天前的文档 |
| 预览可清理量 | 每个时间段显示有多少个文档可清理 |
| 确认弹窗 | 点击清理按钮弹出确认框，确认后执行 |
| 进度提示 | 清理过程中显示进度条和状态文字 |
| 审计日志 | 每次清理操作都会被记录到审计日志（操作类型 `storage_cleanup`） |

### 8.3 清理逻辑

- 删除指定天数之前的 **文档记录**（`documents` 表）
- 级联删除关联的 **检查任务**（`check_tasks` 表）、**检查结果**（`check_results` 表）、**报告**（`reports` 表）
- 删除 `uploads/` 目录下的对应物理文件
- **不可恢复**：删除操作是物理删除，请谨慎操作

### 8.4 推荐策略

| 文档类型 | 推荐保留期限 |
|:--------|:-----------|
| 管理制度 | 90 天 |
| 技术方案 | 180 天 |
| 操作手册 | 180 天 |
| 日常操作文档 | 30 天 |

> 💡 **定期清理建议**：如每日工单量较大（如 600 单/日），建议每月执行一次存储清理，或按业务需求自定义周期。

---

## 9. 常见问题

### Q: 服务启动后访问返回 502

检查端口是否被占用：`lsof -i :8000`，修改 `deploy.sh` 中的 `APP_PORT` 或手动指定不同端口后重新部署。

### Q: 上传文档检查一直 pending

1. 进入 管理 → LLM 配置 页，检查 API Base URL 和 Key 是否正确
2. 点击保存后重新上传文档
3. 查看服务日志排查：`sudo journalctl -u doccheck -n 50`

### Q: PDF 导出中文乱码

安装中文字体：
```bash
sudo apt install fonts-noto-cjk
sudo systemctl restart doccheck
```

### Q: 运行一段时间后磁盘空间不足

管理员登录系统，进入 **管理 → 存储管理**，选择合适的时间段清理旧文档。详见第8节。

### Q: 忘记管理员密码

连接数据库直接重置密码：
```bash
cd /path/to/doccheck
source venv/bin/activate
python3 -c "
import bcrypt
import sqlite3
conn = sqlite3.connect('data/doccheck.db')
pw = bcrypt.hashpw(b'newpass123', bcrypt.gensalt()).decode()
conn.execute('UPDATE users SET password_hash=? WHERE username=?', (pw, 'admin'))
conn.commit()
print('密码已重置为: newpass123')
"
```

### Q: 数据库文件在哪里？

默认路径为 `data/doccheck.db`（相对于项目根目录）。如未找到，直接在当前目录下搜索：
```bash
find /path/to/doccheck -name "*.db"
```

### Q: 支持哪些数据库？

当前使用 SQLite，单文件部署，无需额外安装数据库服务。如需迁移到 MySQL/PostgreSQL，需修改 `database.py` 中的数据库连接配置。
