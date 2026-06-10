"""工商中心 API — 公司注册/注销/股权变更 + 操作日志"""
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.db import get_db
from app.services.auth import get_current_user, require_admin
from app.services.audit_service import log_action

router = APIRouter()


# ============================================================
# 请求模型
# ============================================================

class RegistrationRequest(BaseModel):
    client_id: str
    company_name: str
    legal_person: str
    registered_capital: float = 0
    business_scope: str = ""
    address: str = ""
    contact_phone: str = ""
    shareholders: str = "[]"
    status: str = "draft"


class DeregistrationRequest(BaseModel):
    client_id: str
    reason: str = ""
    tax_cleared: bool = False
    debt_cleared: bool = False
    announcement_date: str = ""
    status: str = "draft"


class EquityChangeRequest(BaseModel):
    client_id: str
    change_type: str = "transfer"
    from_person: str = ""
    to_person: str = ""
    ratio: float = 0
    amount: float = 0
    effective_date: str = ""
    status: str = "draft"


def _build_detail(client_id: str, **kwargs) -> dict:
    d = {"client_id": client_id}
    d.update(kwargs)
    return d


def _log_to_dict(l) -> dict:
    detail = None
    if l.detail:
        try:
            detail = json.loads(l.detail)
        except Exception:
            detail = l.detail
    return {
        "id": l.id,
        "target_type": l.target_type,
        "target_id": l.target_id,
        "action": l.action,
        "operator": l.operator,
        "detail": detail,
        "created_at": l.created_at.isoformat() if l.created_at else None,
    }


TARGET_TYPES = ["company_registration", "company_deregistration", "equity_change", "annual_report"]


# ============================================================
# 公司注册
# ============================================================

