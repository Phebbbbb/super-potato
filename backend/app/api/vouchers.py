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
                "maker": v.maker,
                "reviewer": v.reviewer,
                "bookkeeper": v.bookkeeper,
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
        "maker": v.maker,
        "reviewer": v.reviewer,
        "bookkeeper": v.bookkeeper,
        "qr_code_path": v.qr_code_path,
        "trace_chain": trace,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


@router.post("/")
def create_manual_voucher(data: VoucherCreate, db: Session = Depends(get_db), user=Depends(require_modify)):
    """手工录入记账凭证 — Pydantic 校验借贷平衡"""
    entries = [e.model_dump() for e in data.entries]
    balanced, td, tc = validate_balance(entries)

    maker_name = data.maker or (user.display_name or user.username if hasattr(user, 'display_name') else "制单员")
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
        maker=maker_name,
        client_id=data.client_id,
    )
    db.add(voucher)
    db.flush()
    create_trace(db, "voucher", voucher.id, "manual_voucher")
    commit(db, "voucher", voucher.id, "created", maker_name,
           after={"voucher_no": voucher_no, "summary": data.summary, "entries_count": len(entries)})
    from app.services.audit_service import log_action
    log_action(db, "voucher", voucher.id, "created", operator=maker_name,
               detail={"voucher_no": voucher_no, "client_id": data.client_id, "summary": data.summary})
    db.commit()
    return {"id": voucher.id, "voucher_no": voucher_no, "message": "凭证创建成功", "maker": maker_name}


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
        maker="AI系统",
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
    """确认记账凭证 — 审核人复核通过（不相容职务分离：制单人 ≠ 审核人）"""
    v = db.query(AccountingVoucher).filter(AccountingVoucher.id == voucher_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="凭证不存在")
    if v.client_id and not check_client_access(v.client_id, user, db):
        raise HTTPException(status_code=403, detail="无权访问该客户数据")
    if v.status not in ("draft", "pending_review"):
        raise HTTPException(status_code=400, detail="只有草稿或待审核状态的凭证可以确认")

    # ===== 不相容职务分离：制单人 ≠ 审核人 =====
    if v.maker and v.maker == data.reviewer:
        raise HTTPException(
            status_code=422,
            detail=f"制单人({v.maker})与审核人({data.reviewer})不能为同一人。根据《会计法》第三十七条，记账人员与经济业务事项的审批人员、经办人员、财物保管人员应当实行职务分离。请更换审核人。"
        )

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
        "maker": v.maker,
        "reviewer": v.reviewer,
        "comment": v.review_comment,
        "separation_check": "passed",
    })

    db.commit()
    return {
        "message": "凭证已审核通过",
        "voucher_no": v.voucher_no,
        "status": "confirmed",
        "maker": v.maker,
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

    from app.services.audit_service import log_action
    log_action(db, "voucher", voucher_id, "updated", operator=user.display_name or user.username or "",
               detail={"summary": data.summary or v.summary, "client_id": v.client_id})

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

    from app.services.audit_service import log_action
    log_action(db, "voucher", voucher_id, "deleted", operator=user.display_name or user.username or "",
               detail={"voucher_no": v.voucher_no, "client_id": v.client_id, "summary": v.summary})

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
    """批量确认记账凭证（不相容职务分离检查）"""
    confirm_count = 0
    skipped = []
    separation_rejected = []
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
        if v.maker and v.maker == reviewer:
            separation_rejected.append(v.voucher_no)
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
        "message": f"已批量确认 {confirm_count} 张凭证"
                  + (f"，{len(separation_rejected)} 张因制单人与审核人相同被拒绝" if separation_rejected else ""),
        "confirmed": confirm_count,
        "skipped": skipped,
        "separation_rejected": separation_rejected,
    }


