"""Playwright 通用工具 v4 — tenacity重试 + 熔断器 + loguru结构化日志 + 多策略选择器"""

import asyncio
import random
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable, Awaitable

from loguru import logger
from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception_type, before_sleep_log,
)

SCREENSHOT_DIR = Path("screenshots")


# ============================================================
# 异常类型
# ============================================================

class NeedHumanReview(Exception):
    """验证码或不可自动处理页面，需人工介入"""
    def __init__(self, message: str, screenshot: str = ""):
        self.message = message
        self.screenshot = screenshot
        super().__init__(message)


class SelectorExhausted(Exception):
    """所有选择器链均失败"""
    pass


class CircuitBreakerOpen(Exception):
    """熔断器已打开，拒绝请求"""
    pass


# ============================================================
# 熔断器 — 基于 Netflix Hystrix 模式
# ============================================================

class CircuitBreaker:
    """熔断器 — 防止对故障服务持续发起请求

    三态: CLOSED(正常) → OPEN(熔断) → HALF_OPEN(探测)

    用法:
        cb = CircuitBreaker("tax_bureau", failure_threshold=5, recovery_timeout=60)
        async with cb:
            result = await call_tax_bureau_api()
    """

    def __init__(self, name: str, failure_threshold: int = 5, recovery_timeout: float = 60):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._last_failure_time: float = 0
        self._state = "CLOSED"  # CLOSED / OPEN / HALF_OPEN

    @property
    def is_open(self) -> bool:
        if self._state == "CLOSED":
            return False
        if self._state == "HALF_OPEN":
            return False
        # OPEN — 检查恢复超时
        if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
            self._state = "HALF_OPEN"
            logger.info(f"[熔断器:{self.name}] OPEN → HALF_OPEN (探测中)")
            return False
        return True

    def success(self):
        if self._state == "HALF_OPEN":
            self._state = "CLOSED"
            self._failure_count = 0
            logger.info(f"[熔断器:{self.name}] HALF_OPEN → CLOSED (已恢复)")
        elif self._state == "CLOSED":
            self._failure_count = 0

    def failure(self):
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._state == "HALF_OPEN" or self._failure_count >= self.failure_threshold:
            if self._state != "OPEN":
                self._state = "OPEN"
                logger.warning(f"[熔断器:{self.name}] 已熔断 (连续{self._failure_count}次失败，{self.recovery_timeout}s后恢复)")

    async def __aenter__(self):
        if self.is_open:
            raise CircuitBreakerOpen(f"[熔断器:{self.name}] 已熔断，拒绝请求")
        return self

    async def __aexit__(self, exc_type, exc_val, _tb):
        if exc_type is None:
            self.success()
        elif exc_type in (CircuitBreakerOpen,):
            return False  # 重新抛出但不计入失败
        else:
            self.failure()
            return False  # 重新抛出


# 全局熔断器实例
_tax_bureau_cb = CircuitBreaker("tax_bureau", failure_threshold=5, recovery_timeout=120)
_ocr_cb = CircuitBreaker("ocr", failure_threshold=3, recovery_timeout=60)


def get_tax_bureau_cb() -> CircuitBreaker:
    return _tax_bureau_cb


def get_ocr_cb() -> CircuitBreaker:
    return _ocr_cb


# ============================================================
# 截图
# ============================================================

def screenshot_path(prefix: str = "step") -> str:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return str(SCREENSHOT_DIR / f"{prefix}_{ts}.png")


# ============================================================
# 多策略填充（七层回退）— 保留原有逻辑 + loguru日志
# ============================================================

async def safe_fill(page, label: str, value: str, fallback_selectors: list[str] = None):
    """多策略填充输入框"""
    if not value:
        return True

    selectors = [
        f'input[placeholder*="{label}"]',
        f'input[name*="{label}"]',
        f'input[aria-label*="{label}"]',
        f'input[id*="{label}"]',
    ]

    try:
        label_el = page.locator(f'label:has-text("{label}"), .form-label:has-text("{label}")').first
        if await label_el.count() > 0:
            label_for = await label_el.get_attribute("for")
            if label_for:
                selectors.insert(0, f'#{label_for}')
    except Exception:
        pass

    if fallback_selectors:
        selectors.extend(fallback_selectors)
    selectors.append("input:visible:not([type='hidden']):not([type='submit']):not([type='button'])")

    for sel in selectors:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                await el.click()
                await el.fill(str(value))
                await asyncio.sleep(0.3)
                return True
        except Exception:
            continue

    logger.warning(f"[safe_fill] 所有选择器均失败 label={label}")
    return False


