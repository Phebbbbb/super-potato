"""
并行自动化引擎 — Browser Pool + 任务队列 + 批量执行
核心差异化：多客户并行处理，亿企赢做不到

架构:
  BrowserPool (管理 N 个 browser instance)
    → ParallelFilingEngine (批量申报)
    → ParallelInvoiceEngine (批量开票)
    → BatchJobTracker (进度追踪 + 指标)
"""

import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Callable
from concurrent.futures import ThreadPoolExecutor

from app.services.error_handler import log_error, log_info

# 并发上限（避免触发税局风控）
MAX_CONCURRENT_BROWSERS = int(os.getenv("AUTOMATION_POOL_SIZE", "3"))
BROWSER_IDLE_TIMEOUT = int(os.getenv("BROWSER_IDLE_SECONDS", "300"))  # 5 分钟空闲回收
SCREENSHOT_DIR = Path("screenshots/pool")


@dataclass
class BatchTask:
    """单个批处理任务"""
    task_id: str
    client_id: str
    client_name: str
    task_type: str  # filing / invoice
    tax_type: str = ""  # vat / corporate_income / etc (for filing)
    invoice_id: str = ""  # (for invoice)
    priority: int = 5  # 1-10, 1=最高
    payload: dict = field(default_factory=dict)
    status: str = "queued"  # queued / running / success / failed
    result: dict = field(default_factory=dict)
    retries: int = 0
    max_retries: int = 2
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    error: str = ""


@dataclass
class BatchJob:
    """批量作业"""
    job_id: str
    job_type: str  # batch_filing / batch_invoice
    tasks: list[BatchTask] = field(default_factory=list)
    status: str = "created"  # created / running / completed / partial_failure / failed
    total: int = 0
    completed: int = 0
    success: int = 0
    failed: int = 0
    created_at: str = ""
    completed_at: str = ""
    progress_callback: Optional[Callable] = None

    def progress_pct(self) -> float:
        if self.total == 0:
            return 0
        return self.completed / self.total * 100

    def summary(self) -> dict:
        return {
            "job_id": self.job_id, "job_type": self.job_type, "status": self.status,
            "total": self.total, "completed": self.completed,
            "success": self.success, "failed": self.failed,
            "progress_pct": round(self.progress_pct(), 1),
            "created_at": self.created_at, "completed_at": self.completed_at,
        }


class BrowserPool:
    """
    浏览器实例池 — 复用 browser context 避免反复登录

    用法:
        pool = BrowserPool(pool_size=3)
        async with pool.acquire(profile="beijing", credentials={...}) as ctx:
            await ctx.page.goto(...)
            # ... automation steps ...
    """

    def __init__(self, pool_size: int = None, headless: bool = True):
        self.pool_size = pool_size or MAX_CONCURRENT_BROWSERS
        self.headless = headless
        self._semaphore = asyncio.Semaphore(self.pool_size)
        self._browsers: dict[str, dict] = {}  # keyed by profile
        self._playwright = None
        self._initialized = False

    async def _ensure_playwright(self):
        if not self._initialized:
            from playwright.async_api import async_playwright
            self._pw = await async_playwright().start()
            self._initialized = True

    async def acquire(self, profile: str = "generic", credentials: dict = None):
        """获取一个浏览器上下文（自动登录/预热）"""
        await self._ensure_playwright()
        await self._semaphore.acquire()

        key = f"{profile}:{credentials.get('username', 'anonymous') if credentials else 'anonymous'}"
        now = time.time()

        # 复用已有实例
        if key in self._browsers:
            entry = self._browsers[key]
            if now - entry["last_used"] < BROWSER_IDLE_TIMEOUT:
                entry["last_used"] = now
                return BrowserContext(entry["page"], entry["browser"], self, key)
            # 过期回收
            await self._recycle(key)

        # 创建新实例
        browser = await self._pw.chromium.launch(headless=self.headless)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080}, locale="zh-CN",
        )
        page = await context.new_page()

        # 预热登录
        if credentials and credentials.get("username"):
            from app.services.tax_automation import TAX_BUREAU_CONFIGS
            bureau = TAX_BUREAU_CONFIGS.get(profile, TAX_BUREAU_CONFIGS.get("generic", {}))
            login_url = bureau.get("login_url", "")
            login_s = bureau.get("login_selectors", {})
            if login_url:
                try:
                    await page.goto(login_url, timeout=30000, wait_until="domcontentloaded")
                    await asyncio.sleep(2)
                    from app.services.tax_automation import TaxAutomationEngine
                    engine = TaxAutomationEngine(profile=profile, headless=self.headless)
                    await engine._safe_fill(page, login_s.get("username", ""), credentials.get("username", ""), "用户名")
                    await engine._safe_fill(page, login_s.get("password", ""), credentials.get("password", ""), "密码")
                    # 不点击登录 — 留给实际任务执行时点击（避免 session 过期）
                except Exception as e:
                    log_error("browser_pool", e, {"profile": profile, "phase": "warmup"})

        entry = {"browser": browser, "context": context, "page": page, "last_used": now}
        self._browsers[key] = entry
        return BrowserContext(page, browser, self, key)

    async def release(self, key: str):
        """释放信号量（不关闭浏览器，保留复用）"""
        if key in self._browsers:
            self._browsers[key]["last_used"] = time.time()
        self._semaphore.release()

    async def _recycle(self, key: str):
        """回收过期浏览器"""
        if key in self._browsers:
            try:
                await self._browsers[key]["browser"].close()
            except Exception:
                pass
            del self._browsers[key]

    async def shutdown(self):
        """关闭所有浏览器"""
        for key in list(self._browsers.keys()):
            await self._recycle(key)
        if self._initialized and self._pw:
            await self._pw.stop()
            self._initialized = False


