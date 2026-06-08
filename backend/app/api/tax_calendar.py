"""税务日历与风控 API"""
from datetime import date, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.filing import TaxFiling
from app.models.voucher import AccountingVoucher
from app.services.auth import get_current_user
from app.services.cache import cache_get, cache_set

router = APIRouter()

# 2026年月度申报截止日（已考虑节假日顺延）
DEADLINES_2026 = {
    "2026-01": "2026-01-20", "2026-02": "2026-02-24", "2026-03": "2026-03-16",
    "2026-04": "2026-04-20", "2026-05": "2026-05-22", "2026-06": "2026-06-15",
    "2026-07": "2026-07-15", "2026-08": "2026-08-17", "2026-09": "2026-09-15",
    "2026-10": "2026-10-26", "2026-11": "2026-11-16", "2026-12": "2026-12-15",
}

TAX_TYPES = ["vat", "individual_income", "corporate_income", "stamp_duty"]


@router.get("/calendar")
def get_calendar(client_id: str = Query(None), months_ahead: int = Query(3),
                 db: Session = Depends(get_db), _=Depends(get_current_user)):
    """获取即将到来的申报日历"""
    cache_key = f"tax:calendar:{client_id}:{months_ahead}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    today = date.today()
    items = []
    for i in range(months_ahead):
        month_key = f"{today.year}-{today.month + i:02d}" if today.month + i <= 12 else f"{today.year + 1}-{(today.month + i - 12):02d}"
        deadline = DEADLINES_2026.get(month_key, f"{month_key}-15")

        for tax_type in TAX_TYPES:
            filing = db.query(TaxFiling).filter(
                TaxFiling.tax_type == tax_type,
                TaxFiling.period == month_key,
                TaxFiling.status == "success",
            ).first() if client_id else None

            deadline_date = date.fromisoformat(deadline)
            days_left = (deadline_date - today).days
            if days_left < 0:
                risk = "overdue"
            elif days_left <= 7:
                risk = "urgent"
            elif days_left <= 30:
                risk = "upcoming"
            else:
                risk = "future"

            items.append({
                "period": month_key, "tax_type": tax_type,
                "deadline": deadline, "days_left": days_left,
                "risk": risk,
                "completed": filing is not None,
            })

    result = {"items": items, "today": str(today)}
    cache_set(cache_key, result, ttl=60)
    return result


