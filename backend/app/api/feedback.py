"""反馈与修正接口 — 每个环节均可人工介入修改"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.voucher import AccountingVoucher
from app.models.document import OriginalDocument
from app.models.filing import TaxFiling
from app.services.voucher_service import validate_balance
from app.services.audit_service import log_action, get_audit_trail
from app.services.qr_service import create_trace
from app.services.auth import get_current_user, require_modify

router = APIRouter()


# ========================
# 环节 1：原始凭证 OCR 修正
# ========================

@router.patch("/document/{doc_id}/ocr")
def correct_document_ocr(doc_id: str, data: dict, db: Session = Depends(get_db), _=Depends(require_modify)):
    """人工修正 OCR 识别结果"""
    doc = db.query(OriginalDocument).filter(OriginalDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="凭证不存在")

    old_data = json.loads(doc.ocr_structured) if doc.ocr_structured else {}
    new_data = data.get("ocr_structured", {})

    # 合并修正
    old_data.update(new_data)
    doc.ocr_structured = json.dumps(old_data, ensure_ascii=False)

    # 记录审计日志
    log_action(db, "document", doc_id, "corrected", operator="user", detail={
        "field": "ocr_structured",
        "old": doc.ocr_structured,
        "new": new_data,
    })

    db.commit()
    return {
        "message": "OCR 数据已修正",
        "document_id": doc_id,
        "ocr_structured": old_data,
    }


# ========================
# 环节 2：AI 凭证分录修正
# ========================

@router.patch("/voucher/{voucher_id}/entries")
def correct_voucher_entries(voucher_id: str, data: dict, db: Session = Depends(get_db), _=Depends(require_modify)):
    """人工修改 AI 生成的记账凭证分录"""
    v = db.query(AccountingVoucher).filter(AccountingVoucher.id == voucher_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="凭证不存在")
    if v.status != "draft":
        raise HTTPException(status_code=400, detail="已确认的凭证不可修改，请先作废后重新生成")

    entries = data.get("entries")
    if not entries:
        raise HTTPException(status_code=400, detail="请提供修改后的 entries 列表")

    # 校验借贷平衡
    balanced, td, tc = validate_balance(entries)
    if not balanced:
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"借贷不平衡",
                "total_debit": td,
                "total_credit": tc,
                "diff": round(td - tc, 2),
            },
        )

    old_entries = json.loads(v.entries) if v.entries else []

    v.summary = data.get("summary", v.summary)
    v.entries = json.dumps(entries, ensure_ascii=False)
    v.total_debit = td
    v.total_credit = tc

    # 记录审计
    log_action(db, "voucher", voucher_id, "corrected", operator="user", detail={
        "summary": v.summary,
        "entries_before": old_entries,
        "entries_after": entries,
    })

    db.commit()
    return {
        "message": "分录已修正",
        "voucher_id": voucher_id,
        "entries": entries,
        "total_debit": td,
        "total_credit": tc,
    }


# ========================
# 环节 3：凭证复核驳回
# ========================

@router.patch("/voucher/{voucher_id}/reject")
def reject_voucher(voucher_id: str, data: dict, db: Session = Depends(get_db), _=Depends(require_modify)):
    """复核不通过，退回给 AI 或人工修改"""
    v = db.query(AccountingVoucher).filter(AccountingVoucher.id == voucher_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="凭证不存在")
    if v.status != "draft":
        raise HTTPException(status_code=400, detail="仅草稿状态的凭证可以驳回")

    reason = data.get("reason", "")
    issues = data.get("issues", [])

    v.status = "rejected"

    # 记录驳回原因
    log_action(db, "voucher", voucher_id, "rejected", operator="user", detail={
        "reason": reason,
        "issues": issues,
    })

    db.commit()
    return {
        "message": "凭证已退回，请修改后重新提交",
        "voucher_id": voucher_id,
        "reason": reason,
        "issues": issues,
    }


# ========================
# 环节 4：申报前审核
# ========================

@router.patch("/filing/{filing_id}/review")
def review_filing(filing_id: str, data: dict, db: Session = Depends(get_db), _=Depends(require_modify)):
    """人工审核申报数据，可修改后提交 RPA"""
    f = db.query(TaxFiling).filter(TaxFiling.id == filing_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="申报记录不存在")

    action = data.get("action")  # approve / reject / modify
    comment = data.get("comment", "")

    if action == "approve":
        f.status = "submitted"
        log_action(db, "filing", filing_id, "approved", operator="user", detail={"comment": comment})
    elif action == "reject":
        f.status = "pending"
        log_action(db, "filing", filing_id, "rejected", operator="user", detail={"comment": comment})
    elif action == "modify":
        if "filing_data" in data:
            f.filing_result = json.dumps(data["filing_data"], ensure_ascii=False)
        log_action(db, "filing", filing_id, "corrected", operator="user", detail={"comment": comment, "data": data.get("filing_data")})
    else:
        raise HTTPException(status_code=400, detail=f"无效操作: {action}，支持 approve/reject/modify")

    db.commit()
    return {"message": f"申报审核{action}操作完成", "filing_id": filing_id, "status": f.status}


# ========================
# 通用：审计日志查询
# ========================

@router.get("/audit/{target_type}/{target_id}")
def audit_trail(target_type: str, target_id: str, db: Session = Depends(get_db)):
    """查询某个目标的操作审计历史"""
    trail = get_audit_trail(db, target_type, target_id)
    return {
        "target_type": target_type,
        "target_id": target_id,
        "total": len(trail),
        "trail": trail,
    }
