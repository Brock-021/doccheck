"""
DocCheck AI 检查引擎

批量检查模式：将文档全文 + 全部规则一次发给 LLM，返回结构化结果。
"""

from __future__ import annotations
import json
import asyncio
import logging
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import CheckTask, CheckResult, Report, Rule, DocType
from services.doc_parser import parse_docx

logger = logging.getLogger("doccheck.checker")


SYSTEM_PROMPT = """你是一个文档合规检查助手。请根据以下规则列表逐条检查文档是否符合要求。

对于每条规则，返回一个 JSON 对象：
- rule_name: 规则名称
- compliant: true(符合)/false(不符合)/null(无法判断)
- issue: 问题描述（compliant=true 时可为空字符串）
- location: 原文位置（章节名或段落摘要，能定位到问题所在）
- suggestion: 修改建议（compliant=true 或无法判断时可为空字符串）

请只输出 JSON 数组，不要包含其他文字。"""


async def call_llm(api_base: str, api_key: str, model: str,
                   prompt: str, timeout: int = 60,
                   temperature: float = 0.1, max_tokens: int = 4096) -> str:
    """调用兼容 OpenAI 格式的 LLM API。"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{api_base.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def build_check_prompt(full_text: str, rules: list[dict]) -> str:
    """构造检查 prompt。

    Args:
        full_text: 文档全文
        rules: [{"name": ..., "description": ..., "severity": ...}, ...]
    """
    rules_text = ""
    for i, rule in enumerate(rules, 1):
        rules_text += f"{i}. 规则名称：{rule['name']}\n"
        rules_text += f"   规则描述：{rule['description']}\n"
        rules_text += f"   严重程度：{'必须改' if rule['severity'] == 'must_fix' else '建议改'}\n\n"

    prompt = f"""{SYSTEM_PROMPT}

文档全文：
{full_text[:80000]}  # Truncate to avoid token limits

规则列表：
{rules_text}

请输出 JSON 数组格式的结果。"""
    return prompt


async def run_check(
    db: AsyncSession,
    check_task: CheckTask,
    api_base: str,
    api_key: str,
    model: str,
    llm_timeout: int = 60,
    llm_retries: int = 3,
    temperature: float = 0.1,
    max_tokens: int = 4096,
):
    """执行检查任务（异步后台任务）。"""
    try:
        check_task.status = "running"
        await db.commit()

        # 1. Get document info
        from models import Document
        doc_result = await db.execute(
            select(Document).where(Document.id == check_task.document_id)
        )
        document = doc_result.scalar_one_or_none()
        if not document:
            raise ValueError("文档不存在")

        # 2. Parse document
        parsed = parse_docx(document.file_path)

        # 3. Get rules
        rule_result = await db.execute(
            select(Rule).where(
                Rule.doc_type_id == document.doc_type_id,
                Rule.is_active == True,
                Rule.is_deprecated == False,
            )
        )
        all_rules = rule_result.scalars().all()

        # Filter by stage
        stage = check_task.stage or "initial"
        matched_rules = [
            r for r in all_rules
            if r.stage in ("all", stage)
        ]

        if not matched_rules:
            check_task.status = "done"
            check_task.completed_at = datetime.utcnow()
            await db.commit()
            # Create empty report
            report = Report(
                check_task_id=check_task.id,
                summary_json={
                    "total_rules": 0,
                    "passed": 0,
                    "failed": 0,
                    "unknown": 0,
                    "pass_rate": 0,
                },
            )
            db.add(report)
            await db.commit()
            return

        # 4. Build prompt and call LLM
        rules_data = [
            {"name": r.name, "description": r.description, "severity": r.severity}
            for r in matched_rules
        ]
        prompt = build_check_prompt(parsed["full_text"], rules_data)

        # Retry logic
        llm_response = None
        last_error = None
        for attempt in range(llm_retries):
            try:
                llm_response = await call_llm(
                    api_base, api_key, model, prompt,
                    timeout=llm_timeout, temperature=temperature,
                    max_tokens=max_tokens,
                )
                break
            except Exception as e:
                last_error = str(e)
                logger.warning(f"LLM call attempt {attempt + 1} failed: {e}")
                if attempt < llm_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff

        if llm_response is None:
            check_task.status = "failed"
            check_task.error_message = f"LLM 调用失败（已重试 {llm_retries} 次）: {last_error}"
            check_task.completed_at = datetime.utcnow()
            await db.commit()
            return

        # 5. Parse LLM response
        try:
            # Find JSON array in response
            json_start = llm_response.find("[")
            json_end = llm_response.rfind("]") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = llm_response[json_start:json_end]
            else:
                json_str = llm_response

            results_data = json.loads(json_str)
            if not isinstance(results_data, list):
                raise ValueError("LLM 返回的不是数组")
        except (json.JSONDecodeError, ValueError) as e:
            check_task.status = "failed"
            check_task.error_message = f"LLM 返回格式错误: {e}"
            check_task.completed_at = datetime.utcnow()
            await db.commit()
            return

        # 6. Save check results
        rule_map = {r.name: r for r in matched_rules}
        passed = 0
        failed = 0
        unknown = 0

        for item in results_data:
            rule_name = item.get("rule_name", "")
            rule = rule_map.get(rule_name)
            if not rule:
                continue

            compliant = item.get("compliant")
            compliant_str = str(compliant).lower() if compliant is not None else None

            result = CheckResult(
                check_task_id=check_task.id,
                rule_id=rule.id,
                compliant=compliant_str,
                issue=item.get("issue", ""),
                location=item.get("location", ""),
                original_text="",
                suggestion=item.get("suggestion", ""),
                review_status="pending",
            )
            db.add(result)

            if compliant_str == "true":
                passed += 1
            elif compliant_str == "false":
                failed += 1
            else:
                unknown += 1

        # 7. Create report
        total = len(matched_rules)
        pass_rate = round(passed / total * 100, 1) if total > 0 else 0
        report = Report(
            check_task_id=check_task.id,
            summary_json={
                "total_rules": total,
                "passed": passed,
                "failed": failed,
                "unknown": unknown,
                "pass_rate": pass_rate,
            },
        )
        db.add(report)

        # 8. Update task status
        check_task.status = "done"
        check_task.rule_count = total
        check_task.completed_at = datetime.utcnow()
        await db.commit()

    except Exception as e:
        logger.error(f"Check task {check_task.id} failed: {e}", exc_info=True)
        check_task.status = "failed"
        check_task.error_message = str(e)
        check_task.completed_at = datetime.utcnow()
        await db.commit()