class BrowserContext:
    """浏览器上下文 — async with 支持"""

    def __init__(self, page, browser, pool: BrowserPool, key: str):
        self.page = page
        self.browser = browser
        self._pool = pool
        self._key = key

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self._pool.release(self._key)


# ============================================================
# 并行批量申报引擎
# ============================================================

class ParallelFilingEngine:
    """
    并行批量申报 — 多客户同时向电子税务局提交申报

    用法:
        engine = ParallelFilingEngine(pool_size=3)
        job = await engine.submit_batch([
            {"client_id": "...", "tax_type": "vat", "period": "2026-06", "tax_data": {...}},
            {"client_id": "...", "tax_type": "vat", "period": "2026-06", "tax_data": {...}},
        ], credentials_map={"client_id": {"username": "...", "password": "..."}})
    """

    def __init__(self, pool_size: int = None, headless: bool = True):
        self.pool = BrowserPool(pool_size=pool_size, headless=headless)
        self._jobs: dict[str, BatchJob] = {}
        self._headless = headless

    async def submit_batch(
        self,
        tasks_data: list[dict],
        credentials_map: dict[str, dict],
        profile: str = "generic",
        on_progress: Callable = None,
    ) -> BatchJob:
        """提交批量申报作业"""
        job = BatchJob(
            job_id=uuid.uuid4().hex[:12],
            job_type="batch_filing",
            total=len(tasks_data),
            created_at=datetime.now().isoformat(),
            status="running",
            progress_callback=on_progress,
        )

        for td in tasks_data:
            task = BatchTask(
                task_id=uuid.uuid4().hex[:10],
                client_id=td.get("client_id", ""),
                client_name=td.get("client_name", ""),
                task_type="filing",
                tax_type=td.get("tax_type", "vat"),
                priority=td.get("priority", 5),
                payload=td,
                created_at=datetime.now().isoformat(),
            )
            job.tasks.append(task)

        self._jobs[job.job_id] = job

        # 按优先级排序
        sorted_tasks = sorted(job.tasks, key=lambda t: t.priority)

        # 并行执行
        sem = asyncio.Semaphore(self.pool.pool_size)

        async def _run_one(task: BatchTask):
            async with sem:
                if task.status in ("success", "failed"):
                    return
                task.status = "running"
                task.started_at = datetime.now().isoformat()

                creds = credentials_map.get(task.client_id, {})
                province = creds.get("province", profile)

                try:
                    from app.services.tax_automation import TaxAutomationEngine
                    engine = TaxAutomationEngine(profile=province, headless=self._headless)
                    result = await engine.run_filing(
                        tax_type=task.tax_type,
                        period=task.payload.get("period", ""),
                        tax_data=task.payload.get("tax_data", {}),
                        credentials=creds,
                    )
                    task.result = {
                        "success": result.success, "message": result.message,
                        "screenshots": result.screenshot_paths,
                        "transaction_id": result.transaction_id,
                    }
                    task.status = "success" if result.success else "failed"
                    if not result.success:
                        task.error = result.message
                except Exception as e:
                    task.status = "failed"
                    task.error = str(e)[:300]
                    log_error("parallel_filing", e, {"client_id": task.client_id, "tax_type": task.tax_type})

                task.completed_at = datetime.now().isoformat()
                job.completed += 1
                if task.status == "success":
                    job.success += 1
                else:
                    job.failed += 1

                if job.progress_callback:
                    try:
                        job.progress_callback(job.summary())
                    except Exception:
                        pass

        await asyncio.gather(*[_run_one(t) for t in sorted_tasks])

        job.status = "completed" if job.failed == 0 else ("partial_failure" if job.success > 0 else "failed")
        job.completed_at = datetime.now().isoformat()
        log_info("parallel_filing", "batch_done", f"job={job.job_id} success={job.success}/{job.total}")

        return job

    def get_job(self, job_id: str) -> Optional[BatchJob]:
        return self._jobs.get(job_id)

    def get_job_summary(self, job_id: str) -> dict:
        job = self._jobs.get(job_id)
        if not job:
            return {"error": "job not found"}
        return job.summary()

    async def shutdown(self):
        await self.pool.shutdown()


