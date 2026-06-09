from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db import get_db
from app.services.report_service import dashboard_data, trial_balance, income_statement, balance_sheet, cash_flow_statement
from app.services.qr_service import create_trace
from app.services.cache import cache_get, cache_set

router = APIRouter()


@router.get("/automation-rate")
def automation_rate(db: Session = Depends(get_db)):
    """自动化率分析 — 衡量系统全自动处理比例（核心差异化指标）"""
    from app.models.document import OriginalDocument
    from app.models.voucher import AccountingVoucher
    from app.models.filing import TaxFiling
    from app.models.invoice import Invoice
    from app.models.client import Client

    total_clients = db.query(func.count(Client.id)).filter(Client.is_active == True).scalar() or 0

    # 票据自动化率: OCR done / total
    total_docs = db.query(func.count(OriginalDocument.id)).scalar() or 0
    docs_ocr_done = db.query(func.count(OriginalDocument.id)).filter(OriginalDocument.ocr_status == "done").scalar() or 0
    docs_auto_pct = round(docs_ocr_done / total_docs * 100, 1) if total_docs > 0 else 0

    # 凭证自动化率: AI创建(created_by='ai' or reviewer contains 'AI') / total
    total_vouchers = db.query(func.count(AccountingVoucher.id)).scalar() or 0
    ai_vouchers = db.query(func.count(AccountingVoucher.id)).filter(
        (AccountingVoucher.created_by == "ai") | (AccountingVoucher.reviewer.like("%AI%"))
    ).scalar() or 0
    vouchers_auto_pct = round(ai_vouchers / total_vouchers * 100, 1) if total_vouchers > 0 else 0

    # 申报自动化率: auto_submitted / total (non-pending)
    total_filings = db.query(func.count(TaxFiling.id)).scalar() or 0
    auto_filings = db.query(func.count(TaxFiling.id)).filter(
        TaxFiling.status.in_(["submitted", "success"])
    ).scalar() or 0
    filings_auto_pct = round(auto_filings / total_filings * 100, 1) if total_filings > 0 else 0

    # 开票自动化率: issued / total
    total_invoices = db.query(func.count(Invoice.id)).scalar() or 0
    issued_invoices = db.query(func.count(Invoice.id)).filter(Invoice.status == "issued").scalar() or 0
    invoices_auto_pct = round(issued_invoices / total_invoices * 100, 1) if total_invoices > 0 else 0

    # 全链路自动化率 (端到端零人工介入)
    full_auto_steps = 0
    full_auto_total = 0
    if total_docs > 0:
        full_auto_steps += docs_ocr_done
        full_auto_total += total_docs
    if total_vouchers > 0:
        full_auto_steps += ai_vouchers
        full_auto_total += total_vouchers
    if total_filings > 0:
        full_auto_steps += auto_filings
        full_auto_total += total_filings
    if total_invoices > 0:
        full_auto_steps += issued_invoices
        full_auto_total += total_invoices
    overall_auto_pct = round(full_auto_steps / full_auto_total * 100, 1) if full_auto_total > 0 else 0

    # 全自动客户数（所有环节零人工）
    fully_auto_clients = 0
    if total_clients > 0:
        # 检查每个客户是否有非AI操作
        clients_with_manual = set()
        manual_vouchers = db.query(AccountingVoucher.client_id).filter(
            AccountingVoucher.created_by != "ai",
            AccountingVoucher.reviewer.notlike("%AI%"),
            AccountingVoucher.client_id.isnot(None),
        ).distinct().all()
        for (cid,) in manual_vouchers:
            clients_with_manual.add(cid)

        all_client_ids = set()
        all_clients = db.query(Client.id).filter(Client.is_active == True).all()
        for (cid,) in all_clients:
            all_client_ids.add(cid)

        fully_auto_clients = len(all_client_ids - clients_with_manual)

    return {
        "overall_automation_pct": overall_auto_pct,
        "total_clients": total_clients,
        "fully_auto_clients": fully_auto_clients,
        "breakdown": {
            "documents": {"total": total_docs, "auto_processed": docs_ocr_done, "pct": docs_auto_pct},
            "vouchers": {"total": total_vouchers, "auto_created": ai_vouchers, "pct": vouchers_auto_pct},
            "filings": {"total": total_filings, "auto_submitted": auto_filings, "pct": filings_auto_pct},
            "invoices": {"total": total_invoices, "auto_issued": issued_invoices, "pct": invoices_auto_pct},
        },
    }


@router.get("/dashboard")
def dashboard(client_id: str = Query(None), db: Session = Depends(get_db)):
    """首页仪表盘数据 — 对标亿企赢 KPI 驾驶舱"""
    cache_key = f"reports:dashboard:{client_id or 'all'}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    result = dashboard_data(db, client_id)
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


@router.get("/cash-flow")
def get_cash_flow(period: str = Query(...), db: Session = Depends(get_db)):
    """现金流量表"""
    sections = cash_flow_statement(db, period)
    return {
        "period": period,
        "sections": sections,
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
    elif report_type == "cash-flow":
        data = cash_flow_statement(db, period)
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"不支持的报表类型: {report_type}")

    return {
        "report_type": report_type,
        "period": period,
        "data": data,
        "message": "数据已准备好，可在前端导出为 Excel",
    }
