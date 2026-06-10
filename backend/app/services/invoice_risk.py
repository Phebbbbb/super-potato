"""开票风险检测引擎 — 算法驱动多维度风险评估"""
import re
import json
from datetime import date, timedelta
from sqlalchemy.orm import Session
from app.models.invoice import Invoice


def _validate_uscc(tax_no: str) -> tuple[bool, str]:
    """校验统一社会信用代码（18位）"""
    if not tax_no or len(tax_no) != 18:
        return False, "长度不为18位"
    # 前2位: 登记管理机关代码 (数字/大写字母, 不含I/O/Z/S/V)
    if not re.match(r'^[0-9A-HJ-NPQRTUWXY]{2}', tax_no[:2]):
        return False, "前2位登记机关代码无效"
    # 第3-8位: 组织机构代码
    if not re.match(r'^\d{6}', tax_no[2:8]):
        return False, "组织机构代码无效"
    # 第9-17位: 组织机构代码
    if not re.match(r'^[0-9A-HJ-NPQRTUWXY]{9}', tax_no[8:17]):
        return False, "主体标识码无效"
    # 第18位: 校验码
    if not re.match(r'^[0-9A-HJ-NPQRTUWXY]$', tax_no[17]):
        return False, "校验码无效"

    # 加权因子校验
    weights = [1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23, 25, 27, 29, 31, 33]
    char_map = {str(i): i for i in range(10)}
    for i, c in enumerate("ABCDEFGHJKLMNPQRTUWXY"):
        char_map[c] = 10 + i

    try:
        total = sum(char_map[tax_no[i]] * weights[i] for i in range(17))
        check = 31 - (total % 31)
        if check == 31:
            check = 0
        check_char = {v: k for k, v in char_map.items()}.get(check, str(check))
        if check_char != tax_no[17]:
            return False, "校验码不匹配"
    except (KeyError, IndexError):
        return False, "含非法字符"

    return True, "有效"


def _detect_duplicates(db: Session, invoice_data: dict) -> list[dict]:
    """检测重复开票：相同购方+相近金额+相近时间"""
    buyer = invoice_data.get("buyer_tax_no", "")
    amount = float(invoice_data.get("grand_total", 0))
    if not buyer or amount <= 0:
        return []

    # 查最近90天相同购方的发票
    cutoff = date.today() - timedelta(days=90)
    existing = db.query(Invoice).filter(
        Invoice.buyer_tax_no == buyer,
        Invoice.created_at >= cutoff,
        Invoice.status != "deleted",
    ).all()

    duplicates = []
    for inv in existing:
        inv_amount = inv.grand_total or 0
        if inv_amount > 0 and abs(inv_amount - amount) / max(inv_amount, 1) < 0.02:
            duplicates.append({
                "invoice_id": inv.id,
                "buyer_name": inv.buyer_name,
                "amount": inv_amount,
                "created_at": inv.created_at.isoformat() if inv.created_at else "",
                "similarity": round(1 - abs(inv_amount - amount) / max(inv_amount, 1), 3),
            })
    return duplicates


def _check_amount_reasonableness(amount: float, items: list) -> list[str]:
    """检查金额合理性"""
    warnings = []
    if amount <= 0:
        warnings.append("发票金额为零或负数")
    elif amount > 1_000_000:
        warnings.append(f"发票金额 ¥{amount:,.2f} 超过100万元，建议人工复核")
    elif amount > 100_000:
        warnings.append(f"发票金额 ¥{amount:,.2f} 较大，请确认")

    # 检查明细合计是否匹配
    if items:
        items_total = sum(
            (float(it.get("amount", 0) or 0) + float(it.get("tax_amount", 0) or 0))
            for it in items
        )
        if items_total > 0 and abs(items_total - amount) / max(amount, 1) > 0.01:
            warnings.append(f"商品明细价税合计 ¥{items_total:,.2f} 与发票总额 ¥{amount:,.2f} 不匹配")

    return warnings


def _check_tax_rate(items: list) -> list[str]:
    """检查税率合理性"""
    warnings = []
    for it in items:
        rate = float(it.get("tax_rate", 0) or 0)
        name = it.get("name", "")
        if rate == 0 and name:
            warnings.append(f"商品「{name}」税率为0%，请确认是否为免税商品")
        elif rate > 0.13:
            warnings.append(f"商品「{name}」税率 {rate*100:.0f}% 异常偏高")
    return warnings