@router.get("/registration")
def list_registrations(
    client_id: str = Query(None),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    from app.models.audit_log import AuditLog
    q = db.query(AuditLog).filter(AuditLog.target_type == "company_registration")
    total = q.count()
    items = q.order_by(AuditLog.created_at.desc()).limit(100).all()
    result = [_log_to_dict(l) for l in items]
    if client_id:
        result = [r for r in result if r.get("detail", {}).get("client_id") == client_id]
    return {"items": result, "total": len(result)}


@router.post("/registration")
def create_registration(
    body: RegistrationRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    record_id = uuid.uuid4().hex
    log_action(db, target_type="company_registration", target_id=record_id,
               action="created", operator=current_user.display_name or current_user.username,
               detail=_build_detail(body.client_id,
                   company_name=body.company_name, legal_person=body.legal_person,
                   registered_capital=body.registered_capital, business_scope=body.business_scope,
                   address=body.address, shareholders=body.shareholders, status=body.status))
    db.commit()
    return {"id": record_id, "message": "公司注册申请已创建", "official_url": "https://www.gsxt.gov.cn/"}


@router.patch("/registration/{record_id}")
def update_registration(
    record_id: str,
    body: RegistrationRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    log_action(db, target_type="company_registration", target_id=record_id,
               action="updated", operator=current_user.display_name or current_user.username,
               detail=_build_detail(body.client_id, company_name=body.company_name, status=body.status))
    db.commit()
    return {"message": "已更新"}


# ============================================================
# 公司注销
# ============================================================

@router.get("/deregistration")
def list_deregistrations(
    client_id: str = Query(None),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    from app.models.audit_log import AuditLog
    q = db.query(AuditLog).filter(AuditLog.target_type == "company_deregistration")
    items = q.order_by(AuditLog.created_at.desc()).limit(100).all()
    result = [_log_to_dict(l) for l in items]
    if client_id:
        result = [r for r in result if r.get("detail", {}).get("client_id") == client_id]
    return {"items": result, "total": len(result)}


@router.post("/deregistration")
def create_deregistration(
    body: DeregistrationRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    record_id = uuid.uuid4().hex
    log_action(db, target_type="company_deregistration", target_id=record_id,
               action="created", operator=current_user.display_name or current_user.username,
               detail=_build_detail(body.client_id,
                   reason=body.reason, tax_cleared=body.tax_cleared,
                   debt_cleared=body.debt_cleared, announcement_date=body.announcement_date,
                   status=body.status))
    db.commit()
    return {"id": record_id, "message": "注销申请已创建", "official_url": "https://www.gsxt.gov.cn/"}


# ============================================================
# 股权变更
# ============================================================

@router.get("/equity-change")
def list_equity_changes(
    client_id: str = Query(None),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    from app.models.audit_log import AuditLog
    q = db.query(AuditLog).filter(AuditLog.target_type == "equity_change")
    items = q.order_by(AuditLog.created_at.desc()).limit(100).all()
    result = [_log_to_dict(l) for l in items]
    if client_id:
        result = [r for r in result if r.get("detail", {}).get("client_id") == client_id]
    return {"items": result, "total": len(result)}


@router.post("/equity-change")
def create_equity_change(
    body: EquityChangeRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    record_id = uuid.uuid4().hex
    log_action(db, target_type="equity_change", target_id=record_id,
               action="created", operator=current_user.display_name or current_user.username,
               detail=_build_detail(body.client_id,
                   change_type=body.change_type, from_person=body.from_person,
                   to_person=body.to_person, ratio=body.ratio, amount=body.amount,
                   effective_date=body.effective_date, status=body.status))
    db.commit()
    return {"id": record_id, "message": "股权变更申请已创建", "official_url": "https://www.gsxt.gov.cn/"}


# ============================================================
# 工商中心操作日志
# ============================================================

@router.get("/audit-log")
def business_audit_log(
    client_id: str = Query(None),
    action: str = Query(None),
    target_type: str = Query(None),
    page: int = Query(1),
    page_size: int = Query(50),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    from app.models.audit_log import AuditLog
    q = db.query(AuditLog).filter(AuditLog.target_type.in_(TARGET_TYPES))
    if target_type:
        q = q.filter(AuditLog.target_type == target_type)
    if action:
        q = q.filter(AuditLog.action == action)

    total = q.count()
    items = q.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    result = [_log_to_dict(l) for l in items]

    if client_id:
        result = [r for r in result if r.get("detail", {}).get("client_id") == client_id]

    return {"items": result, "total": total, "page": page, "page_size": page_size}


# ============================================================
# 企业信息自动查询（替代企查查/天眼查）
# ============================================================

class LookupRequest(BaseModel):
    keyword: str  # 企业名称 或 统一社会信用代码


class NameSuggestionRequest(BaseModel):
    location: str = ""            # 注册地（城市/省份）
    industry_keyword: str = ""    # 行业关键词
    business_scope: str = ""      # 经营范围描述
    count: int = 15               # 建议数量


class BusinessAgentRequest(BaseModel):
    message: str                  # 用户消息
    context: str = ""             # 可选上下文（如当前客户信息）


@router.post("/lookup")
def lookup_company(
    body: LookupRequest,
    _=Depends(require_admin),
):
    """自动查询企业工商信息（从国家企业信用信息公示系统）"""
    from app.services.company_lookup import lookup_company_sync

    info = lookup_company_sync(body.keyword)
    return {
        "success": bool(info.name),
        "data": {
            "name": info.name,
            "tax_no": info.tax_no,
            "legal_person": info.legal_person,
            "registered_capital": info.registered_capital,
            "paid_capital": info.paid_capital,
            "established_date": info.established_date,
            "business_status": info.business_status,
            "company_type": info.company_type,
            "industry": info.industry,
            "address": info.address,
            "business_scope": info.business_scope,
            "registration_authority": info.registration_authority,
            "shareholders": info.shareholders,
            "key_personnel": info.key_personnel,
            "change_records": info.change_records,
            "risk_info": info.risk_info,
            "source_url": info.source_url,
        },
    }


# ============================================================
# 智能公司起名
# ============================================================

@router.post("/name-suggestions")
def suggest_company_names(
    body: NameSuggestionRequest,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """智能起名：从已注销企业回收字号 + AI算法生成"""
    import random

    # --- 起名字库（内联，避免 import 问题）---
    LOCATIONS_ = ["北京","上海","深圳","广州","杭州","成都","武汉","南京","重庆","天津","苏州","西安","长沙","郑州","青岛","大连","厦门","宁波","合肥","福州"]
    AUSPICIOUS = ["鑫","瑞","盛","达","通","泰","丰","源","恒","昌","诚","信","德","仁","和","智","创","卓","启","腾","博","嘉","锦","辉","华","宏","远","安","顺","康","翔","龙","鹏","骏","鸿","辰","泽","润","益","凯","荣","晟","鼎","汇","融","聚","升","捷","锐","领"]
    INDUSTRY_MAP = {"科技":["科技","信息","数据","智能","数字"],"贸易":["商贸","贸易","实业","供应链"],"咨询":["咨询","管理","顾问","服务"],"餐饮":["餐饮","食品","饮食"],"建筑":["建筑","工程","建设","装饰"],"教育":["教育","培训","文化"],"医疗":["医疗","医药","健康","生物"],"金融":["金融","投资","资产","资本"],"物流":["物流","运输","供应链"],"制造":["制造","机械","电子","设备"],"电商":["电商","电子商务","网络"],"新能源":["新能源","能源","电力","光伏"],"文化":["文化","传媒","广告","设计"],"农业":["农业","生态","农产品"]}
    COMPANY_TYPES_ = ["有限公司","有限责任公司","股份有限公司","集团有限公司","实业有限公司","科技股份有限公司"]
    BRANDS_2 = ["创新","卓越","领航","远航","启航","腾飞","鹏程","锦绣","瑞丰","鑫源","盛世","宏图","博远","诚信","嘉和","锦程","辉达","华盛","安泰","康盛","龙腾","骏达","鸿运","泽润","益丰","凯旋","荣昌","晟达","鼎盛","汇通","聚源","升泰","捷达","锐志","领创","鑫达","瑞华","丰源","恒盛","昌隆","通达","泰和","德润","仁和","智创","卓然"]
    BRANDS_3 = ["鑫瑞丰","盛达通","泰和源","恒昌瑞","诚信达","德仁和","智创卓","启腾飞","博嘉锦","辉华宏","远安顺","康盛达","龙腾飞","骏驰远","鸿运达","泽润丰","益凯荣","晟鼎汇","融聚升","捷锐领","创智汇","鑫源盛","瑞华丰","通达信","安泰和"]

    def _detect_industry(scope: str, keyword: str) -> str:
        combined = (scope or "") + (keyword or "")
        scores = {}
        for ind, terms in INDUSTRY_MAP.items():
            sc = sum(len(t) for t in terms if t in combined)
            if keyword and ind in keyword: sc += 10
            if sc > 0: scores[ind] = sc
        return max(scores, key=scores.get) if scores else "科技"

    def _extract_brand(name: str) -> str:
        for ct in COMPANY_TYPES_:
            if ct in name: name = name.replace(ct, "")
        for loc in sorted(LOCATIONS_, key=len, reverse=True):
            if name.startswith(loc): name = name[len(loc):]; break
        for terms in INDUSTRY_MAP.values():
            for t in sorted(terms, key=len, reverse=True):
                if name.endswith(t): name = name[:-len(t)]; break
        return name.strip()

    def _meaning(brand: str, industry: str) -> str:
        m = {"鑫":"财富兴盛","瑞":"吉祥如意","盛":"繁荣昌盛","达":"事业通达","通":"畅通无阻","泰":"国泰民安","丰":"丰收富足","源":"财源广进","恒":"恒久长远","昌":"繁荣昌盛","诚":"诚信为本","信":"信誉卓著","德":"厚德载物","仁":"仁者爱人","和":"和谐共赢","智":"智慧创新","创":"创新进取","卓":"卓越不凡","启":"开启未来","腾":"腾飞发展","博":"博学广纳","嘉":"嘉誉美名","锦":"锦绣前程","辉":"辉煌成就","华":"华彩绽放","宏":"宏图大展","远":"远见卓识","安":"稳健安全","顺":"顺风顺水","康":"健康发展","翔":"翱翔天际","龙":"龙腾四海","鹏":"鹏程万里","骏":"骏马奔腾","鸿":"鸿运当头","泽":"惠泽天下","润":"滋润万物","益":"增益价值","凯":"凯旋而归","领":"行业领先","鼎":"鼎立天下","汇":"汇聚英才","融":"融通四海","聚":"聚力前行","升":"步步高升","捷":"捷足先登","锐":"锐意进取"}
        parts = [f"{ch}({m[ch]})" for ch in brand if ch in m]
        return (",".join(parts) if parts else "寓意美好") + f"，适合{industry}行业发展"

    industry = _detect_industry(body.business_scope, body.industry_keyword)
    loc = body.location.strip() if body.location else ""
    loc_str = loc + ("市" if loc and len(loc) <= 3 and not loc.endswith("市") else "") if loc else "北京"
    industry_term = INDUSTRY_MAP.get(industry, ["科技"])[0]
    ct = "有限公司"
    seen_brands: set = set()
    items: list = []

    # 来源1: 已注销企业字号回收
    try:
        from app.models.audit_log import AuditLog
        recs = db.query(AuditLog).filter(AuditLog.target_type == "company_deregistration").order_by(AuditLog.created_at.desc()).limit(50).all()
        for rec in recs:
            if len(items) >= 5: break
            try: detail = json.loads(rec.detail) if rec.detail else {}
            except Exception: continue
            cn = detail.get("company_name", "")
            if not cn: continue
            brand = _extract_brand(cn)
            if not brand or len(brand) < 2 or brand in seen_brands: continue
            seen_brands.add(brand)
            items.append({"full_name": f"{loc_str}{brand}{industry_term}{ct}", "brand": brand, "source": "deregistered", "score": 85, "available": True, "meaning": f"回收字号「{brand}」，原企业已注销，字号可重新使用"})
    except Exception: pass

    # 来源2: 算法生成
    brands_set: set = set()
    for bp in random.sample(BRANDS_2, min(12, len(BRANDS_2))): brands_set.add(bp[:2])
    for bp in random.sample(BRANDS_3, min(8, len(BRANDS_3))): brands_set.add(bp)
    for aus in random.sample(AUSPICIOUS, min(8, len(AUSPICIOUS))): brands_set.add(aus + random.choice(["创","盛","达","源","通","泰"]))
    kw = body.industry_keyword
    if kw and len(kw) >= 2:
        for ch in random.sample(AUSPICIOUS, min(4, len(AUSPICIOUS))): brands_set.add(kw[:2] + ch)
        for ch in random.sample(["创","盛","达","源","通","泰"] + AUSPICIOUS[:5], min(4, 15)): brands_set.add(ch + kw[:1] if kw else ch + "业")
    while len(brands_set) < 20:
        brands_set.add(random.choice(AUSPICIOUS) + random.choice(AUSPICIOUS))

    for brand in brands_set:
        if len(items) >= body.count: break
        if brand in seen_brands: continue
        seen_brands.add(brand)
        score = 70 + sum(5 for ch in brand if ch in AUSPICIOUS) + (10 if kw and kw[:2] in brand else 0)
        items.append({"full_name": f"{loc_str}{brand}{industry_term}{ct}", "brand": brand, "source": "ai_generated", "score": min(score, 95), "available": True, "meaning": _meaning(brand, industry)})

    items.sort(key=lambda s: s["score"], reverse=True)
    return {"industry": items[0]["full_name"] if items else "", "items": items[:body.count]}


# ============================================================
# 工商智能体 — 独立于税务智能体的工商业务对话
# ============================================================

BUSINESS_SYSTEM_PROMPT = """你是一位工商注册代理专家，精通中国公司注册、注销、股权变更、工商年报等业务。你的职责：

1. 解答公司注册流程问题（核名、提交材料、领取执照、刻章、银行开户、税务登记）
2. 解答公司注销流程（简易注销 vs 一般注销、清算组备案、债权人公告、税务注销、工商注销）
3. 解答股权变更（转让协议、股东会决议、税务申报、工商变更登记）
4. 解答工商年报（填报时间、内容要求、逾期后果）
5. 推荐公司名称（根据地区、行业、经营范围生成好名字）
6. 查询企业工商信息（通过统一社会信用代码或企业名称）

回答要求：
- 专业、准确，引用具体法规条文（公司法、市场主体登记管理条例）
- 用中文回答，简洁明了，分步骤说明
- 涉及具体操作时给出官方网址"""


def _detect_business_intent(msg: str) -> str:
    """检测工商业务意图"""
    m = msg
    if any(kw in m for kw in ["起名", "取名", "起公司名", "公司名", "企业名", "字号", "命名", "推荐名称", "起个名"]):
        return "naming"
    if any(kw in m for kw in ["注册", "开公司", "成立公司", "创办", "设立公司", "注册流程", "注册公司"]):
        return "registration"
    if any(kw in m for kw in ["注销", "解散", "关公司", "停业", "吊销", "注销流程"]):
        return "deregistration"
    if any(kw in m for kw in ["股权", "股东", "转股", "增资", "减资", "股份转让", "股权变更"]):
        return "equity"
    if any(kw in m for kw in ["年报", "工商年报", "年检", "年报公示", "逾期年报"]):
        return "annual_report"
    if any(kw in m for kw in ["查询", "查一下", "企查查", "天眼查", "企业信息", "信用代码", "工商信息"]):
        return "lookup"
    return "general"


def _naming_response(msg: str, db) -> str:
    """起名对话回复（复用 name-suggestions 逻辑）"""
    # 复用上面 suggest_company_names 的内联逻辑
    import random

    locations_list = ["北京","上海","深圳","广州","杭州","成都","武汉","南京","重庆","天津","苏州","西安","长沙","郑州","青岛","大连","厦门","宁波","合肥","福州"]
    loc = ""
    for l in locations_list:
        if l in msg:
            loc = l
            break

    industries_map = {"科技": ["科技","技术","互联网","软件","IT","数据"],
                      "贸易": ["贸易","商贸","外贸","进出口","供应链"],
                      "餐饮": ["餐饮","食品","外卖","食堂","饮食"],
                      "咨询": ["咨询","顾问","服务","管理"],
                      "建筑": ["建筑","工程","装修","装饰","建设"],
                      "教育": ["教育","培训","学校","文化"],
                      "医疗": ["医疗","医院","诊所","健康","医药"],
                      "金融": ["金融","投资","理财","基金","资产"],
                      "物流": ["物流","快递","运输","配送","货运"],
                      "电商": ["电商","网店","直播","在线"]}
    industry_kw = ""
    for ind, terms in industries_map.items():
        for t in terms:
            if t in msg:
                industry_kw = ind
                break
        if industry_kw:
            break

    loc_str = (loc + ("市" if loc and len(loc) <= 3 and not loc.endswith("市") else "")) if loc else "北京"
    ind_term = industries_map.get(industry_kw, ["科技"])[0]
    ct = "有限公司"

    auspicious = ["鑫","瑞","盛","达","通","泰","丰","源","恒","昌","诚","信","德","仁","和","智","创","卓","启","腾","博","嘉","锦","辉","华","宏","远","安","顺","康"]
    brands_2 = ["创新","卓越","领航","远航","腾飞","锦绣","瑞丰","鑫源","盛世","宏图","博远","诚信","嘉和","锦程","辉达","华盛","安泰","康盛","龙腾","骏达","鸿运"]

    names = []
    seen = set()
    # 已注销回收
    try:
        from app.models.audit_log import AuditLog
        recs = db.query(AuditLog).filter(AuditLog.target_type == "company_deregistration").order_by(AuditLog.created_at.desc()).limit(30).all()
        for rec in recs:
            if len(names) >= 3: break
            try: detail = json.loads(rec.detail) if rec.detail else {}
            except Exception: continue
            cn = detail.get("company_name", "")
            if not cn: continue
            for cts in ["有限公司","有限责任公司","股份有限公司","集团有限公司","实业有限公司"]:
                if cts in cn: cn = cn.replace(cts, ""); break
            for ll in sorted(locations_list, key=len, reverse=True):
                if cn.startswith(ll): cn = cn[len(ll):]; break
            for terms in industries_map.values():
                for t in sorted(terms, key=len, reverse=True):
                    if cn.endswith(t): cn = cn[:-len(t)]; break
            brand = cn.strip()
            if not brand or len(brand) < 2 or brand in seen: continue
            seen.add(brand)
            names.append({"full": f"{loc_str}{brand}{ind_term}{ct}", "brand": brand, "source": "deregistered", "score": 88})
    except Exception: pass

    # AI生成
    pool = set()
    for bp in random.sample(brands_2, min(10, len(brands_2))): pool.add(bp[:2])
    for _ in range(12):
        pool.add(random.choice(auspicious) + random.choice(auspicious))
    for _ in range(5):
        pool.add(random.choice(auspicious) + random.choice(["创","盛","达","源","通","泰"]))
    if industry_kw and len(industry_kw) >= 2:
        for ch in random.sample(auspicious, min(3, len(auspicious))): pool.add(industry_kw[:2] + ch)

    for brand in pool:
        if len(names) >= 8: break
        if brand in seen: continue
        seen.add(brand)
        score = 70 + sum(4 for ch in brand if ch in auspicious)
        names.append({"full": f"{loc_str}{brand}{ind_term}{ct}", "brand": brand, "source": "ai_generated", "score": min(score, 92)})

    names.sort(key=lambda n: n["score"], reverse=True)

    lines = [f"为您推荐以下公司名称（{loc_str} · {ind_term}行业）：\n"]
    for idx, n in enumerate(names[:8], 1):
        badge = "♻ 已注销回收" if n["source"] == "deregistered" else "✨ AI推荐"
        lines.append(f"{idx}. **{n['full']}**  [{badge}]  推荐度: {n['score']}分")
    lines.append("")
    lines.append("💡 选定名称后可在 **工商中心 → 公司注册** 直接使用。如需换个城市或行业，请告诉我。")
    return "\n".join(lines)


def _business_agent_reply(msg: str, db) -> str:
    """工商智能体总路由"""
    intent = _detect_business_intent(msg)

    if intent == "naming":
        return _naming_response(msg, db)

    if intent == "registration":
        return """**公司注册流程（以有限责任公司为例）：**

**第一步：核名**
- 登录当地市场监督管理局网站 → 企业名称自主申报
- 准备3-5个备选名称（字号+行业+组织形式）
- 名称通过后可保留6个月
- 官方网址：https://zwfw.samr.gov.cn/

**第二步：提交材料**
- 公司登记（备案）申请书
- 公司章程（全体股东签署）
- 股东主体资格证明（自然人身份证、法人营业执照）
- 法定代表人、董事、监事、经理任职文件
- 住所使用证明（房产证复印件 + 租赁合同）
- 法律、行政法规规定须报批的，提交批准文件

**第三步：领取执照（3-5个工作日）**
- 审核通过后领取营业执照正副本
- 同步获得统一社会信用代码

**第四步：刻章（1天）**
- 公章、财务章、法人章、发票章、合同章
- 需到公安局指定刻章点

**第五步：银行开户（3-7天）**
- 基本存款账户（必开）
- 需法人本人到场

**第六步：税务登记（30日内）**
- 电子税务局完成税务登记
- 核定税种、票种
- 签三方协议（银行-税务-企业）
- 领取 UKEY/数电票开票权限

📌 现在很多城市推行"一网通办"，全程电子化，最快1天拿执照。"""

    if intent == "deregistration":
        return """**公司注销流程：**

**简易注销（符合条件的企业）：**
- 条件：未开业或无债权债务、未发生债权债务或已清偿完结
- 流程：公示系统公告20天 → 公告期满20日内申请注销
- 无需清算组备案、无需清算报告
- 适合：未经营的壳公司、已清算完毕的小微企业

**一般注销：**
1. **股东会决议解散** — 股东会作出解散决议
2. **成立清算组** — 决议作出之日起15日内成立
3. **清算组备案** — 10日内到登记机关备案
4. **债权人公告** — 清算组应当自成立之日起10日内通知债权人，60日内在报纸或公示系统公告（公告期45天）
5. **清算** — 编制资产负债表、财产清单，处理未了结业务，清缴税款，清理债权债务
6. **税务注销** — 向税务机关申请清税，取得《清税证明》
7. **工商注销** — 公告期满后，向登记机关申请注销

**重点提醒：**
- 税务注销前必须先完成所有的纳税申报
- 社保、公积金账户必须先注销
- 银行账户建议最后注销
- 吊销 ≠ 注销！吊销是行政处罚，仍需办理注销手续

📌 官方网址：https://www.gsxt.gov.cn/"""

    if intent == "equity":
        return """**股权变更（股权转让）流程：**

**第一步：签署股权转让协议**
- 转让方与受让方签署
- 明确转让比例、价格、付款方式、交割时间

**第二步：股东会决议**
- 其他股东过半数同意（有限责任公司）
- 其他股东放弃优先购买权声明
- 修改公司章程

**第三步：税务申报**
- 转让方申报个人所得税（财产转让所得，税率20%）
- 计税基础 = 转让收入 - 原值 - 合理费用
- 平价/低价转让需有正当理由，否则税务机关可核定
- 在变更登记前完成纳税申报

**第四步：工商变更登记**
- 向登记机关申请股东变更
- 提交：变更登记申请书 + 股权转让协议 + 股东会决议 + 章程修正案 + 完税证明
- 新营业执照换发

**增资/减资：**
- 增资：股东会决议 → 出资 → 验资（非必需）→ 工商变更
- 减资：股东会决议 → 编制资产负债表 → 通知债权人 → 报纸公告45天 → 工商变更

📌 官方网址：https://zwfw.samr.gov.cn/"""

    if intent == "annual_report":
        return """**工商年报（企业年度报告公示）：**

**填报时间：**
- 每年1月1日 至 6月30日
- 报送上一年度报告

**填报内容：**
1. 企业基本信息（名称、住所、联系电话等）
2. 股东出资情况（认缴/实缴金额、出资时间）
3. 资产状况信息（资产总额、负债、营业收入、利润、纳税总额）
4. 对外投资信息
5. 社保信息（参保人数、缴费基数）
6. 行政许可、知识产权出质等

**填报方式：**
- 国家企业信用信息公示系统：https://www.gsxt.gov.cn/
- 各地市场监管局网站

**逾期后果：**
- 列入经营异常名录
- 满3年未移出 → 列入严重违法失信名单
- 政府采购、工程招投标、银行贷款受限
- 可处1万元以下罚款

💡 本系统支持工商年报填报，请切换到 **工商年报** 标签页操作。"""

    if intent == "lookup":
        return """**企业工商信息查询：**

本系统支持免费查询企业工商信息（替代企查查/天眼查），数据来源于国家企业信用信息公示系统。

**查询方式：**
- 输入企业名称 或 统一社会信用代码（18位）
- 系统自动获取：企业名称、法定代表人、注册资本、成立日期、经营状态、经营范围、股东信息等

**请切换到「企业查询」标签页进行操作。**

**官方查询渠道：**
- 国家企业信用信息公示系统：https://www.gsxt.gov.cn/
- 各地区市场监管局网站
- 国家企业信用信息公示系统 APP / 小程序"""

    # general / 默认
    return """您好！我是**工商智能体**，专注于工商业务领域。我可以帮您：

🏢 **公司起名** — 试试说「帮我在深圳起一个科技公司名」
📋 **公司注册** — 问「注册公司需要什么材料」「注册流程是什么」
🚫 **公司注销** — 问「如何注销公司」「简易注销条件」
🔄 **股权变更** — 问「股权转让怎么办理」「增资减资流程」
📊 **工商年报** — 问「年报什么时候填报」「逾期怎么办」
🔍 **企业查询** — 问「查询XX公司」「查一下企业信息」

请描述您的工商业务需求，我会尽力解答！"""


@router.post("/agent")
def business_agent_chat(
    body: BusinessAgentRequest,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """工商智能体对话"""
    reply = _business_agent_reply(body.message, db)
    return {"reply": reply, "source": "business_agent"}


# ============================================================
# 工商自动化 — Playwright 驱动 + 自学习
# ============================================================

class AutoAnnualReportRequest(BaseModel):
    company_name: str
    year: str = ""               # 年报年份，默认去年
    revenue: float = 0
    profit: float = 0
    assets: float = 0
    tax_total: float = 0
    employees: int = 0
    liabilities: float = 0
    equity: float = 0


class AutoLookupRequest(BaseModel):
    keyword: str                 # 企业名称或信用代码


class GenerateFormRequest(BaseModel):
    task_type: str               # registration / deregistration / equity
    data: dict = {}              # 客户数据


@router.post("/auto/annual-report")
def auto_annual_report(
    body: AutoAnnualReportRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """自动填报工商年报 — Playwright 自动填表，最后一步需人工确认提交"""
    from app.services.business_automation import run_auto_sync, run_annual_report_auto, get_learning_stats

    report_data = {
        "year": body.year or str(datetime.now().year - 1),
        "revenue": body.revenue, "profit": body.profit,
        "assets": body.assets, "tax_total": body.tax_total,
        "employees": body.employees, "liabilities": body.liabilities,
        "equity": body.equity,
    }

    result = run_auto_sync(run_annual_report_auto(body.company_name, report_data))

    # 审计日志
    log_action(db, target_type="annual_report", target_id=uuid.uuid4().hex,
               action="auto_fill", operator=current_user.display_name or current_user.username,
               detail={"company_name": body.company_name, "year": report_data["year"],
                       "success": result.success, "duration": result.duration_seconds})

    db.commit()

    return {
        "success": result.success,
        "message": result.message,
        "need_human_review": True,  # 最后一步必须人工审核
        "data": result.data,
        "screenshots": result.screenshots,
        "duration_seconds": result.duration_seconds,
        "learned": result.learned,
        "learning_stats": get_learning_stats(),
    }


@router.post("/auto/lookup")
def auto_company_lookup(
    body: AutoLookupRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """自动查询企业信息 — Playwright 爬取国家企业信用信息公示系统"""
    from app.services.business_automation import run_auto_sync, run_company_lookup, get_learning_stats

    result = run_auto_sync(run_company_lookup(body.keyword))

    log_action(db, target_type="company_lookup", target_id=uuid.uuid4().hex,
               action="auto_lookup", operator=current_user.display_name or current_user.username,
               detail={"keyword": body.keyword, "success": result.success,
                       "name": result.data.get("name", ""),
                       "duration": result.duration_seconds})

    db.commit()

    return {
        "success": result.success,
        "message": result.message,
        "data": result.data,
        "screenshots": result.screenshots,
        "duration_seconds": result.duration_seconds,
        "learned": result.learned,
        "learning_stats": get_learning_stats(),
    }


@router.post("/auto/generate-form")
def generate_official_form(
    body: GenerateFormRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """生成官方预填表单 — 根据客户数据自动填充官方表格模板"""
    from app.services.business_automation import BusinessAutomation

    engine = BusinessAutomation(headless=True)
    form = engine.generate_filled_forms(body.task_type, body.data)

    log_action(db, target_type=body.task_type, target_id=uuid.uuid4().hex,
               action="generate_form", operator=current_user.display_name or current_user.username,
               detail={"task_type": body.task_type, "fields_count": len(form.get("fields", {}))})

    db.commit()

    return {
        "form": form,
        "message": f"已生成 {form.get('form_name', '')} — 请核对后提交",
        "need_human_review": True,
    }


@router.get("/auto/learning-stats")
def get_automation_learning_stats(_=Depends(get_current_user)):
    """获取自动化自学习统计"""
    from app.services.business_automation import get_learning_stats
    return get_learning_stats()


# ============================================================
# 自动化工作流节点管理 — 支持人工返回任意节点修改
# ============================================================

class CreateWorkflowRequest(BaseModel):
    task_type: str                # annual_report / registration / deregistration / equity
    inputs: dict = {}             # 初始输入数据
    operator: str = ""            # 操作人


class UpdateNodeRequest(BaseModel):
    inputs: dict                  # 修改后的节点输入参数


class AdvanceNodeRequest(BaseModel):
    outputs: dict = {}            # 节点输出结果
    screenshots: list[str] = []
    success: bool = True
    error: str = ""


@router.post("/workflow/create")
def create_workflow_instance(
    body: CreateWorkflowRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """创建自动化工作流实例 — 将任务拆分为可编辑节点"""
    from app.services.workflow_engine import create_workflow

    instance_id = create_workflow(
        task_type=body.task_type,
        initial_inputs=body.inputs,
        operator=body.operator or current_user.display_name or current_user.username,
    )

    log_action(db, target_type="workflow", target_id=instance_id,
               action="created", operator=current_user.display_name or current_user.username,
               detail={"task_type": body.task_type})

    db.commit()

    from app.services.workflow_engine import get_workflow
    return {"instance_id": instance_id, "workflow": get_workflow(instance_id)}


@router.get("/workflow/{instance_id}")
def get_workflow_instance(instance_id: str, _=Depends(get_current_user)):
    """获取工作流实例详情（含所有节点状态）"""
    from app.services.workflow_engine import get_workflow
    wf = get_workflow(instance_id)
    if not wf:
        raise HTTPException(status_code=404, detail="工作流实例不存在")
    return wf


@router.patch("/workflow/{instance_id}/node/{node_id}")
def update_workflow_node(
    instance_id: str,
    node_id: str,
    body: UpdateNodeRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """
    修改指定节点的输入参数，并重置该节点及之后所有节点为 PENDING
    → 用户可回到任意节点修改数据后重新执行
    """
    from app.services.workflow_engine import update_node

    result = update_node(instance_id, node_id, body.inputs)

    log_action(db, target_type="workflow", target_id=instance_id,
               action="node_modified", operator=current_user.display_name or current_user.username,
               detail={"node_id": node_id, "new_inputs": body.inputs})

    db.commit()
    return {"message": f"节点「{node_id}」已重置，可重新执行", "workflow": result}


@router.post("/workflow/{instance_id}/node/{node_id}/advance")
def advance_workflow_node(
    instance_id: str,
    node_id: str,
    body: AdvanceNodeRequest = AdvanceNodeRequest(),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """推进工作流节点 — 标记当前节点完成，自动进入下一节点"""
    from app.services.workflow_engine import advance_node

    result = advance_node(
        instance_id, node_id,
        outputs=body.outputs,
        screenshots=body.screenshots,
        success=body.success,
        error=body.error,
    )

    log_action(db, target_type="workflow", target_id=instance_id,
               action="node_advanced", operator=current_user.display_name or current_user.username,
               detail={"node_id": node_id, "success": body.success})

    db.commit()
    return {"message": f"节点「{node_id}」已完成", "workflow": result}


@router.post("/workflow/{instance_id}/submit")
def submit_workflow_instance(
    instance_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """最终提交工作流 — 所有节点已完成，人工最后确认"""
    from app.services.workflow_engine import submit_workflow

    result = submit_workflow(instance_id)

    log_action(db, target_type="workflow", target_id=instance_id,
               action="submitted", operator=current_user.display_name or current_user.username,
               detail=result.get("final_result", {}))

    db.commit()
    return {"message": "工作流已提交", "workflow": result}


@router.get("/workflows")
def list_workflow_instances(
    task_type: str = Query(None),
    _=Depends(get_current_user),
):
    """列出工作流实例"""
    from app.services.workflow_engine import list_workflows
    return {"items": list_workflows(task_type)}


@router.get("/workflow/templates/{task_type}")
def get_workflow_template(task_type: str, _=Depends(get_current_user)):
    """获取工作流模板（节点定义）"""
    from app.services.workflow_engine import WORKFLOW_TEMPLATES
    template = WORKFLOW_TEMPLATES.get(task_type)
    if not template:
        raise HTTPException(status_code=404, detail=f"未知工作流类型: {task_type}")
    return {"task_type": task_type, "nodes": template}