# ============================================================
# 多策略点击（十层回退 + JS终极fallback）
# ============================================================

async def safe_click(page, label: str, fallback_selectors: list[str] = None) -> bool:
    """多策略点击按钮"""
    selectors = [
        f'button:has-text("{label}")',
        f'a:has-text("{label}")',
        f'[role="button"]:has-text("{label}")',
        f'input[type="submit"][value*="{label}"]',
        f'button[name*="{label}"]',
        f'.btn:has-text("{label}"), .submit-btn:has-text("{label}"), [class*="submit"]:has-text("{label}")',
    ]
    if fallback_selectors:
        selectors.extend(fallback_selectors)
    selectors.extend([
        f'[title*="{label}"]',
        f'[aria-label*="{label}"]',
        f'span:has-text("{label}")',
        f'div:has-text("{label}"):not(:has(*))',
    ])

    for sel in selectors:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                await el.scroll_into_view_if_needed()
                await el.click()
                await asyncio.sleep(1)
                return True
        except Exception:
            continue

    # JS 终极 fallback
    try:
        await page.evaluate(f'''
            const btns = document.querySelectorAll('button, a, input[type="submit"], [role="button"]');
            for (const b of btns) {{
                if (b.textContent?.includes("{label}") || b.value?.includes("{label}")) {{
                    b.click();
                    return true;
                }}
            }}
            return false;
        ''')
        await asyncio.sleep(1)
        return True
    except Exception:
        pass

    logger.warning(f"[safe_click] 所有策略均失败 label={label}")
    return False


# ============================================================
# 验证码检测
# ============================================================

async def detect_captcha(page) -> bool:
    """检测页面是否出现验证码"""
    captcha_indicators = [
        'img[src*="captcha"]', 'img[src*="verification"]', 'img[src*="code"]',
        'img[id*="captcha"]', 'img[id*="verify"]',
        'input[placeholder*="验证码"]', 'input[name*="captcha"]',
        'input[name*="verifyCode"]', 'input[id*="captcha"]',
        '.captcha', '#captcha', '.verification', '.verify-code',
        '.slider-captcha', '.slide-verify', '.nc_wrapper', '#nc_1_n1z',
        '.captcha_container',
        'input[placeholder*="短信"]',
        'button:has-text("发送验证码")', 'button:has-text("获取验证码")',
        '#tcaptcha_iframe', '.tcaptcha-transform',
        '.geetest_panel', '.geetest_holder',
        'text=请完成验证', 'text=请点击验证', 'text=请拖动滑块',
    ]
    for ind in captcha_indicators:
        try:
            if await page.locator(ind).count() > 0:
                return True
        except Exception:
            pass
    return False


async def detect_anti_bot(page) -> Optional[str]:
    """检测反爬/风控页面"""
    indicators = {
        'frequent': ['text=操作太频繁', 'text=访问过于频繁', 'text=请稍后再试'],
        'blocked': ['text=IP已被限制', 'text=账号已被锁定', 'text=访问被拒绝'],
        'maintenance': ['text=系统维护中', 'text=暂未开放', 'text=不在申报期'],
    }
    for risk_type, selectors in indicators.items():
        for sel in selectors:
            try:
                if await page.locator(sel).count() > 0:
                    logger.warning(f"[反爬检测] {risk_type}: {sel}")
                    return risk_type
            except Exception:
                pass
    return None


# ============================================================
# 重试引擎 — tenacity 驱动
# ============================================================

RETRYABLE_EXCEPTIONS = (
    TimeoutError,
    ConnectionError,
    OSError,
    Exception,  # Playwright 大多数异常可重试
)

NON_RETRYABLE_EXCEPTIONS = (
    NeedHumanReview,
    SelectorExhausted,
    CircuitBreakerOpen,
)


def is_retryable(exception: Exception) -> bool:
    """判断异常是否可重试"""
    if isinstance(exception, NON_RETRYABLE_EXCEPTIONS):
        return False
    return True