def _assess_frequency_risk(db: Session, client_id: str) -> dict:
    """评估开票频率异常"""
    today = date.today()
    month_start = today.replace(day=1)

    # 本月已开票数量
    month_count = db.query(Invoice).filter(
        Invoice.client_id == client_id,
        Invoice.created_at >= month_start,
        Invoice.status.in_(["issued", "issuing"]),
    ).count()

    # 最近7天已开票数量
    week_start = today - timedelta(days=7)
    week_count = db.query(Invoice).filter(
        Invoice.client_id == client_id,
        Invoice.created_at >= week_start,
        Invoice.status.in_(["issued", "issuing"]),
    ).count()

    risk = "low"
    if month_count > 50:
        risk = "high"
    elif month_count > 20 or week_count > 10:
        risk = "medium"

    return {
        "month_count": month_count,
        "week_count": week_count,
        "frequency_risk": risk,
    }


def comprehensive_risk_check(
    db: Session,
    invoice_data: dict,
    client_id: str,
) -> dict:
    """
    综合风险评估引擎
    返回: { score: 0-100, risk_level: low/medium/high/critical, checks: [...], recommendations: [...] }
    """
    checks = []
    score = 0  # 风险分数越高越危险
    buyer_tax_no = invoice_data.get("buyer_tax_no", "")
    amount = float(invoice_data.get("grand_total", 0))
    items = invoice_data.get("items", []) or []

    # 1. 购方税号校验 (权重: 25)
    valid_uscc, uscc_msg = _validate_uscc(buyer_tax_no)
    checks.append({
        "name": "购方税号校验",
        "passed": valid_uscc,
        "detail": uscc_msg,
        "weight": 25,
    })
    if not valid_uscc:
        score += 25

    # 2. 重复开票检测 (权重: 30)
    duplicates = _detect_duplicates(db, invoice_data)
    dup_passed = len(duplicates) == 0
    checks.append({
        "name": "重复开票检测",
        "passed": dup_passed,
        "detail": f"发现 {len(duplicates)} 张疑似重复发票" if not dup_passed else "未发现重复",
        "weight": 30,
        "duplicates": duplicates[:5],
    })
    if not dup_passed:
        score += 30
    elif len(duplicates) > 0:
        score += len(duplicates) * 5

    # 3. 金额合理性 (权重: 20)
    amount_warnings = _check_amount_reasonableness(amount, items)
    amt_passed = len(amount_warnings) == 0
    checks.append({
        "name": "金额合理性",
        "passed": amt_passed,
        "detail": "; ".join(amount_warnings) if not amt_passed else "金额合理",
        "weight": 20,
    })
    if not amt_passed:
        score += min(len(amount_warnings) * 10, 20)

    # 4. 税率合理性 (权重: 10)
    tax_warnings = _check_tax_rate(items)
    tax_passed = len(tax_warnings) == 0
    checks.append({
        "name": "税率合理性",
        "passed": tax_passed,
        "detail": "; ".join(tax_warnings) if not tax_passed else "税率正常",
        "weight": 10,
    })
    if not tax_passed:
        score += min(len(tax_warnings) * 5, 10)

    # 5. 频率风险评估 (权重: 15)
    freq = _assess_frequency_risk(db, client_id)
    freq_risk = freq["frequency_risk"]
    checks.append({
        "name": "开票频率",
        "passed": freq_risk == "low",
        "detail": f"本月{freq['month_count']}张，近7天{freq['week_count']}张 — 风险{freq_risk}",
        "weight": 15,
        "frequency": freq,
    })
    if freq_risk == "high":
        score += 15
    elif freq_risk == "medium":
        score += 8

    # 6. 购方信息完整性 (权重: 5)
    buyer_name = invoice_data.get("buyer_name", "").strip()
    buyer_addr = invoice_data.get("buyer_address", "").strip()
    buyer_bank = invoice_data.get("buyer_bank", "").strip()
    completeness = sum([bool(buyer_name), bool(buyer_addr), bool(buyer_bank)])
    complete_passed = completeness >= 2
    checks.append({
        "name": "购方信息完整性",
        "passed": complete_passed,
        "detail": f"已填 {completeness}/3 项必填信息" if not complete_passed else "信息完整",
        "weight": 5,
    })
    if not complete_passed:
        score += 3

    # 综合评级
    if score >= 60:
        risk_level = "critical"
    elif score >= 35:
        risk_level = "high"
    elif score >= 15:
        risk_level = "medium"
    else:
        risk_level = "low"

    recommendations = []
    if not valid_uscc:
        recommendations.append("请核实购方统一社会信用代码是否正确")
    if not dup_passed:
        recommendations.append(f"存在 {len(duplicates)} 张疑似重复发票，建议确认后再开票")
    if amount > 100_000:
        recommendations.append("大额发票建议人工复核后开票")
    if freq_risk != "low":
        recommendations.append(f"本月开票频率较高({freq['month_count']}张)，关注是否正常业务需求")

    return {
        "score": min(score, 100),
        "risk_level": risk_level,
        "checks": checks,
        "recommendations": recommendations,
        "pass": risk_level in ("low", "medium"),
        "require_review": risk_level in ("high", "critical"),
    }
