"""AI 税务顾问智能体 API — 集成 RAG 税法检索 + 置信度评分"""
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
- 用中文回答，简洁明了
- 如果提供了税法参考条文，请在回答末尾引用来源"""


@router.post("/chat")
async def agent_chat(data: AgentChatRequest, db: Session = Depends(get_db)):
    """AI 税务顾问对话（集成 RAG 税法检索）"""
    user_message = data.message
    context = data.context

    # RAG 检索相关税法
    from app.services.rag_engine import search_tax_law
    rag_result = search_tax_law(user_message, top_k=3)

    full_prompt = SYSTEM_PROMPT
    if rag_result.answer_context:
        full_prompt += f"\n\n【参考税法条文 — 请据此回答并引用来源】\n{rag_result.answer_context}"
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
                    return {
                        "reply": result["content"][0]["text"],
                        "source": "claude",
                        "rag_confidence": rag_result.confidence,
                        "rag_confidence_label": rag_result.confidence_label,
                        "citations": [law["source"] for law in rag_result.laws[:3]],
                    }
                except (KeyError, IndexError, TypeError) as e:
                    return {"reply": f"AI 响应解析失败: {e}", "source": "error"}
            return {"reply": f"AI 服务调用失败: {resp.status_code}", "source": "error"}

    # 无 API key 时用规则引擎答复（也附带 RAG 结果）
    reply = rule_based_reply(user_message)
    if rag_result.primary_citation:
        reply += f"\n\n📚 参考法规：{rag_result.primary_citation}"
        if rag_result.confidence_label != "低":
            reply += f"（匹配度：{rag_result.confidence_label}）"
    return {
        "reply": reply,
        "source": "rule_engine",
        "rag_confidence": rag_result.confidence,
        "rag_confidence_label": rag_result.confidence_label,
        "citations": [law["source"] for law in rag_result.laws[:3]],
    }


# ===== RAG 独立接口 =====

@router.get("/rag/search")
def rag_search(q: str = Query(..., description="搜索关键词"), top_k: int = Query(5, ge=1, le=10)):
    """税法条文检索 — 独立接口"""
    from app.services.rag_engine import search_tax_law
    result = search_tax_law(q, top_k)
    return {
        "query": result.query,
        "laws": result.laws,
        "confidence": result.confidence,
        "confidence_label": result.confidence_label,
        "primary_citation": result.primary_citation,
    }


# ===== 全文搜索接口 =====

@router.get("/search")
def full_text_search(
    q: str = Query(..., description="搜索关键词"),
    collection: str = Query("all", description="索引集合: vouchers/clients/tax_laws/all"),
    top_k: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """全文搜索 — 跨凭证/客户/税法集合的BM25检索"""
    from app.services.search_engine import get_search, index_vouchers, index_clients, index_tax_laws
    from app.models.voucher import AccountingVoucher
    from app.models.client import Client
    import json as _json

    engine = get_search()

    # 按需构建索引（首次搜索时初始化）
    if collection in ("vouchers", "all") and "vouchers" not in engine.list_collections():
        vouchers = db.query(AccountingVoucher).limit(500).all()
        index_vouchers([
            {"id": v.id, "voucher_no": v.voucher_no, "summary": v.summary,
             "maker": v.maker or "", "reviewer": v.reviewer or ""}
            for v in vouchers
        ])

    if collection in ("clients", "all") and "clients" not in engine.list_collections():
        clients = db.query(Client).limit(500).all()
        index_clients([
            {"id": c.id, "name": c.name, "tax_no": c.tax_no,
             "contact_name": c.contact_name or "", "industry": c.industry or ""}
            for c in clients
        ])

    if collection in ("tax_laws", "all") and "tax_laws" not in engine.list_collections():
        from app.services.rag_engine import TAX_LAW_KB
        index_tax_laws(TAX_LAW_KB)

    # 搜索
    if collection == "all":
        from app.services.search_engine import search_all
        all_results = search_all(q, top_k)
        return {
            "query": q,
            "collections": {
                coll: {"results": r.results, "total": r.total, "took_ms": r.took_ms}
                for coll, r in all_results.items()
            },
        }

    result = engine.search(collection, q, top_k)
    return {"query": q, "collection": collection, "results": result.results,
            "total": result.total, "took_ms": result.took_ms}


# ===== 税务风险检测接口 =====

@router.post("/risk-check")
def tax_risk_check(client_id: str = Query(None), db: Session = Depends(get_db)):
    """对指定客户的凭证进行税务风险检测（Benford + Z-Score + 规则引擎）"""
    from app.services.tax_anomaly_detector import analyze_tax_risk
    from app.models.voucher import AccountingVoucher

    q = db.query(AccountingVoucher)
    if client_id:
        q = q.filter(AccountingVoucher.client_id == client_id)

    vouchers = q.order_by(AccountingVoucher.created_at.desc()).limit(200).all()

    if not vouchers:
        return {"has_anomaly": False, "risk_level": "low", "message": "暂无凭证数据"}

    voucher_dicts = []
    amounts = []
    for v in vouchers:
        voucher_dicts.append({
            "id": v.id,
            "voucher_no": v.voucher_no,
            "voucher_date": v.voucher_date.isoformat() if v.voucher_date else "",
            "summary": v.summary,
            "total_debit": v.total_debit,
            "total_credit": v.total_credit,
            "status": v.status,
        })
        amounts.append(v.total_debit or 0)

    result = analyze_tax_risk(voucher_dicts, amounts)

    return {
        "client_id": client_id,
        "voucher_count": len(vouchers),
        "has_anomaly": result.has_anomaly,
        "risk_level": result.risk_level,
        "risk_score": result.risk_score,
        "findings": result.findings,
        "recommendation": result.recommendation,
    }


# ===== Dashboard 风险摘要 =====

@router.get("/risk-summary")
def tax_risk_summary(db: Session = Depends(get_db)):
    """全局税务风险摘要（Dashboard 用）"""
    from app.services.tax_anomaly_detector import analyze_tax_risk, check_benford
    from app.models.voucher import AccountingVoucher
    from app.models.filing import TaxFiling

    vouchers = db.query(AccountingVoucher).order_by(AccountingVoucher.created_at.desc()).limit(500).all()
    amounts = [v.total_debit for v in vouchers if v.total_debit]

    # Benford 快速检测
    benford = check_benford(amounts) if len(amounts) >= 30 else None

    # 逾期申报检测
    from datetime import date
    overdue_filings = db.query(TaxFiling).filter(
        TaxFiling.status == "pending_review"
    ).count()

    risk_clients = set()
    for v in vouchers:
        if v.status == "draft" and v.client_id:
            risk_clients.add(v.client_id)

    return {
        "benford_suspicious": benford["is_suspicious"] if benford else None,
        "benford_chi2": benford["chi2_statistic"] if benford else None,
        "total_vouchers_analyzed": len(amounts),
        "overdue_filings": overdue_filings,
        "draft_voucher_count": sum(1 for v in vouchers if v.status == "draft"),
        "clients_with_drafts": len(risk_clients),
        "overall_risk": "high" if (benford and benford["is_suspicious"]) else ("medium" if overdue_filings > 0 else "low"),
    }


def rule_based_reply(message: str) -> str:
    """基于关键词的规则回复 — 覆盖主要税种和常见业务场景"""
    msg = message.lower()

    # === 增值税 ===
    if "增值税" in msg:
        if "一般纳税人" in msg:
            return """增值税一般纳税人：
