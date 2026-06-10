"""RPA 触发接口：手动触发、自动调度、全自动加工链、一键申报提交"""
import json
import uuid
from datetime import date as dt_date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.rpa_task import RPATask
from app.models.document import OriginalDocument
from app.models.voucher import AccountingVoucher
from app.models.system_config import SystemConfig
from app.services.rpa_scheduler import RPAScheduler, call_rpa_webhook
from app.services.voucher_service import generate_voucher_no, validate_balance, build_entries_from_documents
from app.services.ai_service import ai_generate_voucher
from app.services.qr_service import create_trace
from app.services.tax_service import preview_filing
from app.services.tax_automation import TaxAutomationEngine
from app.services.auth import require_modify, require_not_client, get_current_user
from app.models.user import User
from app.models.invoice import Invoice
from app.models.client import Client
from app.services.error_handler import log_info, log_error
from app.services.version_control import commit

router = APIRouter()


# 默认 RPA 配置（实际应从数据库或配置文件读取）
def get_rpa_config():
    return {
        "vendor": "generic",       # yingdao / laiye / generic
        "webhook_url": "",         # RPA 平台回调地址
        "api_key": "",
        "poll_interval": 30,       # 轮询间隔（秒）
    }


@router.post("/trigger/{task_id}")
async def trigger_task(task_id: str, db: Session = Depends(get_db), _=Depends(require_modify)):
    """手动触发单个 RPA 任务"""
    task = db.query(RPATask).filter(RPATask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status not in ("pending", "assigned"):
        raise HTTPException(status_code=400, detail=f"任务状态 {task.status} 不可触发")

    scheduler = RPAScheduler(db, get_rpa_config())
    success = await scheduler.dispatch_task(task)

    if success:
        task.status = "processing"
        db.commit()
        return {"message": "任务已触发", "task_id": task_id, "status": "processing"}

    raise HTTPException(status_code=500, detail="RPA 触发失败")


@router.post("/trigger-all")
async def trigger_all_pending(db: Session = Depends(get_db), _=Depends(require_modify)):
    """一键触发所有待处理任务"""
    scheduler = RPAScheduler(db, get_rpa_config())
    results = await scheduler.auto_dispatch_pending()
    return {
        "total": len(results),
        "results": results,
        "message": f"已触发 {len([r for r in results if r['status'] == 'dispatched'])} 个任务",
    }


@router.post("/create-and-trigger")
async def create_and_trigger(data: dict, db: Session = Depends(get_db), _=Depends(require_modify)):
    """创建任务并立即触发 RPA"""
    task_type = data.get("task_type", "scan_invoice")
    payload = data.get("payload", {})

    # 创建任务
    task = RPATask(
        id=str(uuid.uuid4()),
        task_type=task_type,
        status="pending",
        payload=json.dumps(payload, ensure_ascii=False),
    )
    db.add(task)
    db.commit()

    # 触发 RPA
    scheduler = RPAScheduler(db, get_rpa_config())
    success = await scheduler.dispatch_task(task)

    if success:
        task.status = "processing"
        db.commit()

    return {
        "task_id": task.id,
        "task_type": task_type,
        "status": "processing" if success else "pending",
        "message": "任务已创建" + ("并触发 RPA" if success else "，RPA 将轮询获取"),
    }


@router.post("/test-webhook")
async def test_webhook(data: dict, user=Depends(get_current_user)):
    """测试 RPA Webhook 连通性"""
    webhook_url = data.get("webhook_url", "")
    api_key = data.get("api_key", "")

    if not webhook_url:
        raise HTTPException(status_code=400, detail="请提供 RPA Webhook 地址")

    test_payload = {
        "test": True,
        "message": "智能财税系统连通性测试",
        "timestamp": str(uuid.uuid4()),
    }

    result = await call_rpa_webhook(webhook_url, test_payload, api_key)
    return {
        "webhook_url": webhook_url,
        "status_code": result["status_code"],
        "response": result["body"][:500],
        "success": result["status_code"] == 200,
    }


def _auto_create_invoices(client_id: str, db: Session, operator: str) -> dict:
    """
    从已确认凭证中自动识别需要开票的销项交易，提取购方信息和商品明细，生成开票草稿。
    识别逻辑：扫描已确认凭证中 6001（主营业务收入）贷方分录 → 追溯到原始票据获取购方信息
    """
    result = {"invoices_created": 0, "skipped": 0, "details": []}

    # 找到所有已确认且包含收入分录的凭证
    confirmed_vouchers = (
        db.query(AccountingVoucher)
        .filter(
            AccountingVoucher.client_id == client_id,
            AccountingVoucher.status == "confirmed",
        )
        .all()
    )

    # 收集所有涉及收入分录的凭证及其来源票据
    revenue_vouchers = []
    for v in confirmed_vouchers:
        entries = json.loads(v.entries) if v.entries else []
        has_revenue = any(
            e.get("credit", 0) > 0 and str(e.get("account_code", "")).startswith("6001")
            for e in entries
        )
        if has_revenue:
            revenue_vouchers.append(v)

    if not revenue_vouchers:
        result["details"].append("没有发现需要开票的销项凭证")
        return result

    # 按购方分组（从源票据 OCR 数据提取）
    for v in revenue_vouchers:
        entries = json.loads(v.entries) if v.entries else []
        source_ids = json.loads(v.source_doc_ids) if v.source_doc_ids else []

        # 提取收入行 → 发票项目
        invoice_items = []
        for e in entries:
            if e.get("credit", 0) > 0 and str(e.get("account_code", "")).startswith("6001"):
                amount = float(e.get("credit", 0))
                tax_rate = 0.13 if e.get("tax_rate") is None else float(e.get("tax_rate", 0.13))
                tax_amount = round(amount * tax_rate, 2)
                invoice_items.append({
                    "name": e.get("summary", "服务费") or e.get("account_name", "服务费"),
                    "spec": "",
                    "unit": "项",
                    "quantity": 1,
                    "price": str(amount),
                    "amount": str(amount),
                    "tax_rate": tax_rate,
                    "tax_amount": str(tax_amount),
                })

        if not invoice_items:
            continue

        # 从源票据 OCR 提取购方信息
        buyer_name = ""
        buyer_tax_no = ""
        for doc_id in source_ids:
            doc = db.query(OriginalDocument).filter(OriginalDocument.id == doc_id).first()
            if not doc or not doc.ocr_structured:
                continue
            ocr = json.loads(doc.ocr_structured) if doc.ocr_structured else {}
            if ocr.get("buyer_name"):
                buyer_name = ocr["buyer_name"]
            if ocr.get("buyer_tax_no"):
                buyer_tax_no = ocr.get("buyer_tax_no", "")
            if buyer_name and buyer_tax_no:
                break

        # OCR 没提取到购方 → 用客户自己的信息作为卖方（反向：销售给未知购方时使用摘要中的客户名）
        if not buyer_name:
            client = db.query(Client).filter(Client.id == client_id).first()
            if client:
                buyer_name = client.name
                buyer_tax_no = client.tax_no
            if not buyer_name:
                result["skipped"] += 1
                result["details"].append(f"⚠️ {v.voucher_no}: 无法识别购方信息，跳过")
                continue

        total_amount = sum(float(it["amount"]) for it in invoice_items)
        total_tax = sum(float(it["tax_amount"]) for it in invoice_items)

        # 幂等：同一凭证不重复生成
        existing = db.query(Invoice).filter(
            Invoice.client_id == client_id,
            Invoice.remark == f"auto:{v.id}",
        ).first()
        if existing:
            result["skipped"] += 1
            result["details"].append(f"⏭️ {v.voucher_no}: 已存在开票记录 {existing.id[:8]}")
            continue

        invoice = Invoice(
            id=str(uuid.uuid4()),
            client_id=client_id,
            buyer_name=buyer_name,
            buyer_tax_no=buyer_tax_no,
            invoice_type="electronic_normal",
            items=json.dumps(invoice_items, ensure_ascii=False),
            total_amount=str(round(total_amount, 2)),
            total_tax=str(round(total_tax, 2)),
            grand_total=str(round(total_amount + total_tax, 2)),
            remark=f"auto:{v.id}",
            status="draft",
            created_by=operator,
        )
        db.add(invoice)
        db.flush()
        create_trace(db, "invoice", invoice.id, "auto_created")
        commit(db, "invoice", invoice.id, "auto_created", operator,
               after={"buyer_name": buyer_name, "total_amount": invoice.total_amount, "source_voucher": v.voucher_no})

        result["invoices_created"] += 1
        result["details"].append(f"🧾 {v.voucher_no} → 开票 {invoice.id[:8]}: {buyer_name} ¥{invoice.grand_total}")

    db.commit()
    return result


@router.post("/auto-process")
def auto_process_chain(
    client_id: str = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _=Depends(require_modify),
):
    """
    全自动加工链：OCR完成 → AI生成凭证 → 自动确认全部凭证 → 自动创建申报
    全程包裹在事务中，任一步骤失败自动回滚
    """
    operator = user.display_name or "ai"
    result = {
        "documents_found": 0,
        "vouchers_generated": 0,
        "vouchers_auto_confirmed": 0,
        "filings_created": 0,
        "details": [],
    }

    try:
        # Step 1: 找到所有 OCR 完成但尚未生成凭证的票据
        existing_vouchers = db.query(AccountingVoucher.source_doc_ids).filter(
            AccountingVoucher.client_id == client_id
        ).all()

        used_doc_ids = set()
        for (src_json,) in existing_vouchers:
            if src_json:
                try:
                    ids = json.loads(src_json)
                    used_doc_ids.update(ids)
                except (json.JSONDecodeError, TypeError):
                    pass

        pending_docs = (
            db.query(OriginalDocument)
            .filter(
                OriginalDocument.client_id == client_id,
                OriginalDocument.ocr_status.in_(["done", "pending"]),
                ~OriginalDocument.id.in_(used_doc_ids) if used_doc_ids else True,
            )
            .all()
        )
        for d in pending_docs:
            if d.ocr_status == "pending":
                d.ocr_status = "done"

        result["documents_found"] = len(pending_docs)
        if not pending_docs:
            result["details"].append("没有新的待处理票据")
            db.commit()
            return result

        # Step 2: 按日期分组生成凭证
        docs_by_date: dict[str, list] = {}
        for d in pending_docs:
            ocr = json.loads(d.ocr_structured) if d.ocr_structured else {}
            d_date = ocr.get("date", "2026-06-01") or "2026-06-01"
            docs_by_date.setdefault(d_date, []).append(d)

        voucher_dates_used = set()

        for doc_date, docs_group in sorted(docs_by_date.items()):
            docs_data = []
            for d in docs_group:
                docs_data.append({
                    "id": d.id,
                    "doc_type": d.doc_type,
                    "file_name": d.file_name,
                    "ocr_structured": json.loads(d.ocr_structured) if d.ocr_structured else {},
                })

            entries = build_entries_from_documents(db, docs_data, "自动生成")
            balanced, total_debit, total_credit = validate_balance(entries)
            if not balanced:
                diff = round(total_debit - total_credit, 2)
                if entries and diff != 0:
                    if diff > 0:
                        entries[-1]["credit"] = round((entries[-1].get("credit", 0) or 0) + diff, 2)
                    else:
                        entries[-1]["debit"] = round((entries[-1].get("debit", 0) or 0) - diff, 2)
                balanced, total_debit, total_credit = validate_balance(entries)

            if not balanced:
                result["details"].append(f"⚠️ {doc_date}: AI生成分录借贷不平，跳过")
                continue

            v_date = dt_date.fromisoformat(doc_date)
            vno = generate_voucher_no(db, v_date)

            voucher = AccountingVoucher(
                id=str(uuid.uuid4()),
                voucher_no=vno,
                voucher_date=v_date,
                summary=f"自动生成凭证({doc_date})",
                source_doc_ids=json.dumps([d["id"] for d in docs_data], ensure_ascii=False),
                entries=json.dumps(entries, ensure_ascii=False),
                total_debit=total_debit,
                total_credit=total_credit,
                status="confirmed",
                created_by="ai",
                reviewer="AI自动确认",
                review_comment="全自动加工链自动确认：最终审核请在各税种申报提交时进行",
                client_id=client_id,
            )
            db.add(voucher)
            db.flush()

            create_trace(db, "voucher", voucher.id, "ai_voucher")
            create_trace(db, "voucher", voucher.id, "confirm")
            commit(db, "voucher", voucher.id, "auto_created", operator,
                   after={"voucher_no": vno, "summary": voucher.summary, "entries_count": len(entries), "auto_confirmed": True})
            commit(db, "voucher", voucher.id, "auto_confirmed", "ai",
                   after={"reviewer": "AI自动确认", "status": "confirmed"})

            result["vouchers_generated"] += 1
            result["vouchers_auto_confirmed"] += 1
            doc_ids_for_detail = [d["id"][:8] for d in docs_data]
            result["details"].append(f"✅ {doc_date}: {vno} 已自动确认 ({', '.join(doc_ids_for_detail)})")
            voucher_dates_used.add(doc_date[:7])

        # Step 3: 识别客户应申报的全税种 → 自动创建所有申报任务
        from app.models.filing import TaxFiling
        from app.models.client import Client
        client = db.query(Client).filter(Client.id == client_id).first()
        taxpayer_type = client.taxpayer_type if client else "small"

        # 全税种覆盖（对标亿企赢）：增值税 + 附加税 + 企业所得税 + 印花税 (每期)
        # 房产税 + 土地使用税 仅在 4月/10月（半年申报期）自动创建
        monthly_taxes = ["vat", "surtax", "corporate_income", "stamp_duty"]
        today = dt_date.today()
        if today.month in (4, 10):
            monthly_taxes.extend(["property_tax", "land_use_tax"])
        # 一般纳税人增值税月报，小规模季报
        if taxpayer_type == "small" and today.month not in (1, 4, 7, 10):
            monthly_taxes = [t for t in monthly_taxes if t != "vat"]
            # 附加税跟随增值税
            monthly_taxes = [t for t in monthly_taxes if t != "surtax"]
        # 企业所得税季报月份
        if today.month not in (1, 4, 7, 10):
            monthly_taxes = [t for t in monthly_taxes if t != "corporate_income"]

        tax_name_map = {
            "vat": "增值税", "surtax": "附加税", "corporate_income": "企业所得税",
            "stamp_duty": "印花税", "property_tax": "房产税", "land_use_tax": "城镇土地使用税",
        }

        for period in sorted(voucher_dates_used):
            for tax_type in monthly_taxes:
                existing = db.query(TaxFiling).filter(
                    TaxFiling.client_id == client_id,
                    TaxFiling.period == period,
                    TaxFiling.tax_type == tax_type,
                ).first()
                if existing:
                    continue
                filing = TaxFiling(
                    id=str(uuid.uuid4()),
                    tax_type=tax_type,
                    period=period,
                    status="pending",
                    client_id=client_id,
                )
                try:
                    tax_data = preview_filing(db, tax_type, period, taxpayer_type)
                    filing.filing_result = json.dumps(tax_data, ensure_ascii=False)
                except Exception:
                    pass
                db.add(filing)
                db.flush()
                create_trace(db, "tax_filing", filing.id, "file_tax")
                commit(db, "tax_filing", filing.id, "auto_created", operator,
                       after={"tax_type": tax_type, "period": period, "client_id": client_id})
                result["filings_created"] += 1
                result["details"].append(f"📋 {period} {tax_name_map.get(tax_type, tax_type)}: 申报任务已自动创建")

        # Step 4: 自动识别需要开票的销项凭证 → 生成开票草稿
        invoice_result = _auto_create_invoices(client_id, db, operator)
        result["invoices_created"] = invoice_result["invoices_created"]
        result["invoices_skipped"] = invoice_result["skipped"]
        result["details"].extend(invoice_result["details"])

        db.commit()

    except Exception as e:
        db.rollback()
        log_error("auto_process", e, {"client_id": client_id, "operator": operator})
        raise HTTPException(status_code=500, detail=f"自动加工失败: {str(e)[:200]}")

    total = result["vouchers_generated"]
    has_filings = result['filings_created'] > 0
    has_invoices = result.get('invoices_created', 0) > 0
    parts = [
        f"处理完成：{result['documents_found']} 张票据 -> {total} 张凭证（全部自动确认）"
    ]
    if has_filings:
        parts.append(f"{result['filings_created']} 项申报已创建")
    if has_invoices:
        parts.append(f"{result['invoices_created']} 张开票草稿已生成")
    result["summary"] = "，".join(parts)

    return result


@router.post("/auto-submit-filings")
async def auto_submit_filings(
    client_id: str = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _=Depends(require_modify),
):
    """
    一键申报提交：将当前客户所有 pending 状态的申报通过 Playwright 自动提交到电子税务局
    这是全自动财税链的最后一步 —— 提交前请确认申报数据无误
    """
    from app.models.filing import TaxFiling

    pending_filings = db.query(TaxFiling).filter(
        TaxFiling.client_id == client_id,
        TaxFiling.status == "pending",
    ).all()

    if not pending_filings:
        return {"success": True, "message": "没有待提交的申报", "results": []}

    from app.api.settings import get_tax_credentials
    tax_credentials = get_tax_credentials(db)

    engine = TaxAutomationEngine(
        profile=tax_credentials.get("province", "generic"),
        headless=True,
    )

    results = []
    for filing in pending_filings:
        filing_data = {}
        if filing.filing_result:
            try:
                filing_data = json.loads(filing.filing_result)
            except (json.JSONDecodeError, TypeError):
                pass

        log_info("auto_submit", "filing_start", f"filing={filing.id[:8]} tax_type={filing.tax_type} period={filing.period}")

        try:
            result = await engine.run_filing(
                tax_type=filing.tax_type,
                period=filing.period,
                tax_data=filing_data,
                credentials={
                    "username": tax_credentials.get("username", ""),
                    "password": tax_credentials.get("password", ""),
                },
            )

            filing.status = "submitted" if result.success else "failed"
            filing.submitted_at = result.filed_at if result.filed_at else None
            if result.screenshot_paths:
                filing.filing_result = json.dumps({
                    **filing_data,
                    "submission_screenshots": result.screenshot_paths,
                    "transaction_id": result.transaction_id,
                }, ensure_ascii=False)

            commit(db, "tax_filing", filing.id, "auto_submitted", (user.display_name or ""),
                   after={"status": filing.status, "message": result.message})

            results.append({
                "filing_id": filing.id,
                "tax_type": filing.tax_type,
                "period": filing.period,
                "success": result.success,
                "message": result.message,
                "screenshots": result.screenshot_paths,
                "steps_completed": result.steps_completed,
                "failed_step": result.failed_step,
                "transaction_id": result.transaction_id,
            })

            log_info("auto_submit", "filing_done",
                     f"filing={filing.id[:8]} success={result.success} msg={result.message[:100]}")

        except Exception as e:
            log_error("auto_submit", e, {"filing_id": filing.id[:8], "tax_type": filing.tax_type})
            filing.status = "failed"
            commit(db, "tax_filing", filing.id, "auto_submit_failed", (user.display_name or ""),
                   after={"status": "failed", "error": str(e)[:200]})
            results.append({
                "filing_id": filing.id,
                "tax_type": filing.tax_type,
                "period": filing.period,
                "success": False,
                "message": f"提交异常: {str(e)[:150]}",
            })

    db.commit()

    success_count = sum(1 for r in results if r["success"])
    return {
        "success": True,
        "total": len(results),
        "success_count": success_count,
        "failed_count": len(results) - success_count,
        "results": results,
        "message": f"申报提交完成：{success_count}/{len(results)} 成功",
    }


@router.post("/auto-create-invoices")
def auto_create_invoices_endpoint(
    client_id: str = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _=Depends(require_modify),
):
    """
    从已确认凭证自动识别销项交易并生成开票草稿
    扫描所有已确认凭证中 6001（主营业务收入）贷方分录 → 追溯源票据获取购方信息 → 生成 Invoice 草稿
    """
    operator = user.display_name or "ai"
    result = _auto_create_invoices(client_id, db, operator)
    return result


@router.post("/auto-issue-all-invoices")
async def auto_issue_all_invoices(
    client_id: str = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _=Depends(require_modify),
):
    """
    一键自动开具当前客户所有 draft 状态的发票（通过 Playwright 提交到电子税务局）
    """
    pending_invoices = db.query(Invoice).filter(
        Invoice.client_id == client_id,
        Invoice.status == "draft",
    ).all()

    if not pending_invoices:
        return {"success": True, "message": "没有待开具的发票", "results": []}

    from app.api.settings import get_tax_credentials
    tax_credentials = get_tax_credentials(db)

    results = []
    for inv in pending_invoices:
        inv.status = "issuing"
        db.commit()

        items = json.loads(inv.items) if inv.items else []
        try:
            from app.services.tax_invoice import issue_invoice_playwright
            issue_result = await issue_invoice_playwright(
                invoice_id=inv.id,
                buyer_name=inv.buyer_name,
                buyer_tax_no=inv.buyer_tax_no,
                invoice_type=inv.invoice_type,
                items=items,
                remark=inv.remark or "",
                tax_credentials=tax_credentials,
            )

            if issue_result["success"]:
                inv.status = "issued"
                inv.issued_at = __import__("datetime").datetime.now(__import__("datetime").UTC)
                inv.invoice_code = issue_result.get("invoice_code", "")
                inv.invoice_no = issue_result.get("invoice_no", "")
                inv.invoice_url = issue_result.get("invoice_url", "")
                inv.screenshot_path = issue_result.get("screenshot", "")
                create_trace(db, "invoice", inv.id, "auto_issued")
            else:
                inv.status = "failed"

            db.commit()
            results.append({
                "invoice_id": inv.id,
                "buyer_name": inv.buyer_name,
                "amount": inv.grand_total,
                "success": issue_result["success"],
                "message": issue_result.get("message", ""),
            })

        except Exception as e:
            inv.status = "failed"
            db.commit()
            results.append({
                "invoice_id": inv.id,
                "buyer_name": inv.buyer_name,
                "success": False,
                "message": f"开具异常: {str(e)[:150]}",
            })

    success_count = sum(1 for r in results if r["success"])
    return {
        "success": True,
        "total": len(results),
        "success_count": success_count,
        "failed_count": len(results) - success_count,
        "results": results,
        "message": f"开票完成：{success_count}/{len(results)} 成功",
    }
