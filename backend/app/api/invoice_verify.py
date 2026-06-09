"""发票真伪查验 API"""
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import Optional
import os

router = APIRouter()

HEADLESS = os.getenv("AUTOMATION_HEADLESS", "true").lower() == "true"


class VerifyRequest(BaseModel):
    invoice_code: str     # 发票代码 10或12位
    invoice_no: str       # 发票号码 8位
    invoice_date: str     # 开票日期 YYYY-MM-DD
    amount: str = ""      # 开具金额（不含税）
    check_code: str = ""  # 校验码后6位


class BatchVerifyRequest(BaseModel):
    invoices: list[VerifyRequest]


@router.post("/verify")
async def verify_single(req: VerifyRequest):
    """单张发票真伪查验"""
    from app.services.invoice_verifier import verify_invoice
    import asyncio

    result = await verify_invoice(
        invoice_code=req.invoice_code,
        invoice_no=req.invoice_no,
        invoice_date=req.invoice_date,
        amount=req.amount,
        check_code=req.check_code,
        headless=HEADLESS,
    )

    return {
        "success": result.success,
        "is_valid": result.is_valid,
        "message": result.message,
        "invoice_code": result.invoice_code,
        "invoice_no": result.invoice_no,
        "details": {
            "invoice_type": result.invoice_type,
            "seller_name": result.seller_name,
            "seller_tax_no": result.seller_tax_no,
            "buyer_name": result.buyer_name,
            "buyer_tax_no": result.buyer_tax_no,
            "invoice_date": result.invoice_date,
            "total_amount": result.total_amount,
            "tax_amount": result.tax_amount,
            "grand_total": result.grand_total,
            "verify_count": result.verify_count,
        },
        "screenshot": result.screenshot,
    }


@router.post("/verify/batch")
async def verify_batch(req: BatchVerifyRequest):
    """批量发票真伪查验"""
    from app.services.invoice_verifier import batch_verify_invoices
    import asyncio

    invoices_data = [r.model_dump() for r in req.invoices]
    results = await batch_verify_invoices(invoices_data, headless=HEADLESS, max_concurrent=2)

    return {
        "total": len(results),
        "valid": sum(1 for r in results if r.is_valid),
        "invalid": sum(1 for r in results if r.success and not r.is_valid),
        "failed": sum(1 for r in results if not r.success),
        "results": [
            {
                "invoice_code": r.invoice_code,
                "invoice_no": r.invoice_no,
                "is_valid": r.is_valid,
                "message": r.message,
                "details": {
                    "invoice_type": r.invoice_type,
                    "seller_name": r.seller_name,
                    "buyer_name": r.buyer_name,
                    "invoice_date": r.invoice_date,
                    "total_amount": r.total_amount,
                    "tax_amount": r.tax_amount,
                    "grand_total": r.grand_total,
                },
                "screenshot": r.screenshot,
            }
            for r in results
        ],
    }


@router.post("/verify/{invoice_id}")
async def verify_system_invoice(invoice_id: str):
    """查验系统中已记录的一张发票"""
    from app.db import SessionLocal
    from app.models.invoice import Invoice
    from app.services.invoice_verifier import verify_invoice
    import asyncio, json

    db = SessionLocal()
    try:
        inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not inv:
            raise HTTPException(404, "发票不存在")

        # 尝试从 items 获取金额
        amount = ""
        try:
            items = json.loads(inv.items) if inv.items else []
            if items:
                amount = str(float(inv.total_amount or items[0].get("amount", 0) or 0))
        except Exception:
            amount = inv.total_amount or ""

        result = await verify_invoice(
            invoice_code=inv.invoice_code or "",
            invoice_no=inv.invoice_no or "",
            invoice_date=(inv.issued_at.strftime("%Y-%m-%d") if inv.issued_at else ""),
            amount=amount,
            headless=HEADLESS,
        )

        # 回写查验结果
        if result.is_valid:
            inv.screenshot_path = result.screenshot
            db.commit()

        return {
            "invoice_id": invoice_id,
            "success": result.success,
            "is_valid": result.is_valid,
            "message": result.message,
            "details": {
                "invoice_type": result.invoice_type,
                "seller_name": result.seller_name,
                "buyer_name": result.buyer_name,
                "total_amount": result.total_amount,
                "grand_total": result.grand_total,
            },
            "screenshot": result.screenshot,
        }
    finally:
        db.close()
