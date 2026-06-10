"""内审工作台 API — 审计日志筛选 + CSV 导出 + 批量智能审账"""
import csv
import io
from datetime import date, datetime
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.voucher import AccountingVoucher
from app.models.filing import TaxFiling
from app.models.audit_log import AuditLog
from app.services.batch_audit_engine import run_batch_audit, AUDIT_RULES
from sqlalchemy import func

router = APIRouter()

# 操作日志中文映射
ACTION_LABELS = {
    "created": "创建", "updated": "修改", "deleted": "删除",
    "confirmed": "确认", "reverted": "回滚", "status_change": "状态变更",
    "approved": "通过", "rejected": "驳回", "corrected": "更正",
}
TARGET_LABELS = {
    "voucher": "凭证", "invoice": "发票", "filing": "申报",
    "document": "票据", "client": "客户", "employee": "员工",
    "payroll": "工资", "account": "科目", "system_config": "系统配置",
}


@router.get("/summary")
def audit_summary(client_id: str = Query(None), db: Session = Depends(get_db)):
    """内审工作台汇总"""
    q_v = db.query(AccountingVoucher)
    q_f = db.query(TaxFiling)
    q_a = db.query(AuditLog)

    if client_id:
        q_v = q_v.filter(AccountingVoucher.client_id == client_id)
        q_f = q_f.filter(TaxFiling.client_id == client_id)

    pending_vouchers = q_v.filter(AccountingVoucher.status.in_(["draft", "pending_review"])).count()
    pending_filings = q_f.filter(TaxFiling.status.in_(["pending", "pending_review"])).count()

    month_start = date.today().replace(day=1)
    audited_this_month = q_a.filter(
        AuditLog.action.in_(["confirmed", "approved", "rejected"]),
        func.date(AuditLog.created_at) >= month_start,
    ).count()

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


@router.get("/logs")
def list_audit_logs(
    action: str = Query(None),
    target_type: str = Query(None),
    date_from: str = Query(None),
    date_to: str = Query(None),
    operator: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """操作日志列表 — 支持多条件筛选"""
    q = db.query(AuditLog)

    if action:
        q = q.filter(AuditLog.action == action)
    if target_type:
        q = q.filter(AuditLog.target_type == target_type)
    if operator:
        q = q.filter(AuditLog.operator == operator)
    if date_from:
        q = q.filter(func.date(AuditLog.created_at) >= date_from)
    if date_to:
        q = q.filter(func.date(AuditLog.created_at) <= date_to)

    total = q.count()
    items = (
        q.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

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
            for l in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/logs/export")
def export_audit_logs(
    action: str = Query(None),
    target_type: str = Query(None),
    date_from: str = Query(None),
    date_to: str = Query(None),
    operator: str = Query(None),
    db: Session = Depends(get_db),
):
    """导出操作日志为 CSV 文件"""
    q = db.query(AuditLog)

    if action:
        q = q.filter(AuditLog.action == action)
    if target_type:
        q = q.filter(AuditLog.target_type == target_type)
    if operator:
        q = q.filter(AuditLog.operator == operator)
    if date_from:
        q = q.filter(func.date(AuditLog.created_at) >= date_from)
    if date_to:
        q = q.filter(func.date(AuditLog.created_at) <= date_to)

    logs = q.order_by(AuditLog.created_at.desc()).limit(10000).all()

    output = io.StringIO()
    output.write("﻿")  # BOM
    writer = csv.writer(output)
    writer.writerow(["时间", "操作人", "操作", "对象类型", "对象ID", "详情"])

    for l in logs:
        created = l.created_at.strftime("%Y-%m-%d %H:%M:%S") if l.created_at else ""
        writer.writerow([
            created,
            l.operator,
            ACTION_LABELS.get(l.action, l.action),
            TARGET_LABELS.get(l.target_type, l.target_type),
            l.target_id,
            l.detail or "",
        ])

    output.seek(0)
    filename = f"audit_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


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


@router.get("/rules")
def list_audit_rules():
    """列出所有可用审计规则"""
    return {
        "rules": [
            {"key": k, "name": v["name"], "category": v["category"],
             "severity": v["severity"], "description": v["description"],
             "weight": v["weight"]}
            for k, v in AUDIT_RULES.items()
        ]
    }


@router.post("/batch-audit")
def batch_audit(
    data: dict,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    批量智能审账 — 对全部/指定客户执行多维度审计规则

    body: {
        "client_ids": ["id1", ...] | null,  // null=全部
        "period": "2025-06",                // 可选，默认当前月
        "rules": ["balance", ...] | null,   // null=全部规则
        "thresholds": {"large_amount": 50000}  // 可选阈值覆盖
    }
    """
    return run_batch_audit(
        db,
        client_ids=data.get("client_ids"),
        period=data.get("period"),
        rules=data.get("rules"),
        threshold_overrides=data.get("thresholds"),
    )