- 税率：13%（货物）、9%（交通/建筑/邮政/基础电信/不动产）、6%（服务业/现代服务/金融/生活服务）
- 计算公式：应纳税额 = 当期销项税额 - 当期进项税额
- 销项税额 = 不含税销售额 × 税率
- 进项税额可抵扣，须取得合规增值税专用发票
- 申报期限：每月结束后15日内（一般纳税人按月申报）

注意：进项税额抵扣需通过增值税发票综合服务平台勾选认证。"""
        return """增值税（2026年现行政策）：

【小规模纳税人】
- 月销售额≤10万元（季度≤30万元）免征增值税
- 适用3%征收率的减按1%征收
- 开具增值税专用发票部分不享受免税

【一般纳税人】
- 税率：13% / 9% / 6% 三档
- 按月申报，每月结束后15日内
- 可抵扣进项税额（需取得合规专票）

【常见问题】
- 混合销售按主业税率
- 兼营分别核算，否则从高适用税率"""

    # === 企业所得税 ===
    if "企业所得税" in msg or ("企业" in msg and "所得税" in msg):
        return """企业所得税：
- 标准税率：25%
- 小型微利企业：年应纳税所得额≤300万元，减按25%计入应纳税所得额，按20%税率缴纳（实际税负5%）
- 高新技术企业：15%
- 西部大开发鼓励类企业：15%
- 预缴：按季度预缴（每年4/7/10/1月）
- 年度汇算清缴：次年5月31日前完成
- 亏损弥补：向后结转不超过5年（高新技术/科技型中小企业不超过10年）"""

    # === 个人所得税 ===
    if "个税" in msg or "个人所得税" in msg:
        return """个人所得税（工资薪金）7级超额累进税率：

