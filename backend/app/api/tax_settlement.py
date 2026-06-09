"""汇算清缴 API — 企业所得税年度汇算清缴"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date as dt_date, timedelta
from app.db import get_db

router = APIRouter()


@router.get("/settlement-preview")
def settlement_preview(
    client_id: str = Query(...),
    year: int = Query(None),
    db: Session = Depends(get_db),
):
    """
    汇算清缴预览 — 对比全年利润与已预缴所得税，计算应补/应退税额
    """
    from app.models.voucher import AccountingVoucher
    from app.models.filing import TaxFiling
    from app.services.report_service import dashboard_data
    import json as _json

    if not year:
        year = dt_date.today().year - 1  # 默认上年度

    dash = dashboard_data(db, client_id)

    # 汇总全年收入/成本/利润
    annual_revenue = 0.0
    annual_cost = 0.0
    annual_profit = 0.0

    entries_all = []
    for month in range(1, 13):
        period = f"{year}-{month:02d}"
        vouchers = db.query(AccountingVoucher).filter(
            AccountingVoucher.client_id == client_id,
            AccountingVoucher.voucher_date.like(f"{period}%"),
            AccountingVoucher.status == "confirmed",
        ).all()

        for v in vouchers:
            try:
                entries = _json.loads(v.entries) if v.entries else []
            except Exception:
                entries = []
            for e in entries:
                entries_all.append(e)

    # 按科目汇总
    revenue_accounts = {"6001", "6051", "6101"}
    cost_accounts = {"6401", "6402", "6403", "6405"}
    expense_accounts = {"6601", "6602", "6603", "6604", "6605", "6606", "6607", "6608", "6609", "6610"}

    for e in entries_all:
        code = str(e.get("account_code", "") or "")
        credit = float(e.get("credit", 0) or 0)
        debit = float(e.get("debit", 0) or 0)

        if code in revenue_accounts:
            annual_revenue += credit - debit
        elif code in cost_accounts:
            annual_cost += debit - credit
        elif code in expense_accounts:
            annual_profit -= (debit - credit)  # expense debits reduce profit

    annual_profit = annual_revenue - annual_cost + annual_profit

    # 季度预缴汇总
    quarterly_prepaid = 0.0
    quarterly_filings = db.query(TaxFiling).filter(
        TaxFiling.client_id == client_id,
        TaxFiling.tax_type == "corporate_income",
        TaxFiling.period.like(f"{year}%"),
        TaxFiling.status.in_(["submitted", "success"]),
    ).all()

    for f in quarterly_filings:
        try:
            result = _json.loads(f.filing_result) if f.filing_result else {}
        except Exception:
            result = {}
        quarterly_prepaid += float(result.get("tax_payable", 0) or 0)

    # 默认税率：小微企业 20%*0.5=10%（年应纳税所得额≤100万部分）
    small_profit_rate = 0.025  # 小微企业实际税负 2.5%（年利润≤100万）
    general_rate = 0.25

    taxable_income = max(0, annual_profit)  # 简化：不包含纳税调整

    if taxable_income <= 1_000_000:
        annual_tax = taxable_income * small_profit_rate
        rate_desc = "小型微利企业优惠税率 2.5%"
        is_small = True
    elif taxable_income <= 3_000_000:
        annual_tax = 1_000_000 * small_profit_rate + (taxable_income - 1_000_000) * 0.05
        rate_desc = "小型微利企业分段优惠税率（≤100万: 2.5%, 100-300万: 5%）"
        is_small = True
    else:
        annual_tax = taxable_income * general_rate
        rate_desc = "一般企业所得税税率 25%"
        is_small = False

    # 应补/应退
    balance = round(annual_tax - quarterly_prepaid, 2)
    if balance > 0:
        settlement_status = "应补税"
        balance_label = f"应补缴 {balance:,.2f} 元"
    elif balance < 0:
        settlement_status = "应退税"
        balance_label = f"应退 {abs(balance):,.2f} 元"
    else:
        settlement_status = "已结清"
        balance_label = "预缴与应缴一致，无需补退"

    # 常见纳税调整项（简化）
    adjustments = [
        {"item": "业务招待费（按发生额60%扣除，不超过营收5‰）", "amount": 0, "direction": "increase"},
        {"item": "广告费与业务宣传费（超营收15%部分结转）", "amount": 0, "direction": "increase"},
        {"item": "公益性捐赠（超利润12%部分结转）", "amount": 0, "direction": "increase"},
        {"item": "研发费用加计扣除（75%加计）", "amount": 0, "direction": "decrease"},
        {"item": "免税收入（国债利息、居民企业股息红利）", "amount": 0, "direction": "decrease"},
        {"item": "资产减值准备（未经核准的减值准备不得扣除）", "amount": 0, "direction": "increase"},
        {"item": "罚款/滞纳金（税收滞纳金、行政罚款不得扣除）", "amount": 0, "direction": "increase"},
    ]

    return {
        "year": year,
        "client_id": client_id,
        "annual_revenue": round(annual_revenue, 2),
        "annual_cost": round(annual_cost, 2),
        "annual_profit": round(annual_profit, 2),
        "taxable_income": round(taxable_income, 2),
        "tax_rate_description": rate_desc,
        "is_small_profit": is_small,
        "annual_cit_payable": round(annual_tax, 2),
        "quarterly_prepaid_total": round(quarterly_prepaid, 2),
        "balance": balance,
        "settlement_status": settlement_status,
        "balance_label": balance_label,
        "adjustments": adjustments,
        "filing_deadline": f"{year + 1}-05-31",
        "current_month": dash.get("current_month", {}) if dash else {},
        "recommendation": (
            "建议尽快完成年度汇算清缴，截止日期为次年5月31日" if balance >= 0
            else "存在多缴税款，可申请退税或抵减下年应纳税额"
        ),
    }
