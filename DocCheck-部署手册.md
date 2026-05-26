# DocCheck · 部署手册

## 1. 环境要求

| 项目 | 最低配置 | 推荐配置 |
|:----|:---------|:---------|
| CPU | 2 核 | 4 核 |
| 内存 | 2 GB | 4 GB |
| 磁盘 | 10 GB | 20 GB |
| 操作系统 | Ubuntu 20.04+ / Debian 11+ | Ubuntu 22.04 |
| Python | 3.9+ | 3.11 |
| 网络 | 可访问 LLM API（需外网或内网 API） |  |

## 2. 快速部署（一键脚本）

```bash
# 1. 克隆代码
git clone https://github.com/Brock-021/doccheck.git
cd doccheck

# 2. 一键部署（需 sudo 权限）
sudo bash deploy.sh
```

部署脚本会自动完成：

| 步骤 | 操作 |
|:----|:-----|
| 1/5 | 检查并安装系统依赖（python3, pip, venv） |
| 2/5 | 创建 Python 虚拟环境 |
| 3/5 | 安装 Python 依赖包 |
| 4/5 | 初始化数据库 + 种子数据（管理员账号、文档类型、检查规则） |
| 5/5 | 创建 systemd 服务并启动 |

部署完成后输出：

```
🎉 DocCheck 部署完成！
访问地址: http://<服务器IP>:8000
管理员:   admin / admin123
审核员:   reviewer / review123
```

## 3. 手动部署（分步说明）

如果一键脚本不适用（如非 Ubuntu/Debian 系统），可按以下步骤手动部署。

### 3.1 安装系统依赖

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y python3 python3-pip python3-venv

# 如需 PDF 导出中文支持，安装中文字体
sudo apt install -y fonts-noto-cjk
```

### 3.2 创建虚拟环境并安装依赖

```bash
cd doccheck
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 如需 PDF 导出功能
pip install reportlab
```

### 3.3 初始化数据库

```bash
python3 scripts/seed.py
```

### 3.4 启动服务

```bash
# 前台启动（调试用）
uvicorn main:app --host 0.0.0.0 --port 8000

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

## 4. 配置 LLM 引擎

部署完成后，使用浏览器访问系统，用管理员账号登录：

1. 进入 **管理 → LLM 配置**
2. 填写以下配置项：

| 配置项 | 说明 | 示例值 |
|:------|:-----|:-------|
| API Base URL | LLM 服务的 API 地址 | `https://api.deepseek.com/v1` |
| API Key | 认证密钥 | `sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` |
| Model | 模型名称 | `deepseek-chat` |
| Timeout | 单次调用超时时间（秒） | `120` |
| Max Retries | 失败重试次数 | `3` |
| Temperature | 生成温度（0.0~1.0，越低越严谨） | `0.1` |
| Max Tokens | 最大输出 Token 数 | `4096` |

3. 点击 **保存配置**

> ⚠️ **安全提示**：API Key 保存在数据库 `system_config` 表中，请确保数据库文件访问权限正确设置。

## 5. 服务管理

```bash
# 查看服务状态
sudo systemctl status doccheck

# 重启服务
sudo systemctl restart doccheck

# 查看实时日志
sudo journalctl -u doccheck -f

# 停止服务
sudo systemctl stop doccheck

# 查看最近 100 条日志
sudo journalctl -u doccheck -n 100
```

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

## 7. 升级

```bash
cd /path/to/doccheck
git pull
source venv/bin/activate
pip install -r requirements.txt   # 更新依赖
sudo systemctl restart doccheck   # 重启服务
```

> 升级不涉及数据库迁移，数据（用户、规则、检查记录）保留不变。

## 8. 常见问题

### Q: 服务启动后访问返回 502
检查端口是否被占用：`lsof -i :8000`，修改 `deploy.sh` 中的 `APP_PORT` 或手动指定不同端口。

### Q: 上传文档检查一直 pending
进入 LLM 配置页检查 API Base URL 和 Key 是否正确，点击保存后重新上传文档。

### Q: PDF 导出中文乱码
安装中文字体：`sudo apt install fonts-noto-cjk`，重启服务。

### Q: 忘记管理员密码
连接数据库直接重置密码：
```bash
cd /path/to/doccheck
source venv/bin/activate
python3 -c "
import bcrypt
import sqlite3
conn = sqlite3.connect('doccheck.db')
pw = bcrypt.hashpw(b'newpass123', bcrypt.gensalt()).decode()
conn.execute('UPDATE users SET password_hash=? WHERE username=?', (pw, 'admin'))
conn.commit()
print('密码已重置为: newpass123')
"
```