| 级数 | 应纳税所得额（月） | 税率 | 速算扣除数 |
|------|-------------------|------|-----------|
| 1    | ≤3,000            | 3%   | 0         |
| 2    | 3,000-12,000      | 10%  | 210       |
| 3    | 12,000-25,000     | 20%  | 1,410     |
| 4    | 25,000-35,000     | 25%  | 2,660     |
| 5    | 35,000-55,000     | 30%  | 4,410     |
| 6    | 55,000-80,000     | 35%  | 7,160     |
| 7    | >80,000           | 45%  | 15,160    |

- 起征点：5,000元/月（6万元/年）
- 专项附加扣除：子女教育(2000/月/孩)、继续教育(400/月)、大病医疗(据实限额8万)、住房贷款利息(1000/月)、住房租金(800-1500/月)、赡养老人(3000/月)、婴幼儿照护(2000/月/孩)
- 公式：应纳税所得额 = 收入 - 5000 - 社保公积金 - 专项附加扣除"""

    # === 印花税 ===
    if "印花税" in msg:
        return """印花税（2022年7月1日起施行）：

- 借款合同：借款金额 × 0.005‰
- 购销合同：价款 × 0.3‰
- 承揽合同：报酬 × 0.3‰
- 建设工程合同：价款 × 0.3‰
- 技术合同：价款 × 0.3‰
- 租赁合同：租金 × 1‰
- 运输合同：运费 × 0.3‰
- 财产保险合同：保费 × 1‰
- 实收资本+资本公积：合计 × 0.25‰（减半征收）
- 账簿：免印花税"""

    # === 消费税 ===
    if "消费税" in msg:
        return """消费税（烟/酒/成品油/汽车/奢侈品等15类应税消费品）：

- 卷烟：从价56%或36% + 从量0.003元/支
- 白酒：从价20% + 从量0.5元/500g
- 啤酒：甲类250元/吨、乙类220元/吨
- 成品油：汽油1.52元/升、柴油1.2元/升
- 乘用车：1%~40%（按排量分级）
- 高档手表（≥1万元）：20%
- 贵重首饰及珠宝玉石：5%或10%
- 化妆品：15%

注意：消费税是价内税，在生产/进口环节征收（部分在批发/零售环节）。"""

    # === 房产税 ===
    if "房产税" in msg:
        return """房产税：

- 从价计征：房产原值×(1-扣除比例10%~30%)×1.2%（按年）
- 从租计征：租金收入×12%
- 个人所有非营业用房产暂免房产税
- 纳税期限：按年计算、分期缴纳（各省具体规定不同）

注意：房产税由产权所有人缴纳，一般在房产所在地税务机关申报。"""

    # === 城镇土地使用税 ===
    if "土地使用税" in msg or "城镇土地使用税" in msg:
        return """城镇土地使用税：
- 以实际占用的土地面积为计税依据
- 税额：大城市1.5-30元/㎡、中等城市1.2-24元/㎡、小城市0.9-18元/㎡、县城/建制镇/工矿区0.6-12元/㎡
- 按年计算、分期缴纳
- 免税：国家机关/军队/公园/农林牧渔用地等"""

    # === 车船税 ===
    if "车船税" in msg:
        return """车船税（按年申报缴纳）：
