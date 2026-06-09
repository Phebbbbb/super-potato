import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.background import BackgroundScheduler
from app.db import init_db
from app.config import settings
from app.services.backup import backup_database
from app.services.tax_announcement import refresh_announcements
from app.middleware.rate_limit import rate_limit_middleware


def _scheduled_announcement_refresh():
    """定时刷新国家税务总局公告并生成通知（调度器线程需独立 session）"""
    from app.db import SessionLocal
    from app.services.notification_service import create_notification
    db = SessionLocal()
    try:
        count = refresh_announcements(db)
        if count > 0:
            print(f"[调度] 公告刷新完成，新增 {count} 条")
            create_notification(db, "announcement", f"国家税务总局发布了 {count} 条新政策公告",
                                message=f"本次共更新 {count} 条政策公告，请及时查阅", link="/operation-log")
            db.commit()
    except Exception as e:
        print(f"[调度] 公告刷新失败: {e}")
        db.rollback()
    finally:
        db.close()


def _generate_deadline_notifications():
    """每日检查即将到期的申报截止日"""
    from app.db import SessionLocal
    from app.services.notification_service import create_notification
    from datetime import date, timedelta
    db = SessionLocal()
    try:
        today = date.today()
        current_month = f"{today.year}-{today.month:02d}"
        # 查下月15号
        if today.month == 12:
            deadline = date(today.year + 1, 1, 15)
        else:
            deadline = date(today.year, today.month + 1, 15)
        # 周末顺延
        while deadline.weekday() >= 5:
            deadline += timedelta(days=1)
        days_left = (deadline - today).days
        if 0 <= days_left <= 7:
            create_notification(db, "deadline",
                                title=f"申报截止日提醒：{current_month} 期申报将于 {deadline.isoformat()} 截止",
                                message=f"距离申报截止仅剩 {days_left} 天，请尽快完成申报",
                                link="/tax-filings")
            db.commit()
    except Exception as e:
        print(f"[调度] 截止日通知生成失败: {e}")
        db.rollback()
    finally:
        db.close()


def _auto_month_end_closing():
    """月末自动关账：对全部客户执行折旧 + 摊销（全自动财税机器人）"""
    from app.db import SessionLocal
    from app.services.fixed_asset import run_depreciation_for_all_clients
    from app.services.notification_service import create_notification
    from datetime import date as dt_date
    today = dt_date.today()
    # 只在每月最后一天执行
    import calendar
    last_day = calendar.monthrange(today.year, today.month)[1]
    if today.day != last_day:
        return
    db = SessionLocal()
    try:
        results = run_depreciation_for_all_clients(db, today)
        total = results.get("total_depreciation", 0)
        count = results.get("vouchers_created", 0)
        if count > 0:
            create_notification(db, "rpa", f"月末自动关账完成：{count} 项资产折旧，合计 ¥{total:,.2f}",
                                message=f"{today.year}年{today.month}月自动关账已执行", link="/fixed-assets")
            db.commit()
            print(f"[调度] 月末自动关账完成 — {count} 项折旧, 合计 ¥{total:,.2f}")
    except Exception as e:
        print(f"[调度] 月末自动关账失败: {e}")
        db.rollback()
    finally:
        db.close()


