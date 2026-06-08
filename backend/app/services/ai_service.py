"""AI 记账服务：调用 LLM 基于原始凭证数据智能生成借贷分录"""
import json
import httpx
from app.config import settings

AI_SYSTEM_PROMPT = """你是一位资深注册会计师，精通中国企业会计准则。

## 任务
根据提供的原始凭证结构化数据，生成标准借贷记账分录。

## 规则
1. 必须遵循"有借必有贷，借贷必相等"原则
2. 借方合计必须等于贷方合计（精确到分）
3. 每条分录包含：account_code(科目编码)、account_name(科目名称)、debit(借方金额)、credit(贷方金额)、summary(摘要)
4. 常见科目编码参考：
   - 1002 银行存款、1122 应收账款、2202 应付账款
   - 6001 主营业务收入、6401 主营业务成本
   - 6602 管理费用、6603 财务费用、6601 销售费用
   - 222101 应交增值税、6801 所得税费用
   - 1601 固定资产、1405 库存商品、1701 无形资产
5. 输出严格 JSON 格式，不要任何额外文字

## 输出格式
{
  "summary": "凭证摘要（简洁描述业务）",
  "entries": [
    {"account_code": "1002", "account_name": "银行存款", "debit": 0, "credit": 11300.00, "summary": "支付XX货款"},
    {"account_code": "6602", "account_name": "管理费用", "debit": 10000.00, "credit": 0, "summary": "XX费用"},
    {"account_code": "222101", "account_name": "应交增值税", "debit": 1300.00, "credit": 0, "summary": "进项税额"}
  ]
}
"""


async def ai_generate_voucher(documents: list[dict]) -> dict:
    """调用 LLM 生成记账凭证分录"""
    # 构建 prompt
    docs_text = json.dumps(documents, ensure_ascii=False, indent=2)
    user_prompt = f"以下是从原始凭证提取的结构化数据，请生成借贷分录：\n\n{docs_text}"

    if settings.llm_api_key and settings.llm_provider == "claude":
        return await _call_claude(user_prompt)
    elif settings.llm_api_key and settings.llm_provider == "openai":
        return await _call_openai(user_prompt)
    else:
        # 无 LLM API 时使用规则引擎兜底
        return _fallback_rule_engine(documents)


async def _call_claude(user_prompt: str) -> dict:
    """调用 Claude API"""
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.llm_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": settings.llm_model,
                "max_tokens": 2048,
                "system": AI_SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_prompt}],
            },
        )
        data = resp.json()
        try:
            content = data["content"][0]["text"]
        except (KeyError, IndexError, TypeError):
            return {"summary": "AI 响应解析失败", "entries": [], "error": str(data)[:200]}
        return _parse_llm_response(content)


async def _call_openai(user_prompt: str) -> dict:
    """调用 OpenAI API"""
    base_url = settings.llm_base_url or "https://api.openai.com/v1"
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.llm_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o",
                "messages": [
                    {"role": "system", "content": AI_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.3,
            },
        )
        data = resp.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return {"summary": "AI 响应解析失败", "entries": [], "error": str(data)[:200]}
        return _parse_llm_response(content)


def _parse_llm_response(content: str) -> dict:
    """解析 LLM 返回的 JSON"""
    # 去除可能的 markdown 包裹
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1])
    return json.loads(content)


def _fallback_rule_engine(documents: list[dict]) -> dict:
    """
    兜底方案：纯规则引擎生成凭证（无需数据库）
    当没有配置 LLM API 时使用
    """
    from app.services.voucher_service import match_account_by_keyword
    entries = []
    for doc in documents:
        ocr = doc.get("ocr_structured") or {}
        if not ocr:
            continue
        total = ocr.get("total_amount") or 0
        excluding_tax = ocr.get("amount_excluding_tax") or total
        tax_amount = ocr.get("tax_amount") or 0
        items = ocr.get("items", [])
        doc_type = doc.get("doc_type", "invoice")
        summary = doc.get("summary", "")

        if doc_type == "invoice":
            if items:
                for item in items:
                    item_name = item.get("name", "")
                    item_amount = item.get("amount") or item.get("unit_price", 0) * item.get("quantity", 1)
                    code, name, direction = match_account_by_keyword(item_name, summary)
                    entries.append({"account_code": code, "account_name": name, "debit": round(item_amount, 2), "credit": 0, "summary": item_name})
            else:
                code, name, direction = match_account_by_keyword(summary or "其他", summary)
                entries.append({"account_code": code, "account_name": name, "debit": round(excluding_tax, 2), "credit": 0, "summary": summary or "采购"})
            if tax_amount > 0:
                entries.append({"account_code": "222101", "account_name": "应交增值税", "debit": round(tax_amount, 2), "credit": 0, "summary": "进项税额"})
            entries.append({"account_code": "1002", "account_name": "银行存款", "debit": 0, "credit": round(total, 2), "summary": "支付货款"})

    merged = {}
    for e in entries:
        key = e["account_code"]
        if key in merged:
            merged[key]["debit"] += e["debit"]
            merged[key]["credit"] += e["credit"]
        else:
            merged[key] = dict(e)

    return {"summary": "自动生成凭证", "entries": [v for v in merged.values()]}
