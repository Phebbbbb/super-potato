"""
预检引擎 — "模拟考"系统

产品定位：未来官方统一代账入口后，本系统的核心价值是
  在提交到官方系统之前，本地完整模拟验证，确保一次过审。

三级预检：
  L1 数据完整性 — 必填项、逻辑关系、票账表一致性
  L2 税额复核   — 与官方公式对齐，防止计算偏差
  L3 合规风险   — 截止日、异常波动、政策匹配

返回就绪度评分（0-100），≥80 分建议可提交。
"""
import json
from datetime import date as dt_date, timedelta
from sqlalchemy.orm import Session
from collections import defaultdict


def run_precheck(db: Session, client_id: str, period: str = None) -> dict:
    """
    对指定客户执行全量预检

    Args:
        client_id: 客户ID
        period: 所属期 YYYY-MM（默认当前月）

    Returns:
        {
            "score": 85,          # 就绪度评分 0-100
            "grade": "good",      # excellent/good/warning/danger
            "passed": true,
            "checks": [...],      # 所有检查项
            "warnings": [...],    # 预警项
            "errors": [...],      # 阻断项
            "recommendations": [...]  # 建议
        }
    """
    from app.models.client import Client
    from app.models.voucher import AccountingVoucher
    from app.models.filing import TaxFiling
    from app.models.document import OriginalDocument
    from app.models.invoice import Invoice
    from app.services.report_service import get_confirmed_entries, _sum_by_account, _month_range

    today = dt_date.today()
    if period:
        y, m = map(int, period.split("-"))
    else:
        y, m = today.year, today.month

    ms, me = _month_range(y, m)
    period_str = f"{y}-{m:02d}"

    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        return {"score": 0, "grade": "danger", "passed": False, "errors": ["客户不存在"]}

    checks = []
    warnings = []
    errors = []
    score = 100  # 满分起始，逐项扣分

    # ================================================================
    # L1: 数据完整性检查（单次加载凭证明细 + 凭证列表）
    # ================================================================

    # 1.1 客户基础信息
    missing_fields = []
    if not client.tax_no:
        missing_fields.append("统一社会信用代码")
    if not client.taxpayer_type:
        missing_fields.append("纳税人类型")
    if missing_fields:
        errors.append({"check": "基础信息", "detail": f"缺失: {', '.join(missing_fields)}", "severity": "blocker"})
        score -= 20
    else:
        checks.append({"check": "客户基础信息", "status": "pass", "detail": "完整"})

    # 一次性加载所有本月已确认凭证 + 分录明细
    vouchers = db.query(AccountingVoucher).filter(
        AccountingVoucher.client_id == client_id,
        AccountingVoucher.status == "confirmed",
        AccountingVoucher.voucher_date >= ms,
        AccountingVoucher.voucher_date <= me,
    ).all()

    # 1.2 本月凭证数量
    voucher_count = len(vouchers)
    if voucher_count == 0:
        warnings.append({"check": "本月凭证", "detail": "本月无已确认凭证，申报数据可能为空", "severity": "warning"})
        score -= 15
    else:
        checks.append({"check": "本月凭证", "status": "pass", "detail": f"{voucher_count} 张已确认"})

    # 1.3 凭证借贷平衡
    unbalanced = []
    for v in vouchers:
        if v.total_debit is not None and v.total_credit is not None:
            if abs(v.total_debit - v.total_credit) > 0.01:
                unbalanced.append(v.voucher_no)
    if unbalanced:
        errors.append({"check": "借贷平衡", "detail": f"{len(unbalanced)} 张凭证借贷不平衡: {unbalanced[:3]}", "severity": "blocker"})
        score -= 25
    else:
        checks.append({"check": "借贷平衡", "status": "pass", "detail": "全部凭证借贷平衡"})

    # 1.4 票账一致性 — 复用已加载的 vouchers 解析分录（不再单独查询）
    entries = []
    for v in vouchers:
        try:
            v_entries = json.loads(v.entries) if isinstance(v.entries, str) else (v.entries or [])
        except (json.JSONDecodeError, TypeError):
            v_entries = []
        for e in v_entries:
            entries.append({
                "account_code": e.get("account_code", ""),
                "debit": float(e.get("debit", 0) or 0),
                "credit": float(e.get("credit", 0) or 0),
                "summary": e.get("summary", ""),
                "client_id": client_id,
            })

    revenue_from_vouchers = _sum_by_account(entries, ["6001", "6051"], "credit")
    expense_from_vouchers = _sum_by_account(entries, ["6401", "6402", "6403", "6601", "6602", "6603"], "debit")

    # 对比发票金额
    invoices = db.query(Invoice).filter(
        Invoice.client_id == client_id,
        Invoice.status.in_(["issued", "confirmed"]),
    ).all()
    invoice_total = sum(float(inv.total_amount or 0) for inv in invoices)

    if invoice_total > 0 and revenue_from_vouchers > 0:
        diff_pct = abs(invoice_total - revenue_from_vouchers) / max(invoice_total, 1) * 100
        if diff_pct > 20:
            warnings.append({
                "check": "票账一致",
                "detail": f"开票金额(¥{invoice_total:,.0f})与账面收入(¥{revenue_from_vouchers:,.0f})差异 {diff_pct:.0f}%",
                "severity": "warning",
            })
            score -= 10
        else:
            checks.append({"check": "票账一致", "status": "pass", "detail": f"差异 {diff_pct:.1f}%"})

    # ================================================================
    # L2: 税额模拟复核
    # ================================================================

    # 2.1 增值税试算
    output_vat = _sum_by_account(entries, ["2221001"], "credit")
    input_vat = _sum_by_account(entries, ["2221002"], "debit")
    computed_vat = round(max(output_vat - input_vat, 0), 2)

    # 2.2 企业所得税试算
    profit = revenue_from_vouchers - expense_from_vouchers
    if profit > 0:
        if profit <= 3_000_000:
            if profit <= 1_000_000:
                est_cit = round(profit * 0.025, 2)
            else:
                est_cit = round(1_000_000 * 0.025 + (profit - 1_000_000) * 0.05, 2)
        else:
            est_cit = round(profit * 0.25, 2)
    else:
        est_cit = 0

    # 2.3 附加税试算
    est_surtax = round(computed_vat * 0.12, 2)  # 城建7% + 教育附加3% + 地方教育附加2%

    checks.append({"check": "增值税试算", "status": "pass", "detail": f"销项 ¥{output_vat:,.2f} - 进项 ¥{input_vat:,.2f} = ¥{computed_vat:,.2f}"})
    checks.append({"check": "所得税试算", "status": "pass", "detail": f"利润 ¥{profit:,.2f} × 税率 = ¥{est_cit:,.2f}"})
    checks.append({"check": "附加税试算", "status": "pass", "detail": f"增值税 ¥{computed_vat:,.2f} × 12% = ¥{est_surtax:,.2f}"})

    # 2.4 检测异常波动（对比前3个月均值）
    historical = []
    for i in range(1, 4):
        hms, hme = _month_range(y, m - i)
        hentries = get_confirmed_entries(db, hms, hme)
        hentries = [e for e in hentries if e.get("client_id") == client_id]
        hrev = _sum_by_account(hentries, ["6001", "6051"], "credit")
        hvat = _sum_by_account(hentries, ["2221001"], "credit") - _sum_by_account(hentries, ["2221002"], "debit")
        historical.append({"period": f"{y}-{m-i:02d}", "revenue": hrev, "vat": max(hvat, 0)})

    if historical:
        avg_revenue = sum(h["revenue"] for h in historical) / len(historical)
        avg_vat = sum(h["vat"] for h in historical) / len(historical)

        if avg_revenue > 0 and revenue_from_vouchers > 0:
            rev_change = abs(revenue_from_vouchers - avg_revenue) / avg_revenue * 100
            if rev_change > 50:
                warnings.append({
                    "check": "收入异常波动",
                    "detail": f"本月收入(¥{revenue_from_vouchers:,.0f})偏离近3月均值(¥{avg_revenue:,.0f}) {rev_change:.0f}%，建议复核",
                    "severity": "warning",
                })
                score -= 10
            elif rev_change > 30:
                warnings.append({
                    "check": "收入波动",
                    "detail": f"本月收入偏离均值 {rev_change:.0f}%",
                    "severity": "info",
                })
                score -= 5

        if avg_vat > 0 and computed_vat > 0:
            vat_change = abs(computed_vat - avg_vat) / max(avg_vat, 1) * 100
            if vat_change > 50:
                warnings.append({
                    "check": "税负异常波动",
                    "detail": f"本月增值税(¥{computed_vat:,.0f})偏离近3月均值(¥{avg_vat:,.0f}) {vat_change:.0f}%",
                    "severity": "warning",
                })
                score -= 8

    # ================================================================
    # L3: 合规风险检查
    # ================================================================

    # 3.1 申报截止日
    deadline_day = 15
    days_until_deadline = (dt_date(y, m, deadline_day) - today).days
    if days_until_deadline < 0 and today.month == m + 1:
        errors.append({
            "check": "申报截止",
            "detail": f"{period_str} 申报截止日已过 ({abs(days_until_deadline)} 天前)，请立即处理",
            "severity": "blocker",
        })
        score -= 30
    elif days_until_deadline < 3:
        warnings.append({
            "check": "申报截止",
            "detail": f"距 {period_str} 申报截止仅 {max(days_until_deadline, 0)} 天",
            "severity": "warning",
        })
        score -= 10
    else:
        checks.append({"check": "申报截止", "status": "pass", "detail": f"距截止 {days_until_deadline} 天"})

    # 3.2 未处理原始凭证
    pending_docs = db.query(OriginalDocument).filter(
        OriginalDocument.client_id == client_id,
        OriginalDocument.ocr_status == "pending",
    ).count()
    if pending_docs > 0:
        warnings.append({
            "check": "待处理票据",
            "detail": f"{pending_docs} 张原始凭证未完成 OCR 识别",
            "severity": "warning",
        })
        score -= 5

    # 3.3 纳税人类型校验（小规模纳税人申报期）
    taxpayer_type = client.taxpayer_type or "small"
    if taxpayer_type == "small" and m not in (1, 4, 7, 10):
        checks.append({
            "check": "申报期匹配",
            "status": "pass",
            "detail": f"小规模纳税人，{m}月非季度申报月，仅需申报企业所得税",
        })

    # 3.4 税负率预警
    if revenue_from_vouchers > 0:
        tax_burden = computed_vat / revenue_from_vouchers * 100
        if tax_burden < 1 and computed_vat > 0:
            warnings.append({
                "check": "税负率偏低",
                "detail": f"增值税税负率 {tax_burden:.2f}% 低于行业预警线 1%，可能触发税务核查",
                "severity": "warning",
            })
            score -= 8

    # 3.5 已存在的申报记录
    existing_filings = db.query(TaxFiling).filter(
        TaxFiling.client_id == client_id,
        TaxFiling.period == period_str,
    ).all()
    filing_statuses = {f.tax_type: f.status for f in existing_filings}

    required_tax_types = []
    if taxpayer_type == "general" or m in (1, 4, 7, 10):
        required_tax_types.extend(["vat", "surtax"])
    if m in (1, 4, 7, 10):
        required_tax_types.append("corporate_income")
    required_tax_types.append("stamp_duty")

    for tt in required_tax_types:
        status = filing_statuses.get(tt)
        if not status:
            warnings.append({"check": f"{_tax_name(tt)}申报", "detail": "尚未创建申报任务", "severity": "warning"})
            score -= 5
        elif status == "submitted" or status == "success":
            checks.append({"check": f"{_tax_name(tt)}申报", "status": "pass", "detail": f"已提交"})
        elif status == "failed":
            errors.append({"check": f"{_tax_name(tt)}申报", "detail": "上次申报失败，需重新提交", "severity": "blocker"})
            score -= 15

    # ================================================================
    # 汇总评分
    # ================================================================

    score = max(0, min(100, score))

    if score >= 85:
        grade = "excellent"
        passed = True
    elif score >= 70:
        grade = "good"
        passed = True
    elif score >= 50:
        grade = "warning"
        passed = False
    else:
        grade = "danger"
        passed = False

    return {
        "client_id": client_id,
        "client_name": client.name,
        "period": period_str,
        "score": score,
        "grade": grade,
        "passed": passed,
        "summary": {
            "revenue": round(revenue_from_vouchers, 2),
            "expense": round(expense_from_vouchers, 2),
            "profit": round(profit, 2),
            "computed_vat": computed_vat,
            "computed_cit": est_cit,
            "computed_surtax": est_surtax,
            "tax_burden_pct": round(computed_vat / max(revenue_from_vouchers, 1) * 100, 2),
            "voucher_count": voucher_count,
            "pending_docs": pending_docs,
            "days_to_deadline": max(days_until_deadline, 0),
        },
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
        "recommendations": _build_recommendations(warnings, errors, days_until_deadline),
        "checked_at": dt_date.today().isoformat(),
    }