- 乘用车：60元-5400元/年（按排量分级，1.0L以下60-360元，4.0L以上3600-5400元）
- 商用客车：480-1440元/年
- 商用货车：按整备质量16-120元/吨
- 摩托车：36-180元/年
- 船舶：按净吨位3-6元/吨
- 新能源汽车免征车船税"""

    # === 契税 ===
    if "契税" in msg:
        return """契税（2021年9月1日起施行）：

- 税率：3%-5%（各省在此幅度内确定）
- 个人购买家庭唯一住房（≤90㎡）：减按1%
- 个人购买家庭唯一住房（>90㎡）：减按1.5%
- 个人购买家庭第二套改善性住房（≤90㎡）：减按1%
- 个人购买家庭第二套改善性住房（>90㎡）：减按2%
- 计税依据：成交价格（不含增值税）"""

    # === 附加税费 ===
    if "附加税" in msg or "城建税" in msg or "教育费附加" in msg:
        return """附加税费（以实际缴纳的增值税为计税依据）：

- 城市维护建设税：市区7%、县城/镇5%、其他1%
- 教育费附加：3%
- 地方教育附加：2%（多数省份）
- 合计附加率：市区12%、县城10%、其他6%

注意：小规模纳税人可减半征收（至2027年底）。"""

    # === 分录 ===
    if "分录" in msg or "记账" in msg or "怎么做账" in msg:
        return """请描述具体业务场景，我来给出借贷分录建议。例如：
- "报销差旅费5000元，银行存款支付"
- "购入固定资产设备100000元，款未付"
- "计提本月工资80000元"
- "销售商品收入50000元，款已收"

常用分录：
- 差旅报销：借：管理费用-差旅费 / 贷：银行存款
- 采购固定资产：借：固定资产 / 借：应交增值税-进项税额 / 贷：应付账款
- 计提工资：借：管理费用/销售费用-工资 / 贷：应付职工薪酬
- 确认收入：借：银行存款 / 贷：主营业务收入 / 贷：应交增值税-销项税额
- 计提折旧：借：管理费用/制造费用-折旧 / 贷：累计折旧
- 结转成本：借：主营业务成本 / 贷：库存商品"""

    # === 发票相关 ===
    if "发票" in msg or "开票" in msg:
        if "数电票" in msg or "全电" in msg:
            return """数电票（全面数字化的电子发票）：
- 2025年起全国推广，无需税控设备
- 通过电子税务局网页端或APP开具
- 无需领票、无需发票验旧
- 自动归集至税务数字账户
- 格式：XML（结构化数据）+ PDF/OFD（版式展示）
- 红字数电票需原票已入账或已抵扣方可开具"""
        return """发票管理要点：

- 增值税专用发票：可抵扣进项税，仅限一般纳税人取得
- 增值税普通发票：不可抵扣进项税
- 数电票（全电发票）：电子税务局直接开具，全国通用
- 发票认证期限：无期限限制（2017年7月1日后开具的）
- 发票丢失：可使用销售方记账联复印件入账
- 小规模纳税人可自开或代开增值税专用发票"""

    # === 小规模纳税人 ===
    if "小规模" in msg:
        return """小规模纳税人（2026年政策）：

- 认定标准：年应征增值税销售额≤500万元
- 征收率：3%（现行减按1%）
- 月销售额≤10万元（季度≤30万元）：免征增值税
- 不可抵扣进项税额
- 按季度申报（可选按月）
- 可申请代开/自开增值税专用发票（专票部分不免税）"""

    # === 一般纳税人 ===
    if "一般纳税人" in msg:
        return """一般纳税人：

- 年应税销售额>500万元必须登记
- 不足500万元可自愿申请
- 税率：13%/9%/6%
- 可抵扣进项税额
- 按月申报增值税
- 需配备财务核算健全"""

    return """您好！我是AI税务顾问，可以帮您解答以下问题：

**政策咨询**：增值税、企业所得税、个人所得税、消费税、印花税、房产税、契税、车船税、附加税等

**记账指导**：各类业务场景的借贷分录建议（如"报销差旅费怎么做分录"）

**开票指导**：数电票开具流程、发票类型选择、红字发票处理

**申报指导**：申报期限、填报要点、优惠政策适用

**风险提示**：税负率异常、申报逾期后果、常见税务风险点

请描述您遇到的具体问题，我会尽力解答。如涉及重大税务决策，建议咨询当地税务机关或注册税务师。"""
