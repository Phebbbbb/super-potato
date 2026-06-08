"""AI 税务顾问智能体 API"""
import json
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.config import settings
from app.schemas.core import AgentChatRequest

router = APIRouter()

SYSTEM_PROMPT = """你是一位资深中国税务师和注册会计师，拥有20年财税实务经验。你的职责是：

1. 解答用户的财税问题（增值税、企业所得税、个人所得税、印花税等）
2. 根据用户描述的业务场景，给出标准的借贷记账分录建议
3. 分析财务数据，识别潜在税务风险
4. 解读最新税收政策

回答要求：
- 专业、准确，引用具体税率和法规条文
- 对于不确定的问题，明确指出"此问题建议咨询当地税务机关"
- 给出分录时使用标准格式：借：科目名称 金额 / 贷：科目名称 金额
- 用中文回答，简洁明了"""


@router.post("/chat")
async def agent_chat(data: AgentChatRequest, db: Session = Depends(get_db)):
    """AI 税务顾问对话（非流式简化版）"""
    user_message = data.message
    context = data.context

    full_prompt = SYSTEM_PROMPT
    if context:
        full_prompt += f"\n\n当前客户信息：{context}"

    # 如果配置了 LLM API key，调用真实 API
    if settings.llm_api_key and settings.llm_provider == "claude":
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": settings.llm_api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                json={"model": settings.llm_model, "max_tokens": 2048, "system": full_prompt,
                      "messages": [{"role": "user", "content": user_message}]},
            )
            if resp.status_code == 200:
                try:
                    result = resp.json()
                    return {"reply": result["content"][0]["text"], "source": "claude"}
                except (KeyError, IndexError, TypeError) as e:
                    return {"reply": f"AI 响应解析失败: {e}", "source": "error"}
            return {"reply": f"AI 服务调用失败: {resp.status_code}", "source": "error"}

    # 无 API key 时用规则引擎答复
    reply = rule_based_reply(user_message)
    return {"reply": reply, "source": "rule_engine"}


def rule_based_reply(message: str) -> str:
    """基于关键词的规则回复"""
    msg = message.lower()

    if "增值税" in msg and ("起征" in msg or "免税" in msg or "小规模" in msg):
        return """根据现行政策（2026年）：
- 小规模纳税人月销售额不超过10万元（季度30万元）免征增值税
- 适用3%征收率的小规模纳税人，减按1%征收
- 一般纳税人无起征点优惠

注意：免税仅针对增值税普通发票部分，开具增值税专用发票仍需缴纳。"""

    if "个税" in msg or "个人所得税" in msg:
        return """中国个人所得税（工资薪金）采用7级超额累进税率（2024年起）：
- 起征点：5000元/月
- 税率：3% ~ 45%
- 专项附加扣除：子女教育、继续教育、大病医疗、住房贷款利息、住房租金、赡养老人、3岁以下婴幼儿照护

计算公式：应纳税所得额 = 收入 - 5000 - 社保公积金 - 专项附加扣除"""

    if "企业所得税" in msg:
        return """企业所得税基本规定：
- 标准税率：25%
- 小型微利企业优惠：年应纳税所得额≤300万元，减按25%计入应纳税所得额，按20%税率缴纳（实际税负5%）
- 高新技术企业：15%
- 预缴：按季度预缴（每年4/7/10/1月）
- 年度汇算清缴：次年5月31日前完成"""

    if "印花税" in msg:
        return """印花税（2022年7月1日起施行新法）：
- 借款合同：借款金额的0.005‰
- 购销合同：价款的0.3‰
- 技术合同：价款的0.3‰
- 租赁合同：租金的1‰
- 账簿：按件5元
- 资金账簿：实收资本+资本公积的0.25‰"""

    if "分录" in msg or "记账" in msg:
        return """请描述具体业务场景，我来给出借贷分录建议。例如：
- "报销差旅费5000元"
- "购入固定资产设备一台100000元"
- "计提本月工资80000元"

常用分录模板：
差旅费报销：借：管理费用-差旅费 / 贷：银行存款
采购固定资产：借：固定资产 / 贷：银行存款
计提工资：借：管理费用-工资 / 贷：应付职工薪酬"""

    return """您好！我是AI税务顾问，可以帮您解答：
1. 财税政策咨询（如"小规模纳税人增值税起征点"）
2. 记账分录建议（如"报销差旅费的分录"）
3. 税务风险提示
4. 税收优惠政策解读

请具体描述您的问题。"""
