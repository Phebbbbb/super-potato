"""
批量自动化 API — 并行多客户申报/开票 + 进度追踪
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.db import SessionLocal
from app.services.auth import get_current_user
from app.services.automation_pool import (
    get_filing_engine, get_invoice_engine,
    ParallelFilingEngine, ParallelInvoiceEngine,
)
from app.services.error_handler import log_error, log_info

router = APIRouter()

# 引擎实例（headless 由环境变量控制）
import os
HEADLESS = os.getenv("AUTOMATION_HEADLESS", "true").lower() == "true"
POOL_SIZE = int(os.getenv("AUTOMATION_POOL_SIZE", "3"))


class BatchFilingRequest(BaseModel):
    filings: list[dict]  # [{client_id, client_name, tax_type, period, tax_data, priority}]
    profile: str = "generic"
    credentials_map: dict[str, dict] = {}  # {client_id: {username, password, province}}


class BatchInvoiceRequest(BaseModel):
    invoices: list[dict]  # [{client_id, invoice_id, buyer_name, buyer_tax_no, ...}]
    profile: str = "generic"
    credentials_map: dict[str, dict] = {}


@router.post("/batch-filing")
async def batch_filing(req: BatchFilingRequest):
    """并行批量申报：多客户同时提交电子税务局申报"""
    if not req.filings:
        raise HTTPException(400, "filings 不能为空")

    engine = get_filing_engine(pool_size=POOL_SIZE, headless=HEADLESS)

    # 异步执行批量任务
    import asyncio
    job = await engine.submit_batch(
        tasks_data=req.filings,
        credentials_map=req.credentials_map,
        profile=req.profile,
    )

    log_info("batch_api", "batch_filing_done", f"job={job.job_id} total={job.total} success={job.success}")

    return {
        "job_id": job.job_id,
        "status": job.status,
        "total": job.total,
        "success": job.success,
        "failed": job.failed,
        "tasks": [
            {
                "task_id": t.task_id,
                "client_id": t.client_id,
                "client_name": t.client_name,
                "tax_type": t.tax_type,
                "status": t.status,
                "result": t.result,
                "error": t.error,
                "completed_at": t.completed_at,
            }
            for t in job.tasks
        ],
    }


@router.post("/batch-invoice")
async def batch_invoice(req: BatchInvoiceRequest):
    """并行批量开票：多客户同时开具数电票"""
    if not req.invoices:
        raise HTTPException(400, "invoices 不能为空")

    engine = get_invoice_engine(pool_size=POOL_SIZE, headless=HEADLESS)

    import asyncio
    job = await engine.submit_batch(
        invoices_data=req.invoices,
        credentials_map=req.credentials_map,
        profile=req.profile,
    )

    log_info("batch_api", "batch_invoice_done", f"job={job.job_id} total={job.total} success={job.success}")

    return {
        "job_id": job.job_id,
        "status": job.status,
        "total": job.total,
        "success": job.success,
        "failed": job.failed,
        "tasks": [
            {
                "task_id": t.task_id,
                "client_id": t.client_id,
                "client_name": t.client_name,
                "invoice_id": t.invoice_id,
                "status": t.status,
                "result": t.result,
                "error": t.error,
                "completed_at": t.completed_at,
            }
            for t in job.tasks
        ],
    }


@router.get("/job/{job_id}")
async def get_job_status(job_id: str, _=Depends(get_current_user)):
    """查询批量任务进度"""
    filing = get_filing_engine().get_job_summary(job_id)
    if "error" not in filing:
        return filing

    invoice = get_invoice_engine().get_job_summary(job_id)
    if "error" not in invoice:
        return invoice

    raise HTTPException(404, f"任务不存在: {job_id}")


@router.post("/batch-all-clients")
async def batch_all_clients(
    operation: str = Query(..., description="操作类型: filing | invoice | both"),
    profile: str = Query("generic"),
):
    """
    一键全客户批量操作：
    - filing: 扫描所有客户待申报项，批量提交
    - invoice: 扫描所有客户草稿发票，批量开具
    - both: 先申报后开票
    """
    from app.models.client import Client
    from app.models.filing import TaxFiling
    from app.models.invoice import Invoice

    db = SessionLocal()
    try:
        clients = db.query(Client).filter(Client.is_active == True).all()

        # 获取税局凭据
        from app.api.settings import get_tax_credentials
        creds = get_tax_credentials(db)
        credentials_map = {}
        for c in clients:
            credentials_map[c.id] = {
                "username": creds.get("username", ""),
                "password": creds.get("password", ""),
                "province": creds.get("province", profile),
            }

        results = {}

        if operation in ("filing", "both"):
            # 收集所有 pending 申报
            all_filings = []
            for c in clients:
                pending = db.query(TaxFiling).filter(
                    TaxFiling.client_id == c.id,
                    TaxFiling.status == "pending",
                ).all()
                for f in pending:
                    all_filings.append({
                        "client_id": c.id,
                        "client_name": c.name,
                        "tax_type": f.tax_type,
                        "period": f.period,
                        "filing_id": f.id,
                        "tax_data": {},
                        "priority": 3,
                    })

            if all_filings:
                engine = get_filing_engine(pool_size=POOL_SIZE, headless=HEADLESS)
                import asyncio
                job = await engine.submit_batch(
                    tasks_data=all_filings,
                    credentials_map=credentials_map,
                    profile=profile,
                    on_progress=None,
                )

                # 回写成功状态到数据库
                for task in job.tasks:
                    if task.status == "success":
                        filing = db.query(TaxFiling).filter(TaxFiling.id == task.payload.get("filing_id")).first()
                        if filing:
                            filing.status = "submitted"
                            filing.filing_result = task.result.get("message", "")
                db.commit()

                results["filing"] = {
                    "job_id": job.job_id, "total": job.total,
                    "success": job.success, "failed": job.failed,
                }
            else:
                results["filing"] = {"total": 0, "message": "无待申报项"}

        if operation in ("invoice", "both"):
            # 收集所有 draft 发票
            all_invoices = []
            import json as _json
            for c in clients:
                drafts = db.query(Invoice).filter(
                    Invoice.client_id == c.id,
                    Invoice.status == "draft",
                ).all()
                for inv in drafts:
                    items_data = []
                    try:
                        items_data = _json.loads(inv.items) if inv.items else []
                    except Exception:
                        pass
                    all_invoices.append({
                        "client_id": c.id,
                        "client_name": c.name,
                        "invoice_id": inv.id,
                        "buyer_name": inv.buyer_name or "",
                        "buyer_tax_no": inv.buyer_tax_no or "",
                        "buyer_address": inv.buyer_address or "",
                        "buyer_phone": inv.buyer_phone or "",
                        "buyer_bank": inv.buyer_bank or "",
                        "buyer_account": inv.buyer_account or "",
                        "invoice_type": inv.invoice_type or "electronic_normal",
                        "items": items_data,
                        "remark": inv.remark or "",
                        "priority": 5,
                    })

            if all_invoices:
                engine = get_invoice_engine(pool_size=POOL_SIZE, headless=HEADLESS)
                import asyncio
                job = await engine.submit_batch(
                    invoices_data=all_invoices,
                    credentials_map=credentials_map,
                    profile=profile,
                    on_progress=None,
                )

                # 回写状态
                for task in job.tasks:
                    if task.status == "success":
                        inv = db.query(Invoice).filter(Invoice.id == task.invoice_id).first()
                        if inv:
                            inv.status = "issued"
                            inv.invoice_code = task.result.get("invoice_code", "")
                            inv.issued_at = datetime.now()
                db.commit()

                results["invoice"] = {
                    "job_id": job.job_id, "total": job.total,
                    "success": job.success, "failed": job.failed,
                }
            else:
                results["invoice"] = {"total": 0, "message": "无待开票发票"}

        return {"operation": operation, "clients_count": len(clients), "results": results}

    except Exception as e:
        log_error("batch_api", e, {"operation": operation})
        raise HTTPException(500, f"批量操作失败: {str(e)[:200]}")
    finally:
        db.close()


@router.get("/pool-stats")
async def pool_stats():
    """获取自动化引擎池状态"""
    return {
        "pool_size": POOL_SIZE,
        "headless": HEADLESS,
        "engines": {
            "filing": "ready",
            "invoice": "ready",
        },
    }