@router.post("/{voucher_id}/rollback")
def rollback_voucher(voucher_id: str, db: Session = Depends(get_db), user=Depends(require_modify)):
    """回退凭证状态 → draft（仅 pending_review 状态可回退）"""
    v = db.query(AccountingVoucher).filter(AccountingVoucher.id == voucher_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="凭证不存在")
    if v.client_id and not check_client_access(v.client_id, user, db):
        raise HTTPException(status_code=403, detail="无权访问该客户数据")
    if v.status != "pending_review":
        raise HTTPException(status_code=400, detail="只有待审核状态的凭证可以回退")

    v.status = "draft"
    v.reviewer = None
    v.reviewed_at = None
    v.review_comment = None

    commit(db, "voucher", voucher_id, "rolled_back", user.display_name or "",
           before={"status": "pending_review"}, after={"status": "draft"})
    db.commit()
    return {"message": f"凭证 {v.voucher_no} 已回退至草稿", "id": voucher_id}


@router.post("/{voucher_id}/reverse")
def reverse_voucher(
    voucher_id: str,
    reason: str = Query("", description="冲销原因"),
    db: Session = Depends(get_db),
    user=Depends(require_modify),
):
    """红字冲销 — 对已确认的凭证创建反向冲销凭证（原凭证不可修改不可删除，只能冲销）"""
    v = db.query(AccountingVoucher).filter(AccountingVoucher.id == voucher_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="凭证不存在")
    if v.client_id and not check_client_access(v.client_id, user, db):
        raise HTTPException(status_code=403, detail="无权访问该客户数据")
    if v.status != "confirmed":
        raise HTTPException(status_code=400, detail="只有已确认的凭证才能冲销")
    if v.status == "reversed":
        raise HTTPException(status_code=400, detail="该凭证已被冲销")

    # 原分录取反
    entries = json.loads(v.entries) if v.entries else []
    reversed_entries = []
    for e in entries:
        reversed_entries.append({
            "account_code": e.get("account_code", ""),
            "account_name": e.get("account_name", ""),
            "summary": f"[红字冲销] {e.get('summary', '')}",
            "debit": round(e.get("credit", 0), 2),
            "credit": round(e.get("debit", 0), 2),
        })

    # 生成红字冲销凭证
    reversed_voucher_no = generate_voucher_no(db, v.voucher_date)
    reversed_voucher = AccountingVoucher(
        id=str(uuid.uuid4()),
        voucher_no=reversed_voucher_no,
        voucher_date=v.voucher_date,
        summary=f"红字冲销 — 原凭证 {v.voucher_no}：{reason or '冲正'}",
        entries=json.dumps(reversed_entries, ensure_ascii=False),
        total_debit=v.total_credit,
        total_credit=v.total_debit,
        status="confirmed",  # 冲销凭证直接确认
        created_by="manual",
        maker=user.display_name or user.username or "",
        reviewer=user.display_name or user.username or "",
        client_id=v.client_id,
    )
    db.add(reversed_voucher)
    db.flush()

    # 原凭证标记为已冲销
    v.status = "reversed"
    v.review_comment = (v.review_comment or "") + f" | 于 {reversed_voucher_no} 冲销: {reason or '冲正'}"

    # 链路追溯
    create_trace(db, "voucher", v.id, "confirm")
    create_trace(db, "voucher", reversed_voucher.id, "confirm")

    from app.services.audit_service import log_action
    log_action(db, "voucher", v.id, "reversed", operator=user.display_name or user.username or "",
               detail={"reason": reason, "reversed_by_voucher": reversed_voucher_no})
    log_action(db, "voucher", reversed_voucher.id, "created", operator=user.display_name or user.username or "",
               detail={"type": "红字冲销", "reversed_voucher_id": v.id, "reason": reason})

    commit(db, "voucher", v.id, "reversed", user.display_name or "",
           before={"status": "confirmed", "voucher_no": v.voucher_no},
           after={"status": "reversed", "reversed_by": reversed_voucher_no})

    db.commit()
    return {
        "id": reversed_voucher.id,
        "voucher_no": reversed_voucher_no,
        "original_voucher_no": v.voucher_no,
        "message": f"红字冲销凭证 {reversed_voucher_no} 已生成，原凭证 {v.voucher_no} 已标记为已冲销",
    }