# ============================================================
# 并行批量开票引擎
# ============================================================

class ParallelInvoiceEngine:
    """
    并行批量开票 — 多客户同时在电子税务局开票
    """

    def __init__(self, pool_size: int = None, headless: bool = True):
        self.pool = BrowserPool(pool_size=pool_size, headless=headless)
        self._jobs: dict[str, BatchJob] = {}
        self._headless = headless

    async def submit_batch(
        self,
        invoices_data: list[dict],
        credentials_map: dict[str, dict],
        profile: str = "generic",
        on_progress: Callable = None,
    ) -> BatchJob:
        """提交批量开票作业"""
        job = BatchJob(
            job_id=uuid.uuid4().hex[:12],
            job_type="batch_invoice",
            total=len(invoices_data),
            created_at=datetime.now().isoformat(),
            status="running",
            progress_callback=on_progress,
        )

        for inv in invoices_data:
            task = BatchTask(
                task_id=uuid.uuid4().hex[:10],
                client_id=inv.get("client_id", ""),
                client_name=inv.get("client_name", ""),
                task_type="invoice",
                invoice_id=inv.get("invoice_id", ""),
                priority=inv.get("priority", 5),
                payload=inv,
                created_at=datetime.now().isoformat(),
            )
            job.tasks.append(task)

        self._jobs[job.job_id] = job
        sorted_tasks = sorted(job.tasks, key=lambda t: t.priority)
        sem = asyncio.Semaphore(self.pool.pool_size)

        async def _run_one(task: BatchTask):
            async with sem:
                task.status = "running"
                task.started_at = datetime.now().isoformat()

                creds = credentials_map.get(task.client_id, {})
                province = creds.get("province", profile)

                try:
                    from app.services.tax_invoice import issue_invoice_playwright
                    inv = task.payload
                    result = await issue_invoice_playwright(
                        invoice_id=inv.get("invoice_id", ""),
                        buyer_name=inv.get("buyer_name", ""),
                        buyer_tax_no=inv.get("buyer_tax_no", ""),
                        buyer_address=inv.get("buyer_address", ""),
                        buyer_phone=inv.get("buyer_phone", ""),
                        buyer_bank=inv.get("buyer_bank", ""),
                        buyer_account=inv.get("buyer_account", ""),
                        invoice_type=inv.get("invoice_type", "electronic_normal"),
                        items=inv.get("items", []),
                        remark=inv.get("remark", ""),
                        tax_credentials=creds,
                    )
                    task.result = {
                        "success": result.get("success", False),
                        "message": result.get("message", ""),
                        "invoice_code": result.get("invoice_code", ""),
                        "screenshot": result.get("screenshot", ""),
                    }
                    task.status = "success" if result.get("success") else "failed"
                    if not result.get("success"):
                        task.error = result.get("message", "")
                except Exception as e:
                    task.status = "failed"
                    task.error = str(e)[:300]
                    log_error("parallel_invoice", e, {"invoice_id": task.invoice_id})

                task.completed_at = datetime.now().isoformat()
                job.completed += 1
                if task.status == "success":
                    job.success += 1
                else:
                    job.failed += 1

                if job.progress_callback:
                    try:
                        job.progress_callback(job.summary())
                    except Exception:
                        pass

        await asyncio.gather(*[_run_one(t) for t in sorted_tasks])

        job.status = "completed" if job.failed == 0 else ("partial_failure" if job.success > 0 else "failed")
        job.completed_at = datetime.now().isoformat()
        log_info("parallel_invoice", "batch_done", f"job={job.job_id} success={job.success}/{job.total}")

        return job

    def get_job(self, job_id: str) -> Optional[BatchJob]:
        return self._jobs.get(job_id)

    async def shutdown(self):
        await self.pool.shutdown()


# ============================================================
# 全局引擎实例（模块级单例）
# ============================================================

_filing_engine: Optional[ParallelFilingEngine] = None
_invoice_engine: Optional[ParallelInvoiceEngine] = None


def get_filing_engine(pool_size: int = None, headless: bool = True) -> ParallelFilingEngine:
    global _filing_engine
    if _filing_engine is None:
        _filing_engine = ParallelFilingEngine(pool_size=pool_size, headless=headless)
    return _filing_engine


def get_invoice_engine(pool_size: int = None, headless: bool = True) -> ParallelInvoiceEngine:
    global _invoice_engine
    if _invoice_engine is None:
        _invoice_engine = ParallelInvoiceEngine(pool_size=pool_size, headless=headless)
    return _invoice_engine
