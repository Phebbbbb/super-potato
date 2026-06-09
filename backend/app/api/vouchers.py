import json
import uuid
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.db import get_db
from app.models.voucher import AccountingVoucher
from app.models.document import OriginalDocument
from app.services.voucher_service import generate_voucher_no, validate_balance, build_entries_from_documents
from app.services.ai_service import ai_generate_voucher
from app.services.qr_service import create_trace
from app.services.auth import get_current_user, require_modify, check_client_access, check_optimistic_lock
from app.services.version_control import commit
from app.schemas.core import VoucherCreate, VoucherConfirm, VoucherUpdate

router = APIRouter()


@router.get("/")
def list_vouchers(
    page: int = 1,
    page_size: int = 20,
    status: str = None,
    start_date: str = None,
    end_date: str = None,
    client_id: str = Query(None),
    db: Session = Depends(get_db),
):
    """记账凭证列表"""
    q = db.query(AccountingVoucher)
    if status:
        q = q.filter(AccountingVoucher.status == status)
    if start_date:
        q = q.filter(AccountingVoucher.voucher_date >= start_date)
    if end_date:
        q = q.filter(AccountingVoucher.voucher_date <= end_date)
    if client_id:
        q = q.filter(AccountingVoucher.client_id == client_id)

    total = q.count()
    items = (
        q.order_by(desc(AccountingVoucher.voucher_date), desc(AccountingVoucher.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "items": [
            {
                "id": v.id,
                "voucher_no": v.voucher_no,
                "voucher_date": v.voucher_date.isoformat() if v.voucher_date else None,
                "summary": v.summary,
                "entries": json.loads(v.entries) if v.entries else [],
                "total_debit": v.total_debit,
                "total_credit": v.total_credit,
                "status": v.status,
                "created_by": v.created_by,
                "qr_code_path": v.qr_code_path,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{voucher_id}")
def get_voucher(voucher_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """记账凭证详情（含追溯链）"""
    v = db.query(AccountingVoucher).filter(AccountingVoucher.id == voucher_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="凭证不存在")
    if v.client_id and not check_client_access(v.client_id, user, db):
        raise HTTPException(status_code=403, detail="无权访问该客户数据")

    from app.services.qr_service import get_trace_chain
    trace = get_trace_chain(db, "voucher", v.id)

    return {
        "id": v.id,
        "voucher_no": v.voucher_no,
        "voucher_date": v.voucher_date.isoformat() if v.voucher_date else None,
        "summary": v.summary,
        "source_doc_ids": json.loads(v.source_doc_ids) if v.source_doc_ids else [],
        "entries": json.loads(v.entries) if v.entries else [],
        "total_debit": v.total_debit,
        "total_credit": v.total_credit,
        "status": v.status,
        "created_by": v.created_by,
        "qr_code_path": v.qr_code_path,
        "trace_chain": trace,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


@router.post("/")
def create_manual_voucher(data: VoucherCreate, db: Session = Depends(get_db), _=Depends(require_modify)):
    """手工录入记账凭证 — Pydantic 校验借贷平衡"""
    entries = [e.model_dump() for e in data.entries]
    balanced, td, tc = validate_balance(entries)

    voucher_no = generate_voucher_no(db, data.voucher_date)
    voucher = AccountingVoucher(
        id=str(uuid.uuid4()),
        voucher_no=voucher_no,
        voucher_date=data.voucher_date,
        summary=data.summary or "手工录入",
        entries=json.dumps(entries, ensure_ascii=False),
        total_debit=td,
        total_credit=tc,
        status="draft",
        created_by="manual",
        client_id=data.client_id,
    )
    db.add(voucher)
    db.flush()
    create_trace(db, "voucher", voucher.id, "manual_voucher")
    commit(db, "voucher", voucher.id, "created", "manual",
           after={"voucher_no": voucher_no, "summary": data.summary, "entries_count": len(entries)})
    db.commit()
    return {"id": voucher.id, "voucher_no": voucher_no, "message": "凭证创建成功"}


@router.post("/ai-generate")
async def ai_generate_voucher_api(document_ids: list[str], client_id: str = Query(None), db: Session = Depends(get_db), _=Depends(require_modify)):
    """AI 智能生成记账凭证 — 全自动化核心接口"""
    if not document_ids:
        raise HTTPException(status_code=400, detail="请选择至少一个原始凭证")

    # 获取原始凭证数据
    docs = db.query(OriginalDocument).filter(OriginalDocument.id.in_(document_ids)).all()
    if not docs:
        raise HTTPException(status_code=404, detail="未找到原始凭证")

    docs_data = []
    for d in docs:
        docs_data.append({
            "id": d.id,
            "doc_type": d.doc_type,
            "file_name": d.file_name,
            "ocr_structured": json.loads(d.ocr_structured) if d.ocr_structured else {},
        })

    # AI 生成分录
    ai_result = await ai_generate_voucher(docs_data)
    entries = ai_result.get("entries", [])

    # 如果 AI 返回为空，使用规则引擎兜底
    if not entries:
        entries = build_entries_from_documents(db, docs_data, ai_result.get("summary", ""))

    # 校验借贷平衡
    balanced, total_debit, total_credit = validate_balance(entries)
    if not balanced:
        # 尝试自动修正：调整最后一个条目
        diff = round(total_debit - total_credit, 2)
        if entries:
            if diff > 0:
                entries[-1]["credit"] = round((entries[-1].get("credit", 0) or 0) + diff, 2)
            else:
                entries[-1]["debit"] = round((entries[-1].get("debit", 0) or 0) - diff, 2)
        balanced, total_debit, total_credit = validate_balance(entries)

    if not balanced:
        raise HTTPException(status_code=422, detail=f"借贷不平衡: 借={total_debit}, 贷={total_credit}")

    # 确定凭证日期（取原始凭证中最晚的日期）
    voucher_date = None
    for d in docs_data:
        ocr = d.get("ocr_structured") or {}
        d_date = ocr.get("date")
        if d_date:
            from datetime import date as dt_date
            try:
                parsed = dt_date.fromisoformat(d_date)
                if voucher_date is None or parsed > voucher_date:
                    voucher_date = parsed
            except (ValueError, TypeError):
                pass
    if voucher_date is None:
        from datetime import date as dt_date
        voucher_date = dt_date.today()

    # 创建记账凭证
    voucher_no = generate_voucher_no(db, voucher_date)
    voucher = AccountingVoucher(
        id=str(uuid.uuid4()),
        voucher_no=voucher_no,
        voucher_date=voucher_date,
        summary=ai_result.get("summary", "AI 自动生成"),
        source_doc_ids=json.dumps(document_ids, ensure_ascii=False),
        entries=json.dumps(entries, ensure_ascii=False),
        total_debit=total_debit,
        total_credit=total_credit,
        status="draft",
        created_by="ai",
        client_id=client_id,
    )
    db.add(voucher)
    db.flush()

    # 生成 QR 码 #2 (AI 生成)
    trace = create_trace(db, "voucher", voucher.id, "ai_voucher")
    voucher.qr_code_path = trace.qr_code_path

    commit(db, "voucher", voucher.id, "auto_created", "ai",
           after={"voucher_no": voucher.voucher_no, "summary": voucher.summary, "total_debit": total_debit, "total_credit": total_credit})

    db.commit()

    return {
        "id": voucher.id,
        "voucher_no": voucher.voucher_no,
        "summary": voucher.summary,
        "entries": entries,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "status": "draft",
        "qr_code_path": voucher.qr_code_path,
        "message": "AI 凭证生成成功，请复核后确认",
    }


@router.patch("/{voucher_id}/confirm")
def confirm_voucher(voucher_id: str, data: VoucherConfirm = VoucherConfirm(), db: Session = Depends(get_db), user=Depends(require_modify)):
    """确认记账凭证 — 审核人复核通过"""
    v = db.query(AccountingVoucher).filter(AccountingVoucher.id == voucher_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="凭证不存在")
    if v.client_id and not check_client_access(v.client_id, user, db):
        raise HTTPException(status_code=403, detail="无权访问该客户数据")
    if v.status not in ("draft", "pending_review"):
        raise HTTPException(status_code=400, detail="只有草稿或待审核状态的凭证可以确认")

    check_optimistic_lock(v, data.model_dump())

    from datetime import datetime as dt_datetime
    v.status = "confirmed"
    v.reviewer = data.reviewer
    v.reviewed_at = dt_datetime.now()
    v.review_comment = data.comment

    # 生成 QR 码 #3 (审核确认)
    trace = create_trace(db, "voucher", v.id, "confirm")
    v.qr_code_path = trace.qr_code_path

    # 记录审计日志
    from app.services.audit_service import log_action
    log_action(db, "voucher", voucher_id, "confirmed", operator=v.reviewer, detail={
        "reviewer": v.reviewer,
        "comment": v.review_comment,
    })

    db.commit()
    return {
        "message": "凭证已审核通过",
        "voucher_no": v.voucher_no,
        "status": "confirmed",
        "reviewer": v.reviewer,
    }


@router.patch("/{voucher_id}")
def update_voucher(voucher_id: str, data: VoucherUpdate, db: Session = Depends(get_db), user=Depends(require_modify)):
    """修改记账凭证（仅草稿状态）"""
    v = db.query(AccountingVoucher).filter(AccountingVoucher.id == voucher_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="凭证不存在")
    if v.client_id and not check_client_access(v.client_id, user, db):
        raise HTTPException(status_code=403, detail="无权访问该客户数据")
    if v.status != "draft":
        raise HTTPException(status_code=400, detail="已确认的凭证不可修改")

    check_optimistic_lock(v, data.model_dump())

    before = {"summary": v.summary, "entries": v.entries, "status": v.status}

    if data.summary is not None:
        v.summary = data.summary
    if data.entries is not None:
        entries = [e.model_dump() for e in data.entries]
        balanced, td, tc = validate_balance(entries)
        if not balanced:
            raise HTTPException(status_code=422, detail=f"借贷不平衡: 借={td}, 贷={tc}")
        v.entries = json.dumps(entries, ensure_ascii=False)
        v.total_debit = td
        v.total_credit = tc

    after = {"summary": v.summary, "entries": v.entries, "status": v.status}
    commit(db, "voucher", voucher_id, "updated", user.display_name or "",
           before=before, after=after)

    db.commit()
    return {"message": "凭证已更新", "id": voucher_id}


@router.delete("/{voucher_id}")
def delete_voucher(voucher_id: str, db: Session = Depends(get_db), user=Depends(require_modify)):
    v = db.query(AccountingVoucher).filter(AccountingVoucher.id == voucher_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="凭证不存在")
    if v.client_id and not check_client_access(v.client_id, user, db):
        raise HTTPException(status_code=403, detail="无权访问该客户数据")
    if v.status == "confirmed":
        raise HTTPException(status_code=400, detail="已确认的凭证不可删除")
    commit(db, "voucher", voucher_id, "deleted", user.display_name or "",
           before={"summary": v.summary, "voucher_no": v.voucher_no, "status": v.status})
    db.delete(v)
    db.commit()
    return {"message": "凭证已删除", "id": voucher_id}


@router.post("/batch-confirm")
def batch_confirm_vouchers(
    voucher_ids: list[str] = Body(..., description="凭证ID列表"),
    reviewer: str = Query("批量审核", description="审核人"),
    comment: str = Query("", description="审核意见"),
    db: Session = Depends(get_db),
    user=Depends(require_modify),
):
    """批量确认记账凭证"""
    confirm_count = 0
    skipped = []
    for vid in voucher_ids:
        v = db.query(AccountingVoucher).filter(AccountingVoucher.id == vid).first()
        if not v:
            continue
        if v.client_id and not check_client_access(v.client_id, user, db):
            skipped.append(v.voucher_no)
            continue
        if v.status == "confirmed":
            skipped.append(v.voucher_no)
            continue
        v.status = "confirmed"
        v.reviewer = reviewer
        v.review_comment = comment or "批量审核通过"
        create_trace(db, "voucher", v.id, "confirm")
        commit(db, "voucher", v.id, "confirmed", reviewer,
               before={"status": "draft", "voucher_no": v.voucher_no},
               after={"status": "confirmed", "reviewer": reviewer})
        confirm_count += 1

    db.commit()
    return {
        "message": f"已批量确认 {confirm_count} 张凭证",
        "confirmed": confirm_count,
        "skipped": skipped,
    }