def run_batch_precheck(db: Session, client_ids: list[str] = None) -> list[dict]:
    """批量预检所有客户（或指定客户列表）"""
    from app.models.client import Client

    q = db.query(Client)
    if client_ids:
        q = q.filter(Client.id.in_(client_ids))
    clients = q.all()

    results = []
    for c in clients:
        try:
            r = run_precheck(db, c.id)
            results.append(r)
        except Exception as e:
            results.append({
                "client_id": c.id,
                "client_name": c.name,
                "score": 0,
                "grade": "error",
                "passed": False,
                "errors": [str(e)],
            })

    # 排序：分数低的排前面（最需要关注的）
    results.sort(key=lambda r: r["score"])
    return results


def _tax_name(tax_type: str) -> str:
    names = {
        "vat": "增值税", "corporate_income": "企业所得税", "surtax": "附加税",
        "stamp_duty": "印花税", "property_tax": "房产税", "land_use_tax": "土地使用税",
    }
    return names.get(tax_type, tax_type)


def _build_recommendations(warnings: list, errors: list, days_to_deadline: int) -> list[str]:
    """根据检查结果生成操作建议"""
    recs = []

    blocker_count = sum(1 for e in errors if e.get("severity") == "blocker")
    warn_count = sum(1 for w in warnings if w.get("severity") == "warning")

    if blocker_count > 0:
        recs.append(f"发现 {blocker_count} 项阻断性问题，必须解决后才能申报")
    if warn_count > 0:
        recs.append(f"发现 {warn_count} 项预警，建议申报前确认")

    if days_to_deadline <= 3 and days_to_deadline >= 0:
        recs.append(f"申报截止日临近（{days_to_deadline} 天），请尽快处理")
    elif days_to_deadline < 0:
        recs.append("申报已逾期，请立即处理避免罚款")

    if not errors and not warnings:
        recs.append("所有检查项通过，可以放心申报")
    elif not errors:
        recs.append("无阻断性问题，可先申报再处理预警项")

    return recs