@router.get("/risk-check")
def risk_check(client_id: str = Query(None), db: Session = Depends(get_db), _=Depends(get_current_user)):
    """税务风险检测 — 多维度分析"""
    risks = []
    today = date.today()
    current_month = f"{today.year}-{today.month:02d}"

    start = f"{current_month}-01"
    if today.month == 12:
        end = f"{today.year+1}-01-01"
    else:
        end = f"{today.year}-{today.month+1:02d}-01"

    q = db.query(AccountingVoucher).filter(AccountingVoucher.status == "confirmed")
    monthly_vouchers = q.filter(AccountingVoucher.voucher_date >= start, AccountingVoucher.voucher_date < end).all()

    # === 1. 零凭证风险 ===
    if len(monthly_vouchers) == 0:
        risks.append({"level": "B", "type": "zero_voucher", "message": f"{current_month} 本月暂无已确认凭证，可能漏记账", "suggestion": "请检查本月票据是否已全部录入并确认"})

    # === 2. 申报截止日风险 ===
    deadline = DEADLINES_2026.get(current_month, f"{current_month}-15")
    deadline_date = date.fromisoformat(deadline)
    days_left = (deadline_date - today).days
    if 0 <= days_left <= 5:
        risks.append({"level": "A", "type": "deadline_close", "message": f"{current_month} 申报截止日为 {deadline}，仅剩 {days_left} 天", "suggestion": "请尽快完成申报并提交"})
    elif days_left < 0:
        risks.append({"level": "A", "type": "deadline_passed", "message": f"{current_month} 申报截止日 {deadline} 已过", "suggestion": "请立即补申报，避免罚款和信用降级"})

    # === 3. 税负率分析（从会计分录汇总） ===
    if len(monthly_vouchers) > 0:
        import json
        total_revenue = 0.0    # 收入（6001 贷方）
        total_cost = 0.0       # 成本（6401 借方）
        total_expense = 0.0    # 三费（6601/6602/6603 借方）
        input_tax = 0.0        # 进项税额（222101 借方）
        output_tax = 0.0       # 销项税额（222101 贷方）
        payroll_debit = 0.0    # 薪酬（2211 借方）
        total_assets_debit = 0.0  # 资产类借方（排除成本费用）

        for v in monthly_vouchers:
            entries = json.loads(v.entries) if isinstance(v.entries, str) else (v.entries or [])
            for e in entries:
                code = str(e.get("account_code", ""))
                debit = float(e.get("debit", 0) or 0)
                credit = float(e.get("credit", 0) or 0)

                if code.startswith("6001"):
                    total_revenue += credit
                elif code.startswith("6401"):
                    total_cost += debit
                elif code.startswith(("6601", "6602", "6603")):
                    total_expense += debit
                elif code == "222101":
                    input_tax += debit
                    output_tax += credit
                elif code.startswith("2211"):
                    payroll_debit += debit
                elif code.startswith(("1001", "1002")):
                    total_assets_debit += debit

        # 增值税税负率 = (销项-进项) / 收入
        if total_revenue > 0:
            vat_net = output_tax - input_tax
            vat_burden = round(vat_net / total_revenue * 100, 2) if total_revenue > 0 else 0
            # 小规模纳税人增值税税负约1%，一般纳税人各行业不同（1%-5%）
            if vat_burden > 10:
                risks.append({"level": "B", "type": "vat_burden_high", "message": f"增值税税负率 {vat_burden}%，偏高（参考值1%-5%）", "suggestion": "请确认进项发票是否已全部认证抵扣"})
            elif vat_burden < 0.5 and output_tax > 0:
                risks.append({"level": "C", "type": "vat_burden_low", "message": f"增值税税负率 {vat_burden}%，偏低", "suggestion": "低税负率可能触发税务机关关注，请确保申报数据准确"})

            # 毛利率 = (收入-成本) / 收入
            gross_margin = round((total_revenue - total_cost) / total_revenue * 100, 2)
            if gross_margin < 0:
                risks.append({"level": "A", "type": "negative_margin", "message": f"毛利率 {gross_margin}%，本月经亏损", "suggestion": "检查成本核算是否正确，是否存在收入少计或成本多计"})
            elif gross_margin < 5:
                risks.append({"level": "C", "type": "low_margin", "message": f"毛利率 {gross_margin}%，低于正常水平", "suggestion": "持续低毛利可能引起税务机关关注"})

        # 进销项比例异常
        if output_tax > 0 and input_tax > 0:
            ratio = round(input_tax / output_tax * 100, 2)
            if ratio > 95:
                risks.append({"level": "B", "type": "io_ratio_high", "message": f"进销项税额比 {ratio}%，接近100%，可能存在留抵异常", "suggestion": "请核实是否存在不应抵扣的进项税额"})
            elif ratio < 10:
                risks.append({"level": "C", "type": "io_ratio_low", "message": f"进销项税额比 {ratio}%，进项严重不足", "suggestion": "请确认是否有未取得的进项发票"})

        # 费用率 = 三费 / 收入
        if total_revenue > 0:
            expense_ratio = round(total_expense / total_revenue * 100, 2)
            if expense_ratio > 80:
                risks.append({"level": "B", "type": "high_expense_ratio", "message": f"期间费用率 {expense_ratio}%，费用占比过高", "suggestion": "核查管理费用和销售费用是否合理，是否存在虚列费用"})

        # 连续零申报检测（检查上月）
        prev_month = f"{today.year}-{today.month-1:02d}" if today.month > 1 else f"{today.year-1}-12"
        prev_start = f"{prev_month}-01"
        prev_vouchers = db.query(AccountingVoucher).filter(
            AccountingVoucher.status == "confirmed",
            AccountingVoucher.voucher_date >= prev_start,
            AccountingVoucher.voucher_date < start,
        ).count()
        if prev_vouchers == 0 and len(monthly_vouchers) == 0:
            risks.append({"level": "B", "type": "consecutive_zero", "message": f"连续两月（{prev_month}、{current_month}）无已确认凭证", "suggestion": "连续零申报可能触发税务稽查，请确认是否存在未处理的业务"})

        # 薪酬支出风险（有收入但工资为0）
        if total_revenue > 10000 and payroll_debit == 0:
            risks.append({"level": "C", "type": "no_payroll", "message": "本月有收入但薪酬支出为0，可能异常", "suggestion": "请确认工资是否已计提入账"})

        # 信息项
        risks.append({"level": "C", "type": "info", "message": f"{current_month} 本月已确认 {len(monthly_vouchers)} 张凭证，收入¥{total_revenue:,.0f}", "suggestion": ""})

    # 评分
    severe = len([r for r in risks if r["level"] == "A"])
    warning = len([r for r in risks if r["level"] == "B"])
    if severe > 0:
        score = "C"
    elif warning > 1:
        score = "B"
    else:
        score = "A"

    return {"items": risks, "score": score, "risk_summary": {"severe": severe, "warning": warning, "info": len([r for r in risks if r["level"] == "C"])}}