def _auto_submit_due_filings():
    """到期自动申报：检查3天内截止的待申报任务，自动提交（全自动财税机器人）"""
    from app.db import SessionLocal
    from app.models.filing import TaxFiling
    from app.models.client import Client
    from app.services.notification_service import create_notification
    from datetime import date as dt_date, timedelta
    db = SessionLocal()
    try:
        today = dt_date.today()
        deadline = today + timedelta(days=3)
        # 找到所有 pending 状态的申报
        pending = db.query(TaxFiling).filter(TaxFiling.status == "pending").all()
        submitted = 0
        for f in pending:
            if not f.client_id:
                continue
            client = db.query(Client).filter(Client.id == f.client_id).first()
            if not client:
                continue
            # 获取税局凭据
            from app.api.settings import get_tax_credentials
            creds = get_tax_credentials(db)
            if not creds.get("username"):
                continue  # 未配置凭据，跳过
            # 自动提交
            try:
                import asyncio
                from app.services.tax_automation import TaxAutomationEngine
                engine = TaxAutomationEngine(profile=creds.get("province", "generic"), headless=True)
                filing_data = {}
                if f.filing_result:
                    try:
                        filing_data = __import__("json").loads(f.filing_result)
                    except Exception:
                        pass
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(
                    engine.run_filing(
                        tax_type=f.tax_type,
                        period=f.period,
                        tax_data=filing_data,
                        credentials={"username": creds.get("username", ""), "password": creds.get("password", "")},
                    )
                )
                loop.close()
                if result.success:
                    f.status = "submitted"
                    submitted += 1
                else:
                    f.status = "auto_submit_failed"
            except Exception as e:
                f.status = "auto_submit_failed"
                print(f"[调度] 自动申报失败: {f.id[:8]} {f.tax_type} {f.period} — {e}")
        db.commit()
        if submitted > 0:
            create_notification(db, "rpa", f"自动申报完成：{submitted} 项已提交",
                                message=f"截止日 {deadline.isoformat()}，已自动提交 {submitted} 项申报", link="/tax-filings")
            db.commit()
        print(f"[调度] 自动申报检查完成 — 提交 {submitted} 项")
    except Exception as e:
        print(f"[调度] 自动申报失败: {e}")
        db.rollback()
    finally:
        db.close()


