"""
DocCheck · 预置种子数据脚本

用法：
    python3 seed.py

此脚本会自动创建：
    1. 管理员账号（admin / admin123）
    2. 审核员账号（reviewer / review123）
    3. 三种文档类型（管理制度、技术方案、操作手册）
    4. 各类型对应的检查规则（共10+条）
"""

import asyncio
import sys

try:
    import bcrypt
except ImportError:
    import pip
    pip.main(['install', 'bcrypt', '-i', 'https://pypi.tuna.tsinghua.edu.cn/simple'])
    import bcrypt

sys.path.insert(0, '.')

from database import init_db, async_session_factory
from models import User, DocType, Rule
from sqlalchemy import select


async def seed():
    await init_db()
    async with async_session_factory() as db:
        # ── 用户 ─────────────────────────────────────
        users_data = [
            ('admin', 'admin123', '系统管理员', 'admin'),
            ('reviewer', 'review123', '文档审核员', 'reviewer'),
            ('zhangsan', 'doc123456', '张三', 'user'),
            ('lisi', 'doc123456', '李四', 'user'),
        ]
        for username, password, display_name, role in users_data:
            exists = await db.execute(select(User).where(User.username == username))
            if not exists.scalar_one_or_none():
                db.add(User(
                    username=username,
                    password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
                    display_name=display_name,
                    role=role,
                    is_active=True,
                ))
                print(f"  ✅ 用户: {username} / {password}")

        await db.commit()

        # ── 文档类型 ─────────────────────────────────
        doc_types_data = [
            ('管理制度', 1),
            ('技术方案', 2),
            ('操作手册', 3),
        ]
        dts = {}
        for name, sort in doc_types_data:
            exists = await db.execute(select(DocType).where(DocType.name == name))
            dt = exists.scalar_one_or_none()
            if not dt:
                dt = DocType(name=name, sort_order=sort)
                db.add(dt)
                await db.flush()
                print(f"  ✅ 文档类型: {name}")
            dts[name] = dt

        await db.commit()

        # ── 规则 ─────────────────────────────────────
        rules_data = [
            # 管理制度
            ('管理制度', '格式规范', '文档标题应使用一级标题（Heading 1），各级子标题应使用正确的层级结构，不允许无标题直接开始正文。', 'must_fix', 'initial', 1),
            ('管理制度', '段落规范', '正文段落不应包含不必要的手动换行符，每个段落应语义完整、表述清晰。', 'must_fix', 'initial', 2),
            ('管理制度', '编号规范', '文档中的编号列表应当使用自动编号，不允许手动输入数字编号。', 'must_fix', 'initial', 3),
            ('管理制度', '术语一致性', '全文中同一术语应保持一致的表述方式，不允许混用不同翻译或缩写。', 'suggest', 'all', 4),
            ('管理制度', '标点符号', '正文中的标点符号应使用全角中文标点，英文和数字应使用半角字符。', 'must_fix', 'final', 5),
            ('管理制度', '页眉页脚', '文档应包含页眉（文档名称）和页脚（页码），页码从正文开始连续编号。', 'must_fix', 'final', 6),
            # 技术方案
            ('技术方案', '架构描述', '技术方案应包含系统架构描述，包括模块划分、数据流向和技术选型说明。', 'must_fix', 'initial', 1),
            ('技术方案', '接口定义', '涉及接口设计时，应明确定义请求参数、返回格式和错误码。', 'must_fix', 'initial', 2),
            ('技术方案', '安全考量', '技术方案应包含安全方面的考虑，如认证鉴权、数据加密、防注入等。', 'must_fix', 'final', 3),
            # 操作手册
            ('操作手册', '步骤完整', '操作手册中的每一步应完整可执行，不能跳过关键环节。', 'must_fix', 'initial', 1),
            ('操作手册', '截图说明', '关键操作步骤应配有截图或示意图辅助说明。', 'suggest', 'initial', 2),
            ('操作手册', '异常处理', '操作手册应包含常见异常情况的处理说明。', 'must_fix', 'final', 3),
        ]

        for doc_type_name, name, desc, severity, stage, sort in rules_data:
            exists = await db.execute(select(Rule).where(Rule.name == name, Rule.doc_type_id == dts[doc_type_name].id))
            if not exists.scalar_one_or_none():
                db.add(Rule(
                    name=name, description=desc,
                    severity=severity, stage=stage,
                    doc_type_id=dts[doc_type_name].id,
                    sort_order=sort,
                    is_active=True,
                ))

        await db.commit()
        print(f"  ✅ 规则: {len(rules_data)} 条")
        print()
        print("=" * 50)
        print("种子数据创建完成！")
        print(f"管理员: admin / admin123")
        print(f"审核员: reviewer / review123")
        print(f"用户:   zhangsan / doc123456")
        print(f"用户:   lisi / doc123456")
        print(f"文档类型: {len(doc_types_data)} 种")
        print(f"检查规则: {len(rules_data)} 条")
        print("=" * 50)


if __name__ == "__main__":
    print("DocCheck · 种子数据初始化...")
    asyncio.run(seed())
