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
    """税务风险检测"""
    risks = []
    today = date.today()
    current_month = f"{today.year}-{today.month:02d}"

    # 1. 检查本月确认的凭证数
    start = f"{current_month}-01"
    if today.month == 12:
        end = f"{today.year+1}-01-01"
    else:
        end = f"{today.year}-{today.month+1:02d}-01"

    q = db.query(AccountingVoucher).filter(AccountingVoucher.status == "confirmed")
    if client_id:
        # 暂不按 client 过滤（等 client_id 加到 voucher 表后启用）
        pass
    monthly_vouchers = q.filter(AccountingVoucher.voucher_date >= start, AccountingVoucher.voucher_date < end).count()

    if monthly_vouchers == 0:
        risks.append({"level": "B", "type": "zero_voucher", "message": f"{current_month} 本月暂无已确认凭证，可能漏记账", "suggestion": "请检查本月票据是否已全部录入"})

    # 2. 检查即将到期的申报
    deadline = DEADLINES_2026.get(current_month, f"{current_month}-15")
    deadline_date = date.fromisoformat(deadline)
    days_left = (deadline_date - today).days
    if 0 <= days_left <= 5:
        risks.append({"level": "A", "type": "deadline_close", "message": f"{current_month} 申报截止日为 {deadline}，仅剩 {days_left} 天", "suggestion": "请尽快完成申报并提交"})
    elif days_left < 0:
        risks.append({"level": "A", "type": "deadline_passed", "message": f"{current_month} 申报截止日 {deadline} 已过", "suggestion": "请立即补申报，避免罚款和信用降级"})

    # 3. 计算本月税负率（简化）
    if monthly_vouchers > 0:
        risks.append({"level": "C", "type": "info", "message": f"{current_month} 本月已确认 {monthly_vouchers} 张凭证", "suggestion": ""})

    return {"items": risks, "score": "A" if len([r for r in risks if r["level"] in ("A","B")]) == 0 else "B"}