# ===== 定时任务调度器 =====
scheduler = BackgroundScheduler()
scheduler.add_job(backup_database, "cron", hour=2, minute=0, id="daily_backup")
scheduler.add_job(_scheduled_announcement_refresh, "interval", hours=2, id="refresh_announcements")
scheduler.add_job(_generate_deadline_notifications, "cron", hour=9, minute=0, id="deadline_notifications")
def _auto_scan_all_clients():
    """全客户自动巡检：扫描所有客户未处理的票据，自动跑全加工链（全自动财税机器人核心）"""
    from app.db import SessionLocal
    from app.models.client import Client
    from app.models.document import OriginalDocument
    from app.models.voucher import AccountingVoucher
    from app.services.notification_service import create_notification
    import json as _json

    db = SessionLocal()
    try:
        clients = db.query(Client).filter(Client.is_active == True).all()
        total_processed = 0
        for client in clients:
            # 检查是否有 OCR 完成但未生成凭证的票据
            existing_doc_ids = set()
            vouchers = db.query(AccountingVoucher.source_doc_ids).filter(
                AccountingVoucher.client_id == client.id
            ).all()
            for (src,) in vouchers:
                if src:
                    try:
                        existing_doc_ids.update(_json.loads(src))
                    except Exception:
                        pass

            pending = db.query(OriginalDocument).filter(
                OriginalDocument.client_id == client.id,
                OriginalDocument.ocr_status == "done",
                ~OriginalDocument.id.in_(existing_doc_ids) if existing_doc_ids else True,
            ).count()

            if pending == 0:
                continue

            # 自动加工
            try:
                # 调用 auto-process（内联逻辑，避免循环导入）
                existing_vouchers = db.query(AccountingVoucher.source_doc_ids).filter(
                    AccountingVoucher.client_id == client.id
                ).all()
                used_ids = set()
                for (src,) in existing_vouchers:
                    if src:
                        try:
                            used_ids.update(_json.loads(src))
                        except Exception:
                            pass

                pending_docs = db.query(OriginalDocument).filter(
                    OriginalDocument.client_id == client.id,
                    OriginalDocument.ocr_status == "done",
                    ~OriginalDocument.id.in_(used_ids) if used_ids else True,
                ).all()

                if not pending_docs:
                    continue

                # 批量加工
                from app.api.rpa_trigger import _auto_create_invoices
                from app.services.voucher_service import generate_voucher_no, validate_balance, build_entries_from_documents
                from app.models.filing import TaxFiling
                from app.services.qr_service import create_trace as _create_trace
                from app.services.version_control import commit as _commit
                from app.services.tax_service import preview_filing as _preview_filing
                from datetime import date as _dt_date
                import uuid as _uuid

                # 按日期分组
                docs_by_date: dict = {}
                for d in pending_docs:
                    ocr = _json.loads(d.ocr_structured) if d.ocr_structured else {}
                    d_date = ocr.get("date", f"{_dt_date.today()}")
                    docs_by_date.setdefault(d_date, []).append(d)

                for doc_date, docs_group in sorted(docs_by_date.items()):
                    docs_data = [{"id": d.id, "doc_type": d.doc_type, "file_name": d.file_name,
                                  "ocr_structured": _json.loads(d.ocr_structured) if d.ocr_structured else {}} for d in docs_group]
                    entries = build_entries_from_documents(db, docs_data, "自动生成")
                    balanced, td, tc = validate_balance(entries)
                    if not balanced and entries:
                        diff = round(td - tc, 2)
                        if diff > 0:
                            entries[-1]["credit"] = round((entries[-1].get("credit", 0) or 0) + diff, 2)
                        else:
                            entries[-1]["debit"] = round((entries[-1].get("debit", 0) or 0) - diff, 2)

                    v_date = _dt_date.fromisoformat(doc_date)
                    vno = generate_voucher_no(db, v_date)
                    voucher = AccountingVoucher(
                        id=str(_uuid.uuid4()), voucher_no=vno, voucher_date=v_date,
                        summary=f"自动生成凭证({doc_date})",
                        source_doc_ids=_json.dumps([d["id"] for d in docs_data], ensure_ascii=False),
                        entries=_json.dumps(entries, ensure_ascii=False),
                        total_debit=td, total_credit=tc, status="confirmed", created_by="ai",
                        reviewer="AI自动巡检", review_comment="全客户自动巡检确认",
                        client_id=client.id,
                    )
                    db.add(voucher)
                    total_processed += 1

                # 创建申报
                client_obj = db.query(Client).filter(Client.id == client.id).first()
                tp = client_obj.taxpayer_type if client_obj else "small"
                today = _dt_date.today()
                taxes = ["vat", "surtax", "corporate_income", "stamp_duty"]
                if tp == "small" and today.month not in (1, 4, 7, 10):
                    taxes = ["corporate_income", "stamp_duty"]
                if today.month not in (1, 4, 7, 10):
                    taxes = [t for t in taxes if t not in ("vat", "surtax")]
                if today.month not in (1, 4, 7, 10):
                    taxes = [t for t in taxes if t != "corporate_income"]

                period = f"{today.year}-{today.month:02d}"
                for tax_type in taxes:
                    existing = db.query(TaxFiling).filter(
                        TaxFiling.client_id == client.id, TaxFiling.period == period, TaxFiling.tax_type == tax_type
                    ).first()
                    if not existing:
                        filing = TaxFiling(id=str(_uuid.uuid4()), tax_type=tax_type, period=period,
                                           status="pending", client_id=client.id)
                        db.add(filing)

                # 自动创建开票
                _auto_create_invoices(client.id, db, "auto_scan")

                db.commit()
            except Exception as e:
                print(f"[调度] 客户 {client.id[:8]} 自动加工失败: {e}")
                try:
                    db.rollback()
                except Exception:
                    pass

        if total_processed > 0:
            print(f"[调度] 全客户自动巡检完成 — {total_processed} 张凭证, {len(clients)} 个客户")
    except Exception as e:
        print(f"[调度] 全客户自动巡检失败: {e}")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


