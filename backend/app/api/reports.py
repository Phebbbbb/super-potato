from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.report_service import dashboard_data, trial_balance, income_statement, balance_sheet
from app.services.qr_service import create_trace
from app.services.cache import cache_get, cache_set

router = APIRouter()


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    """首页仪表盘数据"""
    cache_key = "reports:dashboard"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    result = dashboard_data(db)
    cache_set(cache_key, result, ttl=120)
    return result


@router.get("/general-ledger")
def general_ledger(
    start_date: str = Query(...),
    end_date: str = Query(...),
    account_code: str = None,
    db: Session = Depends(get_db),
):
    """总账 — 按日期列出所有分录"""
    from app.services.report_service import get_confirmed_entries
    entries = get_confirmed_entries(db, start_date, end_date)

    if account_code:
        entries = [e for e in entries if e["account_code"] == account_code]

    # 按凭证号 + 日期排序
    entries.sort(key=lambda e: (e["voucher_date"], e["voucher_no"]))

    return {
        "start_date": start_date,
        "end_date": end_date,
        "account_code": account_code,
        "total_entries": len(entries),
        "items": entries,
    }


@router.get("/trial-balance")
def get_trial_balance(period: str = Query(...), db: Session = Depends(get_db)):
    """科目余额表"""
    items = trial_balance(db, period)
    return {
        "period": period,
        "total_accounts": len(items),
        "items": items,
    }


@router.get("/income-statement")
def get_income_statement(period: str = Query(...), db: Session = Depends(get_db)):
    """利润表"""
    items = income_statement(db, period)
    return {
        "period": period,
        "items": items,
    }


@router.get("/balance-sheet")
def get_balance_sheet(period: str = Query(...), db: Session = Depends(get_db)):
    """资产负债表"""
    bs = balance_sheet(db, period)
    return {
        "period": period,
        **bs,
    }


@router.get("/export")
def export_report(report_type: str, period: str, db: Session = Depends(get_db)):
    """导出报表（返回 JSON 数据，前端可进一步处理为 Excel）"""
    if report_type == "trial-balance":
        data = trial_balance(db, period)
    elif report_type == "income-statement":
        data = income_statement(db, period)
    elif report_type == "balance-sheet":
        data = balance_sheet(db, period)
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"不支持的报表类型: {report_type}")

    return {
        "report_type": report_type,
        "period": period,
        "data": data,
        "message": "数据已准备好，可在前端导出为 Excel",
    }
