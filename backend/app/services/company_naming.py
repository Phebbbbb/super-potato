"""
智能公司起名引擎 — 从已注销企业回收字号 + 算法组合生成
"""
import random
import re
from dataclasses import dataclass, field


# ===== 起名字库 =====

# 行政区划前缀
LOCATIONS = [
    "北京", "上海", "深圳", "广州", "杭州", "成都", "武汉", "南京", "重庆", "天津",
    "苏州", "西安", "长沙", "郑州", "青岛", "大连", "厦门", "宁波", "合肥", "福州",
    "无锡", "佛山", "东莞", "济南", "沈阳", "昆明", "贵阳", "南宁", "长春", "哈尔滨",
    "石家庄", "太原", "兰州", "南昌", "海口", "珠海", "惠州", "温州", "绍兴", "嘉兴",
]

# 吉祥/寓意字（字号常用）
AUSPICIOUS_CHARS = [
    "鑫", "瑞", "盛", "达", "通", "泰", "丰", "源", "恒", "昌",
    "诚", "信", "德", "仁", "和", "智", "创", "卓", "启", "腾",
    "博", "嘉", "锦", "辉", "华", "宏", "远", "安", "顺", "康",
    "翔", "龙", "鹏", "骏", "鸿", "辰", "泽", "润", "益", "凯",
    "荣", "晟", "鼎", "汇", "融", "聚", "升", "捷", "锐", "领",
]

# 行业关键词 → 常用字号词
INDUSTRY_TERMS = {
    "科技": ["科技", "信息", "数据", "智能", "数字", "互联", "云", "网", "软件", "技术"],
    "贸易": ["商贸", "贸易", "商", "工贸", "经贸", "实业", "物资", "供应链"],
    "咨询": ["咨询", "管理", "顾问", "服务", "企业服务", "商务"],
    "餐饮": ["餐饮", "食品", "饮食", "酒店", "餐饮管理"],
    "建筑": ["建筑", "工程", "建设", "装饰", "安装", "市政", "园林"],
    "教育": ["教育", "培训", "文化", "传媒", "艺术", "体育"],
    "医疗": ["医疗", "医药", "健康", "生物", "器械", "护理", "养老"],
    "金融": ["金融", "投资", "资产", "资本", "基金", "典当", "担保"],
    "物流": ["物流", "运输", "供应链", "快递", "配送", "货运"],
    "制造": ["制造", "机械", "电子", "设备", "精密", "自动化", "工业"],
    "电商": ["电商", "电子商务", "网络", "在线", "新零售"],
    "新能源": ["新能源", "能源", "电力", "光伏", "储能", "节能", "环保"],
    "文化": ["文化", "传媒", "广告", "设计", "创意", "娱乐", "影视"],
    "农业": ["农业", "生态", "农产品", "牧业", "渔业", "种植", "养殖"],
}

# 组织形式
COMPANY_TYPES = [
    "有限公司", "有限责任公司", "股份有限公司",
    "集团有限公司", "实业有限公司", "科技股份有限公司",
]

# 常用吉祥二字组合
BRAND_PATTERNS_2 = [
    "创新", "卓越", "领航", "远航", "启航", "腾飞", "鹏程", "锦绣",
    "瑞丰", "鑫源", "盛世", "宏图", "博远", "诚信", "嘉和", "锦程",
    "辉达", "华盛", "安泰", "康盛", "龙腾", "骏达", "鸿运", "泽润",
    "益丰", "凯旋", "荣昌", "晟达", "鼎盛", "汇通", "聚源", "升泰",
    "捷达", "锐志", "领创", "鑫达", "瑞华", "丰源", "恒盛", "昌隆",
    "通达", "泰和", "德润", "仁和", "智创", "卓然", "启明", "腾达",
    "博创", "嘉瑞", "锦源", "辉腾", "华瑞", "宏达", "远见", "安信",
]

# 常用吉祥三字组合
BRAND_PATTERNS_3 = [
    "鑫瑞丰", "盛达通", "泰和源", "恒昌瑞", "诚信达",
    "德仁和", "智创卓", "启腾飞", "博嘉锦", "辉华宏",
    "远安顺", "康盛达", "龙腾飞", "骏驰远", "鸿运达",
    "泽润丰", "益凯荣", "晟鼎汇", "融聚升", "捷锐领",
    "创智汇", "鑫源盛", "瑞华丰", "通达信", "安泰和",
]