def _daily_risk_scan():
    """每日税务风控巡检：扫描所有客户，检测异常（税负率异常、零申报、未申报等）"""
    from app.db import SessionLocal
    from app.models.client import Client
    from app.models.filing import TaxFiling
    from app.services.notification_service import create_notification
    from app.services.report_service import dashboard_data
    from datetime import date as _dt_date

    db = SessionLocal()
    try:
        clients = db.query(Client).filter(Client.is_active == True).all()
        alerts = []
        for client in clients:
            dash = dashboard_data(db, client.id)
            if not dash or not dash.get("current_month"):
                continue
            cm = dash["current_month"]
            ops = dash.get("operations", {})

            # 检查1: 待申报逾期
            if ops.get("pending_filings", 0) > 0:
                alerts.append(f"⚠️ {client.name}: {ops['pending_filings']} 项待申报")

            # 检查2: 增值税税负率异常 (<1% 或 >10%)
            if cm.get("revenue", 0) > 0 and cm.get("vat_payable", 0) > 0:
                burden = cm["vat_payable"] / cm["revenue"] * 100
                if burden < 1:
                    alerts.append(f"⚠️ {client.name}: 增值税税负率偏低 ({burden:.1f}%)")
                elif burden > 10:
                    alerts.append(f"⚠️ {client.name}: 增值税税负率偏高 ({burden:.1f}%)")

            # 检查3: 连续零申报
            if cm.get("revenue", 0) == 0 and cm.get("cost", 0) == 0:
                filings_count = db.query(TaxFiling).filter(
                    TaxFiling.client_id == client.id, TaxFiling.status == "success"
                ).count()
                if filings_count >= 3:
                    alerts.append(f"⚠️ {client.name}: 连续 {filings_count} 期零申报，请关注")

        if alerts:
            for alert in alerts[:10]:
                create_notification(db, "risk", alert, message="税务风控自动巡检", link="/tax-risk")
            db.commit()
            print(f"[调度] 风控巡检完成 — {len(alerts)} 条告警")
    except Exception as e:
        print(f"[调度] 风控巡检失败: {e}")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


def _daily_contract_expiry_check():
    """每日检查合同和客户服务到期（合同到期和客户服务到期提醒）"""
    from app.db import SessionLocal
    from app.models.contract import Contract
    from app.models.client import Client
    from app.services.notification_service import create_notification
    from datetime import date as dt_date, timedelta

    db = SessionLocal()
    try:
        today = dt_date.today()
        warning_date = today + timedelta(days=30)

        # 检查合同到期
        expiring_contracts = db.query(Contract).filter(
            Contract.status == "active",
            Contract.end_date <= warning_date.isoformat(),
            Contract.end_date >= today.isoformat(),
        ).all()

        for c in expiring_contracts:
            days = (dt_date.fromisoformat(c.end_date) - today).days if c.end_date else 0
            client = db.query(Client).filter(Client.id == c.client_id).first()
            client_name = client.name if client else "未知客户"
            create_notification(db, "deadline",
                                title=f"合同即将到期：{c.contract_name}",
                                message=f"{client_name} 的合同「{c.contract_name}」将于 {c.end_date} 到期（剩余 {days} 天）",
                                link="/contracts")
        if expiring_contracts:
            db.commit()

        # 检查客户服务到期
        expiring_clients = db.query(Client).filter(
            Client.is_active == True,
            Client.service_end.isnot(None),
            Client.service_end <= warning_date.isoformat(),
            Client.service_end >= today.isoformat(),
        ).all()

        for cl in expiring_clients:
            days = (dt_date.fromisoformat(cl.service_end) - today).days if cl.service_end else 0
            create_notification(db, "deadline",
                                title=f"客户服务即将到期：{cl.name}",
                                message=f"客户「{cl.name}」服务期将于 {cl.service_end} 到期（剩余 {days} 天）",
                                link="/clients")
        if expiring_clients:
            db.commit()

        total = len(expiring_contracts) + len(expiring_clients)
        if total > 0:
            print(f"[调度] 合同/客户到期检查完成 — {total} 项即将到期")
    except Exception as e:
        print(f"[调度] 到期检查失败: {e}")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


scheduler.add_job(_daily_contract_expiry_check, "cron", hour=8, minute=30, id="contract_expiry_check")
scheduler.add_job(_auto_month_end_closing, "cron", hour=22, minute=0, id="month_end_closing")
scheduler.add_job(_auto_submit_due_filings, "cron", hour=8, minute=0, id="auto_submit_due_filings")
scheduler.add_job(_auto_scan_all_clients, "interval", minutes=30, id="auto_scan_clients")
scheduler.add_job(_daily_risk_scan, "cron", hour=7, minute=0, id="daily_risk_scan")
scheduler.start()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    # 检查 Playwright 是否已安装
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        print("[系统] Playwright 就绪 — 自动化开票/申报引擎可用")
    except ImportError:
        print("[系统] ⚠️ Playwright 未安装 — 自动化开票/申报不可用，请执行: pip install playwright && playwright install chromium")
    except Exception as e:
        print(f"[系统] ⚠️ Playwright 异常 — {str(e)[:100]}")
    yield
    try:
        scheduler.shutdown()
    except Exception:
        pass