async def retry_with_backoff(fn: Callable[..., Awaitable], max_retries: int = 3, base_delay: float = 2):
    """指数退避重试（含随机抖动）— 保留异步接口兼容"""
    for attempt in range(max_retries):
        try:
            return await fn()
        except NON_RETRYABLE_EXCEPTIONS:
            raise
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            jitter = random.uniform(0, base_delay * 0.5)
            delay = base_delay * (2 ** attempt) + jitter
            logger.debug(f"[重试] 第{attempt+1}次失败，{delay:.1f}s后重试: {e}")
            await asyncio.sleep(delay)
    return None


# ============================================================
# 安全导航（含网络空闲等待 + 重试）
# ============================================================

async def safe_goto(page, url: str, timeout: int = 30000, max_retries: int = 3) -> bool:
    """安全导航到 URL"""
    for attempt in range(max_retries):
        try:
            await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            return True
        except Exception as e:
            logger.warning(f"[safe_goto] 尝试{attempt+1}/{max_retries} 失败: {e}")
            if attempt == max_retries - 1:
                return False
            await asyncio.sleep(3 * (attempt + 1))
    return False


# ============================================================
# 等待任一选择器
# ============================================================

async def wait_for_any(page, selectors: list[str], timeout: int = 10000) -> Optional[str]:
    """等待列表中任一选择器出现"""
    for sel in selectors:
        try:
            await page.wait_for_selector(sel, timeout=timeout, state="visible")
            return sel
        except Exception:
            continue
    return None


# ============================================================
# 调试快照
# ============================================================

async def save_debug_snapshot(page, prefix: str = "debug") -> str:
    """保存截图 + HTML 源码"""
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ss_path = str(SCREENSHOT_DIR / f"{prefix}_{ts}.png")
    html_path = str(SCREENSHOT_DIR / f"{prefix}_{ts}.html")

    try:
        await page.screenshot(path=ss_path, full_page=True)
    except Exception:
        ss_path = ""

    try:
        html = await page.content()
        Path(html_path).write_text(html, encoding="utf-8")
    except Exception:
        pass

    return ss_path


# ============================================================
# 带熔断器的 API 调用包装器
# ============================================================

async def call_with_circuit_breaker(
    fn: Callable[..., Awaitable],
    cb: CircuitBreaker,
    fallback: Callable[..., Awaitable] = None,
    *args, **kwargs,
):
    """通过熔断器调用函数，熔断时执行 fallback"""
    try:
        async with cb:
            result = await fn(*args, **kwargs)
            return result
    except CircuitBreakerOpen:
        logger.error(f"[熔断] {cb.name} 已熔断")
        if fallback:
            return await fallback(*args, **kwargs)
        raise


# ============================================================
# 浏览器预热 + 登录（带熔断器）
# ============================================================

async def warmup_and_login(
    page,
    login_url: str,
    credentials: dict,
    login_selectors: dict,
    max_attempts: int = 3,
) -> bool:
    """带索引退避的登录预热"""
    for attempt in range(max_attempts):
        try:
            if not await safe_goto(page, login_url):
                logger.warning(f"[预热] 导航失败 第{attempt+1}次")
                continue

            await asyncio.sleep(2)

            # 检测是否已登录（跳过登录页）
            page_url = page.url.lower()
            if any(kw in page_url for kw in ["dashboard", "home", "main", "portal"]):
                logger.info("[预热] 已登录，跳过")
                return True

            # 填充凭据
            username = credentials.get("username", "")
            password = credentials.get("password", "")
            if username:
                await safe_fill(page, "税号", username, [login_selectors.get("username", "")])
            if password:
                await safe_fill(page, "密码", password, [login_selectors.get("password", "")])

            # 检测验证码
            if await detect_captcha(page):
                ss = await save_debug_snapshot(page, "captcha_login")
                raise NeedHumanReview("登录时检测到验证码", ss)

            # 点击登录
            await safe_click(page, "登录", [login_selectors.get("submit", "")])
            await asyncio.sleep(3)

            # 验证登录成功
            page_url = page.url.lower()
            if any(kw in page_url for kw in ["dashboard", "home", "main", "login/verify"]):
                logger.info("[预热] 登录成功")
                return True

            logger.warning(f"[预热] 登录状态不确定 url={page_url}")
        except NeedHumanReview:
            raise
        except Exception as e:
            logger.warning(f"[预热] 第{attempt+1}次异常: {e}")
            if attempt == max_attempts - 1:
                return False
            await asyncio.sleep(3 * (attempt + 1))

    return False