@dataclass
class NameSuggestion:
    full_name: str           # 完整公司名：北京创新科技有限公司
    brand: str               # 字号：创新
    source: str              # "deregistered" | "ai_generated" | "pattern"
    score: int               # 0-100 推荐度
    available: bool          # 是否可用（粗略检查）
    meaning: str = ""        # 寓意说明


def _extract_brand(company_name: str) -> str:
    """从完整公司名中提取字号"""
    for ct in COMPANY_TYPES:
        if ct in company_name:
            name = company_name.replace(ct, "")
            break
    else:
        name = company_name
    # 去掉行政区划前缀
    for loc in sorted(LOCATIONS, key=len, reverse=True):
        if name.startswith(loc):
            name = name[len(loc):]
            break
    # 去掉行业后缀
    for terms in INDUSTRY_TERMS.values():
        for term in sorted(terms, key=len, reverse=True):
            if name.endswith(term):
                name = name[:-len(term)]
                break
    return name.strip()


def _detect_industry(business_scope: str, industry_keyword: str) -> str:
    """根据经营范围和关键词检测最匹配的行业类别"""
    scope = business_scope or ""
    keyword = industry_keyword or ""
    combined = scope + keyword

    scores = {}
    for industry, terms in INDUSTRY_TERMS.items():
        score = 0
        for term in terms:
            if term in combined:
                score += len(term)
        if keyword and industry in keyword:
            score += 10
        if score > 0:
            scores[industry] = score

    if scores:
        return max(scores, key=scores.get)
    return "科技"  # 默认


def _generate_brand_names(industry: str, keyword: str, count: int = 20) -> list[str]:
    """算法生成字号候选"""
    brands = set()
    terms = INDUSTRY_TERMS.get(industry, INDUSTRY_TERMS["科技"])

    # 1. 二吉祥字 + 行业相关字
    for bp in random.sample(BRAND_PATTERNS_2, min(15, len(BRAND_PATTERNS_2))):
        if len(brands) >= count:
            break
        brands.add(bp[:2])

    # 2. 三字组合
    for bp in random.sample(BRAND_PATTERNS_3, min(10, len(BRAND_PATTERNS_3))):
        if len(brands) >= count:
            break
        brands.add(bp)

    # 3. 吉祥字 + 行业字组合
    for aus in random.sample(AUSPICIOUS_CHARS, min(10, len(AUSPICIOUS_CHARS))):
        if len(brands) >= count:
            break
        brand = aus + random.choice(["创", "盛", "达", "源", "通", "泰", "丰", "信", "恒", "瑞"])
        brands.add(brand)

    # 4. 行业字 + 吉祥字
    for term in random.sample(terms, min(5, len(terms))):
        if len(brands) >= count:
            break
        short = term[:2] if len(term) >= 2 else term
        brand = short + random.choice(AUSPICIOUS_CHARS)
        brands.add(brand)

    # 5. 带用户关键词的组合
    if keyword and len(keyword) >= 2:
        kw_prefix = keyword[:2]
        for ch in random.sample(AUSPICIOUS_CHARS, min(5, len(AUSPICIOUS_CHARS))):
            if len(brands) >= count:
                break
            brands.add(kw_prefix + ch)
        for ch in random.sample(["创", "盛", "达", "源", "通", "泰", "丰", "信", "恒"] + AUSPICIOUS_CHARS[:5], min(5, 15)):
            if len(brands) >= count:
                break
            brands.add(ch + kw_prefix[:1] if kw_prefix else ch + "业")

    # 填充到目标数量
    while len(brands) < count:
        ch1 = random.choice(AUSPICIOUS_CHARS)
        ch2 = random.choice(AUSPICIOUS_CHARS)
        brands.add(ch1 + ch2)

    return list(brands)[:count]


