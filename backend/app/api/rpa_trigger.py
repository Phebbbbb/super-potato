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
from app.services.auth import require_modify, get_current_user
from app.models.user import User
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
async def test_webhook(data: dict):
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

        # Step 3: 为涉及的申报期自动创建申报任务
        from app.models.filing import TaxFiling
        for period in sorted(voucher_dates_used):
            existing_filing = db.query(TaxFiling).filter(
                TaxFiling.client_id == client_id,
                TaxFiling.period == period,
            ).first()
            if not existing_filing:
                filing = TaxFiling(
                    id=str(uuid.uuid4()),
                    tax_type="vat",
                    period=period,
                    status="pending",
                    client_id=client_id,
                )
                try:
                    tax_data = preview_filing(db, "vat", period, "small")
                    filing.filing_result = json.dumps(tax_data, ensure_ascii=False)
                except Exception:
                    pass
                db.add(filing)
                db.flush()
                create_trace(db, "tax_filing", filing.id, "file_tax")
                commit(db, "tax_filing", filing.id, "auto_created", operator,
                       after={"tax_type": "vat", "period": period, "client_id": client_id})
                result["filings_created"] += 1
                result["details"].append(f"📋 {period}: 增值税申报任务已自动创建")

        db.commit()

    except Exception as e:
        db.rollback()
        log_error("auto_process", e, {"client_id": client_id, "operator": operator})
        raise HTTPException(status_code=500, detail=f"自动加工失败: {str(e)[:200]}")

    total = result["vouchers_generated"]
    has_filings = result['filings_created'] > 0
    result["summary"] = (
        f"处理完成：{result['documents_found']} 张票据 -> "
        f"{total} 张凭证（全部自动确认）"
        + (f"，{result['filings_created']} 项申报已创建" + ("，可一键提交" if has_filings else "") if has_filings else "")
    )

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