app = FastAPI(title=settings.app_name, version="2.1.0", lifespan=lifespan)

# 速率限制（最先执行）
app.middleware("http")(rate_limit_middleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(settings.upload_dir, exist_ok=True)
os.makedirs(settings.qrcode_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")
app.mount("/qrcodes", StaticFiles(directory=settings.qrcode_dir), name="qrcodes")


@app.get("/api/health")
def health_check():
    return {"status": "ok", "app": settings.app_name, "version": "2.0.0"}


# 注册路由
from app.api import rpa, documents, vouchers, filings, accounts, qr, reports, feedback, rpa_trigger
from app.api import settings as settings_api
from app.api import auth, clients, users, payroll, bank, field_tasks, agent, tax_calendar, audit, tax_automation, invoices, backup, version_control, announcements, notifications, fixed_assets, contracts, batch_automation, annual_reports, tax_settlement, invoice_verify, period_close, precheck

app.include_router(rpa.router, prefix="/api/rpa", tags=["RPA对接"])
app.include_router(rpa_trigger.router, prefix="/api/rpa", tags=["RPA触发"])
app.include_router(documents.router, prefix="/api/documents", tags=["原始凭证"])
app.include_router(vouchers.router, prefix="/api/vouchers", tags=["记账凭证"])
app.include_router(filings.router, prefix="/api/filings", tags=["纳税申报"])
app.include_router(accounts.router, prefix="/api/accounts", tags=["会计科目"])
app.include_router(qr.router, prefix="/api/qr", tags=["QR追溯"])
app.include_router(reports.router, prefix="/api/reports", tags=["财务报表"])
app.include_router(feedback.router, prefix="/api/feedback", tags=["人工反馈修正"])
app.include_router(settings_api.router, prefix="/api/settings", tags=["系统配置"])
app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(clients.router, prefix="/api/clients", tags=["客户管理"])
app.include_router(users.router, prefix="/api/users", tags=["用户管理"])
app.include_router(payroll.router, prefix="/api/payroll", tags=["薪酬管理"])
app.include_router(bank.router, prefix="/api/bank", tags=["银行对账"])
app.include_router(field_tasks.router, prefix="/api/field-tasks", tags=["外勤任务"])
app.include_router(agent.router, prefix="/api/agent", tags=["AI税务顾问"])
app.include_router(tax_calendar.router, prefix="/api/tax", tags=["税务风控"])
app.include_router(audit.router, prefix="/api/audit", tags=["内审中心"])
app.include_router(tax_automation.router, prefix="/api/tax-automation", tags=["自动申报引擎"])
app.include_router(invoices.router, prefix="/api/invoices", tags=["数电票开票"])
app.include_router(backup.router, prefix="/api/system", tags=["系统运维"])
app.include_router(version_control.router, prefix="/api/version", tags=["版本控制"])
app.include_router(announcements.router, prefix="/api/announcements", tags=["官方公告"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["消息通知"])
app.include_router(fixed_assets.router, prefix="/api/fixed-assets", tags=["固定资产"])
app.include_router(contracts.router, prefix="/api/contracts", tags=["合同管理"])
app.include_router(batch_automation.router, prefix="/api/batch", tags=["批量自动化"])
app.include_router(annual_reports.router, prefix="/api/annual-reports", tags=["工商年报"])
app.include_router(tax_settlement.router, prefix="/api/tax", tags=["汇算清缴"])
app.include_router(invoice_verify.router, prefix="/api/invoice-verify", tags=["发票查验"])
app.include_router(period_close.router, prefix="/api/rpa", tags=["一键关账"])
app.include_router(precheck.router, prefix="/api", tags=["预检优化"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
