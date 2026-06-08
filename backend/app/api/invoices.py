"""数电票开票 API"""
import json
import uuid
from datetime import datetime, UTC
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.invoice import Invoice
from app.models.user import User
from app.services.auth import require_modify, get_current_user, check_client_access
from app.services.tax_invoice import issue_invoice_playwright
from app.services.qr_service import create_trace
from app.services.version_control import commit
from app.schemas.core import InvoiceCreate

router = APIRouter()


@router.get("/")
def list_invoices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    client_id: str = Query(None),
    status: str = Query(None),
    db: Session = Depends(get_db),
):
    """获取开票列表"""
    q = db.query(Invoice)
    if client_id:
        q = q.filter(Invoice.client_id == client_id)
    if status:
        q = q.filter(Invoice.status == status)
    total = q.count()
    items = q.order_by(Invoice.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    result = []
    for inv in items:
        result.append({
            "id": inv.id,
            "client_id": inv.client_id,
            "buyer_name": inv.buyer_name,
            "buyer_tax_no": inv.buyer_tax_no,
            "invoice_type": inv.invoice_type,
            "items": json.loads(inv.items) if inv.items else [],
            "total_amount": inv.total_amount,
            "total_tax": inv.total_tax,
            "grand_total": inv.grand_total,
            "remark": inv.remark,
            "status": inv.status,
            "issued_at": inv.issued_at.isoformat() if inv.issued_at else None,
            "invoice_code": inv.invoice_code,
            "invoice_no": inv.invoice_no,
            "invoice_url": inv.invoice_url,
            "screenshot_path": inv.screenshot_path,
            "created_by": inv.created_by,
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
        })
    return {"items": result, "total": total, "page": page, "page_size": page_size}


@router.post("/")
def create_invoice(
    data: InvoiceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _=Depends(require_modify),
):
    """创建开票申请（草稿）— Pydantic 校验"""
    if data.idempotency_key:
        existing = db.query(Invoice).filter(Invoice.idempotency_key == data.idempotency_key).first()
        if existing:
            return {
                "id": existing.id,
                "message": "开票申请已存在（幂等）",
                "status": existing.status,
            }

    items = [it.model_dump() for it in data.items]
    total_amount = sum(it.get("amount", 0) or 0 for it in items)
    total_tax = sum(it.get("tax_amount", 0) or 0 for it in items)

    invoice = Invoice(
        id=str(uuid.uuid4()),
        client_id=data.client_id,
        buyer_name=data.buyer_name,
        buyer_tax_no=data.buyer_tax_no,
        buyer_address=data.buyer_address or "",
        buyer_phone=data.buyer_phone or "",
        buyer_bank=data.buyer_bank or "",
        buyer_account=data.buyer_account or "",
        invoice_type=data.invoice_type,
        items=json.dumps(items, ensure_ascii=False),
        total_amount=str(round(total_amount, 2)),
        total_tax=str(round(total_tax, 2)),
        grand_total=str(round(total_amount + total_tax, 2)),
        remark=data.remark or "",
        status="draft",
        idempotency_key=data.idempotency_key or None,
        created_by=user.display_name or "",
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)

    create_trace(db, "invoice", invoice.id, "created")
    commit(db, "invoice", invoice.id, "created", user.display_name or "",
           after={"buyer_name": invoice.buyer_name, "invoice_type": invoice.invoice_type, "grand_total": invoice.grand_total})

    return {
        "id": invoice.id,
        "message": "开票申请已创建",
        "status": "draft",
    }


@router.post("/{invoice_id}/issue")
async def issue_invoice(
    invoice_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user=Depends(require_modify),
):
    """一键开票 — 调用 Playwright 自动登录电子税务局开具数电票"""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="开票记录不存在")
    if invoice.client_id and not check_client_access(invoice.client_id, user, db):
        raise HTTPException(status_code=403, detail="无权访问该客户数据")
    if invoice.status == "issued":
        raise HTTPException(status_code=400, detail="该发票已开具")

    from app.api.settings import get_tax_credentials
    tax_credentials = get_tax_credentials(db)

    # 标记为开票中
    invoice.status = "issuing"
    db.commit()

    items = json.loads(invoice.items) if invoice.items else []

    try:
        result = await issue_invoice_playwright(
            invoice_id=invoice.id,
            buyer_name=invoice.buyer_name,
            buyer_tax_no=invoice.buyer_tax_no,
            buyer_address=invoice.buyer_address or "",
            buyer_phone=invoice.buyer_phone or "",
            buyer_bank=invoice.buyer_bank or "",
            buyer_account=invoice.buyer_account or "",
            invoice_type=invoice.invoice_type,
            items=items,
            remark=invoice.remark or "",
            tax_credentials=tax_credentials,
        )

        if result["success"]:
            invoice.status = "issued"
            invoice.issued_at = datetime.now(UTC)
            invoice.invoice_code = result.get("invoice_code", "")
            invoice.invoice_no = result.get("invoice_no", "")
            invoice.invoice_url = result.get("invoice_url", "")
            invoice.screenshot_path = result.get("screenshot", "")
            create_trace(db, "invoice", invoice.id, "issued")
            db.commit()
            return {"success": True, "message": result["message"], "screenshot": result.get("screenshot", "")}
        else:
            invoice.status = "failed"
            db.commit()
            return {"success": False, "message": result.get("message", "开票失败")}

    except Exception as e:
        invoice.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"开票引擎异常: {str(e)[:200]}")


@router.get("/{invoice_id}")
def get_invoice(invoice_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """获取单张开票记录详情"""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="开票记录不存在")
    if invoice.client_id and not check_client_access(invoice.client_id, user, db):
        raise HTTPException(status_code=403, detail="无权访问该客户数据")
    return {
        "id": invoice.id,
        "client_id": invoice.client_id,
        "buyer_name": invoice.buyer_name,
        "buyer_tax_no": invoice.buyer_tax_no,
        "buyer_address": invoice.buyer_address,
        "buyer_phone": invoice.buyer_phone,
        "buyer_bank": invoice.buyer_bank,
        "buyer_account": invoice.buyer_account,
        "invoice_type": invoice.invoice_type,
        "items": json.loads(invoice.items) if invoice.items else [],
        "total_amount": invoice.total_amount,
        "total_tax": invoice.total_tax,
        "grand_total": invoice.grand_total,
        "remark": invoice.remark,
        "status": invoice.status,
        "issued_at": invoice.issued_at.isoformat() if invoice.issued_at else None,
        "invoice_code": invoice.invoice_code,
        "invoice_no": invoice.invoice_no,
        "invoice_url": invoice.invoice_url,
        "screenshot_path": invoice.screenshot_path,
        "created_by": invoice.created_by,
        "created_at": invoice.created_at.isoformat() if invoice.created_at else None,
    }


@router.delete("/{invoice_id}")
def delete_invoice(invoice_id: str, db: Session = Depends(get_db), user=Depends(require_modify)):
    """删除开票记录"""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="开票记录不存在")
    if invoice.client_id and not check_client_access(invoice.client_id, user, db):
        raise HTTPException(status_code=403, detail="无权访问该客户数据")
    commit(db, "invoice", invoice.id, "deleted", user.display_name or "",
           before={"buyer_name": invoice.buyer_name, "status": invoice.status})
    db.delete(invoice)
    db.commit()
    return {"message": "已删除"}
