"""内审工作台 API"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.voucher import AccountingVoucher
from app.models.filing import TaxFiling
from app.models.audit_log import AuditLog
from sqlalchemy import func

router = APIRouter()


@router.get("/summary")
def audit_summary(client_id: str = Query(None), db: Session = Depends(get_db)):
    """内审工作台汇总"""
    q_v = db.query(AccountingVoucher)
    q_f = db.query(TaxFiling)
    q_a = db.query(AuditLog)

    if client_id:
        q_v = q_v.filter(AccountingVoucher.client_id == client_id)
        q_f = q_f.filter(TaxFiling.client_id == client_id)

    # Pending items
    pending_vouchers = q_v.filter(AccountingVoucher.status.in_(["draft", "pending_review"])).count()
    pending_filings = q_f.filter(TaxFiling.status.in_(["pending", "pending_review"])).count()

    # Audited this month
    from datetime import date
    month_start = date.today().replace(day=1)
    audited_this_month = q_a.filter(
        AuditLog.action.in_(["confirmed", "approved", "rejected"]),
        func.date(AuditLog.created_at) >= month_start,
    ).count()

    # Issues found (rejected items)
    issues_found = q_a.filter(
        AuditLog.action.in_(["rejected", "corrected"]),
        func.date(AuditLog.created_at) >= month_start,
    ).count()

    return {
        "pending_vouchers": pending_vouchers,
        "pending_filings": pending_filings,
        "audited_this_month": audited_this_month,
        "issues_found": issues_found,
    }


@router.get("/pending-vouchers")
def pending_vouchers_list(client_id: str = Query(None), db: Session = Depends(get_db)):
    """待审核凭证列表"""
    q = db.query(AccountingVoucher).filter(
        AccountingVoucher.status.in_(["draft", "pending_review"])
    )
    if client_id:
        q = q.filter(AccountingVoucher.client_id == client_id)
    vouchers = q.order_by(AccountingVoucher.created_at.desc()).limit(100).all()
    return {
        "items": [
            {
                "id": v.id,
                "voucher_no": v.voucher_no,
                "voucher_date": str(v.voucher_date) if v.voucher_date else None,
                "summary": v.summary,
                "total_debit": v.total_debit,
                "total_credit": v.total_credit,
                "status": v.status,
                "created_by": v.created_by,
                "reviewer": v.reviewer,
            }
            for v in vouchers
        ]
    }


@router.get("/recent-audits")
def recent_audits(client_id: str = Query(None), limit: int = Query(50), db: Session = Depends(get_db)):
    """最近的内审记录"""
    q = db.query(AuditLog).filter(
        AuditLog.action.in_(["confirmed", "rejected", "approved", "corrected"])
    )
    logs = q.order_by(AuditLog.created_at.desc()).limit(limit).all()
    return {
        "items": [
            {
                "id": l.id,
                "target_type": l.target_type,
                "target_id": l.target_id,
                "action": l.action,
                "operator": l.operator,
                "detail": l.detail,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ]
    }