def _meaning_for_brand(brand: str, industry: str) -> str:
    """生成字号的寓意说明"""
    meanings = {
        "鑫": "财富兴盛", "瑞": "吉祥如意", "盛": "繁荣昌盛", "达": "事业通达",
        "通": "畅通无阻", "泰": "国泰民安", "丰": "丰收富足", "源": "财源广进",
        "恒": "恒久长远", "昌": "繁荣昌盛", "诚": "诚信为本", "信": "信誉卓著",
        "德": "厚德载物", "仁": "仁者爱人", "和": "和谐共赢", "智": "智慧创新",
        "创": "创新进取", "卓": "卓越不凡", "启": "开启未来", "腾": "腾飞发展",
        "博": "博学广纳", "嘉": "嘉誉美名", "锦": "锦绣前程", "辉": "辉煌成就",
        "华": "华彩绽放", "宏": "宏图大展", "远": "远见卓识", "安": "稳健安全",
        "顺": "顺风顺水", "康": "健康发展", "翔": "翱翔天际", "龙": "龙腾四海",
        "鹏": "鹏程万里", "骏": "骏马奔腾", "鸿": "鸿运当头", "泽": "惠泽天下",
        "润": "滋润万物", "益": "增益价值", "凯": "凯旋而归", "领": "行业领先",
        "鼎": "鼎立天下", "汇": "汇聚英才", "融": "融通四海", "聚": "聚力前行",
        "升": "步步高升", "捷": "捷足先登", "锐": "锐意进取",
    }
    parts = []
    for ch in brand:
        if ch in meanings:
            parts.append(f"{ch}({meanings[ch]})")
    base = "、".join(parts) if parts else "寓意美好"
    return f"{base}，适合{industry}行业发展"


def suggest_names(
    location: str = "",
    industry_keyword: str = "",
    business_scope: str = "",
    db_session=None,
    count: int = 15,
) -> list[NameSuggestion]:
    """
    智能起名主入口
    - 从已注销企业回收字号
    - 算法生成新字号
    - 结合行政区划和行业生成完整名称
    """
    # 检测行业
    industry = _detect_industry(business_scope, industry_keyword)
    loc = location.strip() if location else ""

    suggestions: list[NameSuggestion] = []
    seen_brands: set[str] = set()

    # ===== 来源1: 已注销企业字号回收 =====
    if db_session:
        try:
            from app.models.audit_log import AuditLog
            import json

            dereg_records = (
                db_session.query(AuditLog)
                .filter(AuditLog.target_type == "company_deregistration")
                .order_by(AuditLog.created_at.desc())
                .limit(50)
                .all()
            )

            for rec in dereg_records:
                if len(suggestions) >= count // 3:
                    break
                try:
                    detail = json.loads(rec.detail) if rec.detail else {}
                except Exception:
                    continue
                company_name = detail.get("company_name", "")
                if not company_name:
                    continue
                brand = _extract_brand(company_name)
                if not brand or len(brand) < 2 or brand in seen_brands:
                    continue
                seen_brands.add(brand)

                # 构造新名称：用新地址 + 原字号 + 新行业
                location_str = loc + ("市" if loc and not loc.endswith("市") else "") if loc else "北京"
                industry_term = INDUSTRY_TERMS.get(industry, ["科技"])[0]
                full = f"{location_str}{brand}{industry_term}有限公司"

                suggestions.append(NameSuggestion(
                    full_name=full,
                    brand=brand,
                    source="deregistered",
                    score=85,
                    available=True,
                    meaning=f"回收字号「{brand}」，原企业已注销，字号可重新使用",
                ))
        except Exception:
            pass

    # ===== 来源2: 算法生成 =====
    brands = _generate_brand_names(industry, industry_keyword, count=count * 2)

    for brand in brands:
        if len(suggestions) >= count:
            break
        if brand in seen_brands:
            continue
        seen_brands.add(brand)

        location_str = loc if loc else random.choice(["北京", "上海", "深圳", "杭州", "成都"])
        # 智能补"市"
        if location_str and len(location_str) <= 3 and not location_str.endswith("市"):
            location_str += "市"

        industry_term = INDUSTRY_TERMS.get(industry, ["科技"])[0]

        # 生成多种组织形式变体
        ct = "有限公司"
        full = f"{location_str}{brand}{industry_term}{ct}"

        # 打分：行业匹配度 + 吉祥字密度 + 朗朗上口
        score = 70
        for ch in brand:
            if ch in AUSPICIOUS_CHARS:
                score += 5
        if industry_keyword and industry_keyword[:2] in brand:
            score += 10

        suggestions.append(NameSuggestion(
            full_name=full,
            brand=brand,
            source="ai_generated",
            score=min(score, 95),
            available=True,
            meaning=_meaning_for_brand(brand, industry),
        ))

    # 按分数排序
    suggestions.sort(key=lambda s: s.score, reverse=True)
    return suggestions[:count]
