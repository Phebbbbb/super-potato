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
    """定时刷新国家税务总局公告（调度器线程需独立 session）"""
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        count = refresh_announcements(db)
        print(f"[调度] 公告刷新完成，新增 {count} 条")
    except Exception as e:
        print(f"[调度] 公告刷新失败: {e}")
    finally:
        db.close()


# ===== 定时任务调度器 =====
scheduler = BackgroundScheduler()
scheduler.add_job(backup_database, "cron", hour=2, minute=0, id="daily_backup")
scheduler.add_job(_scheduled_announcement_refresh, "interval", hours=2, id="refresh_announcements")
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
from app.api import auth, clients, users, payroll, bank, field_tasks, agent, tax_calendar, audit, tax_automation, invoices, backup, version_control, announcements

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
