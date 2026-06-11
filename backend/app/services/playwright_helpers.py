"""Playwright 通用工具 v5 — session持久化 + 打码平台 + SMS API + 熔断器 + 多策略选择器"""

import asyncio
import json
import os
import random
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Callable, Awaitable

from loguru import logger
from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception_type, before_sleep_log,
)

SCREENSHOT_DIR = Path("screenshots")
SESSION_DIR = Path("sessions")
SESSION_DIR.mkdir(parents=True, exist_ok=True)
SESSION_MAX_AGE_MINUTES = 50  # 税务局 session 通常 30-60 分钟过期


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


# ============================================================
# Session 持久化 — 人工登录一次，复用 N 次
# ============================================================

def _session_path(province: str) -> Path:
    return SESSION_DIR / f"{province}_session.json"


def is_session_valid(province: str) -> bool:
    """检查已保存的 session 是否仍在有效期内"""
    sp = _session_path(province)
    if not sp.exists():
        return False
    mtime = datetime.fromtimestamp(sp.stat().st_mtime)
    age = datetime.now() - mtime
    return age < timedelta(minutes=SESSION_MAX_AGE_MINUTES)


def session_age_minutes(province: str) -> float:
    sp = _session_path(province)
    if not sp.exists():
        return float("inf")
    mtime = datetime.fromtimestamp(sp.stat().st_mtime)
    return (datetime.now() - mtime).total_seconds() / 60


async def save_session(context, province: str) -> str:
    """保存浏览器 storage state（cookies + localStorage + sessionStorage）到磁盘"""
    sp = _session_path(province)
    await context.storage_state(path=str(sp))
    logger.info(f"[session] 已保存 {province} → {sp}")
    return str(sp)


async def load_session(context, province: str) -> bool:
    """从磁盘加载已保存的 session。返回 True 表示加载成功。"""
    sp = _session_path(province)
    if not sp.exists():
        logger.info(f"[session] {province} 无已保存 session")
        return False
    try:
        state = json.loads(sp.read_text(encoding="utf-8"))
        await context.add_cookies(state.get("cookies", []))
        # localStorage/origins 通过 storage_state 参数在 new_context 时加载更可靠
        logger.info(f"[session] 已加载 {province} (age={session_age_minutes(province):.0f}min)")
        return True
    except Exception as e:
        logger.warning(f"[session] 加载失败 {province}: {e}")
        return False


# ============================================================
# 打码平台集成 — YesCaptcha / 2Captcha（stub，需配置 API key 后激活）
# ============================================================

CAPTCHA_CLIENT_KEY = os.getenv("CAPTCHA_CLIENT_KEY", "")  # YesCaptcha 或 2Captcha 的 clientKey


async def solve_captcha(page, service: str = "yescaptcha") -> Optional[str]:
    """
    自动识别并解决验证码（滑块 / 图形 / reCAPTCHA）
    当前为 stub：未配置 CAPTCHA_CLIENT_KEY 时返回 None，由上层 fallback 到人工处理

    支持的 service: yescaptcha (国内), 2captcha (国际)
    激活方式: 设置环境变量 CAPTCHA_CLIENT_KEY=your_key
    """
    if not CAPTCHA_CLIENT_KEY:
        return None  # stub 模式，上层走人工处理

    import aiohttp

    # 1. 判断验证码类型
    captcha_type = None
    if await page.locator('.slider-captcha, .slide-verify, .nc_wrapper, #nc_1_n1z').count() > 0:
        captcha_type = "slider"
    elif await page.locator('img[src*="captcha"], img[id*="captcha"], .captcha img').count() > 0:
        captcha_type = "image"
    else:
        return None  # 未知类型

    if captcha_type == "image":
        captcha_el = page.locator('img[src*="captcha"], img[id*="captcha"], .captcha img').first
        if await captcha_el.count() == 0:
            return None
        img_bytes = await captcha_el.screenshot(type="png")
        import base64
        img_b64 = base64.b64encode(img_bytes).decode()

        api_url = (
            "https://api.yescaptcha.com/createTask"
            if service == "yescaptcha"
            else "https://api.2captcha.com/createTask"
        )
        task_data = {
            "clientKey": CAPTCHA_CLIENT_KEY,
            "task": {
                "type": "ImageToTextTask",
                "body": img_b64,
            },
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json=task_data, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    result = await resp.json()
            if result.get("errorId") == 0:
                code = result.get("solution", {}).get("text", "")
                captcha_input = page.locator(
                    'input[placeholder*="验证码"], input[name*="captcha"], input[id*="captcha"]'
                ).first
                if await captcha_input.count() > 0 and code:
                    await captcha_input.fill(code.strip())
                    logger.info(f"[打码] 图片验证码已自动填入: {code.strip()}")
                    return code.strip()
        except Exception as e:
            logger.warning(f"[打码] 识别失败: {e}")

    elif captcha_type == "slider":
        api_url = (
            "https://api.yescaptcha.com/createTask"
            if service == "yescaptcha"
            else "https://api.2captcha.com/createTask"
        )
        slider_data = {
            "clientKey": CAPTCHA_CLIENT_KEY,
            "task": {
                "type": "NoCaptchaTaskProxyless" if service == "2captcha" else "SliderTask",
                "websiteURL": page.url,
            },
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json=slider_data, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    result = await resp.json()
            if result.get("errorId") == 0 and result.get("solution"):
                logger.info("[打码] 滑块验证码已提交打码平台处理")
                return "slider_task_created"
        except Exception as e:
            logger.warning(f"[打码] 滑块识别失败: {e}")

    return None


# ============================================================
# SMS 验证码 API — 短信转发 / 接码平台（stub，需配置后激活）
# ============================================================

SMS_API_ENDPOINT = os.getenv("SMS_API_ENDPOINT", "")
SMS_API_KEY = os.getenv("SMS_API_KEY", "")


async def get_sms_code(phone: str, timeout: int = 60) -> Optional[str]:
    """
    从短信转发服务获取验证码
    当前为 stub：未配置 SMS_API_ENDPOINT 时返回 None，由上层 fallback 到人工输入

    激活方式: 设置环境变量
      SMS_API_ENDPOINT=https://your-sms-relay.com/api/latest-sms
      SMS_API_KEY=your_key
    """
    if not SMS_API_ENDPOINT or not SMS_API_KEY:
        return None

    import aiohttp

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    SMS_API_ENDPOINT,
                    params={"phone": phone, "limit": 1},
                    headers={"Authorization": f"Bearer {SMS_API_KEY}"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    data = await resp.json()
            if data.get("messages"):
                latest = data["messages"][0]
                # 提取6位数字验证码
                import re
                match = re.search(r"\d{4,6}", latest.get("content", ""))
                if match:
                    code = match.group()
                    logger.info(f"[SMS] 自动获取验证码: {code}")
                    return code
        except Exception as e:
            logger.warning(f"[SMS] 查询失败: {e}")
        await asyncio.sleep(5)
    return None


# ============================================================
# 交互式登录 — Session 持久化核心流程
# ============================================================

class SessionExpired(Exception):
    """Session 已过期，需重新人工登录"""
    def __init__(self, province: str, message: str = ""):
        self.province = province
        self.message = message or f"Session for {province} expired, manual re-login required"
        super().__init__(self.message)


async def interactive_login(
    page,
    login_url: str,
    login_selectors: dict,
    province: str,
    credentials: dict,
    max_wait_seconds: int = 120,
) -> bool:
    """
    交互式登录流程 — 打开可见浏览器，自动填写已知凭据，检测到验证码/SMS/UKey 时等待人工操作

    流程：
    1. 导航到登录页
    2. 自动填写用户名密码（如果有）
    3. 检测验证码 → 尝试打码平台 → 失败则等人
    4. 检测 SMS 输入框 → 尝试 SMS API → 失败则等人
    5. 检测 UKey 提示 → 等人插 UKey
    6. 等待 URL 变化为 dashboard/portal → 登录成功
    7. 保存 session

    Returns: True if login successful and session saved
    """
    if not await safe_goto(page, login_url):
        logger.error(f"[登录] 无法访问登录页 {login_url}")
        return False

    await asyncio.sleep(2)

    # 检查是否已登录
    page_url = page.url.lower()
    if any(kw in page_url for kw in ["dashboard", "home", "main", "portal", "workbench"]):
        logger.info(f"[登录] 已有有效 session，跳过登录")
        return True

    # Step 1: 自动填写凭据
    username = credentials.get("username", "")
    password = credentials.get("password", "")
    phone = credentials.get("phone", "")

    if username:
        await safe_fill(page, "税号", username, [login_selectors.get("username", "")])
    if password:
        await safe_fill(page, "密码", password, [login_selectors.get("password", "")])

    # Step 2: 按需尝试填手机号
    if phone:
        try:
            phone_input = page.locator('input[placeholder*="手机"], input[type="tel"]').first
            if await phone_input.count() > 0:
                await phone_input.fill(phone)
        except Exception:
            pass

    await page.screenshot(path=str(SCREENSHOT_DIR / f"login_{province}_pre_check.png"))

    # Step 3: 检测验证码 → 打码平台 / 人工
    if await detect_captcha(page):
        solved = await solve_captcha(page)
        if solved:
            logger.info(f"[登录] 打码平台已处理验证码")
        else:
            logger.info(f"[登录] 检测到验证码，等待人工处理（{max_wait_seconds}s）...")
            await page.screenshot(
                path=str(SCREENSHOT_DIR / f"login_{province}_needs_human.png")
            )

    # Step 4: 检测 SMS 输入框 → SMS API / 人工
    sms_input = page.locator(
        'input[placeholder*="短信"], input[placeholder*="验证码"], input[name*="sms"], input[name*="verify"]'
    ).first
    if await sms_input.count() > 0:
        if phone:
            sms_code = await get_sms_code(phone, timeout=30)
            if sms_code:
                await sms_input.fill(sms_code)
                logger.info(f"[登录] SMS 验证码已自动填入")
            else:
                logger.info(f"[登录] 等待人工输入 SMS 验证码...")

    # Step 5: 点击登录（如果还没自动跳转）
    await safe_click(page, "登录", [login_selectors.get("submit", "")])
    await asyncio.sleep(2)

    # Step 6: 等待登录完成 — 轮询 URL + 检测二次验证
    logger.info(f"[登录] 等待登录完成（最多 {max_wait_seconds}s）...")
    deadline = time.monotonic() + max_wait_seconds

    while time.monotonic() < deadline:
        try:
            page_url = page.url.lower()

            # 成功标志：进入 dashboard/home/main/portal/workbench
            if any(kw in page_url for kw in ["dashboard", "home", "main", "portal", "workbench", "invoice"]):
                logger.info(f"[登录] 成功 → {page_url}")
                return True

            # 仍在登录页，检查是否有新的验证码/SMS/UKey 提示
            if await detect_captcha(page):
                await solve_captcha(page)  # 再试一次打码平台
                await asyncio.sleep(2)

            # 检测 UKey 提示
            ukey_hints = page.locator(
                'text=插入, text=UKey, text=税控盘, text=金税盘, text=USB Key, text=数字证书'
            ).first
            if await ukey_hints.count() > 0:
                logger.info(f"[登录] 检测到 UKey 提示，等待插入硬件...")
                await page.screenshot(
                    path=str(SCREENSHOT_DIR / f"login_{province}_ukey_required.png")
                )
                # UKey 是老税号客户的硬障碍，等待人工操作
                await asyncio.sleep(5)  # 给用户时间插 UKey

            # 检测错误消息
            error_msg = page.locator(
                'text=密码错误, text=账号不存在, text=验证码错误, text=登录失败'
            ).first
            if await error_msg.count() > 0:
                error_text = await error_msg.text_content() or "登录失败"
                logger.error(f"[登录] 错误: {error_text}")
                await page.screenshot(
                    path=str(SCREENSHOT_DIR / f"login_{province}_error.png")
                )

        except Exception:
            pass

        await asyncio.sleep(3)

    logger.error(f"[登录] 超时（{max_wait_seconds}s），仍未检测到登录成功")
    await page.screenshot(path=str(SCREENSHOT_DIR / f"login_{province}_timeout.png"))
    return False


# ============================================================
# Session 保活 — 定时刷新防止过期
# ============================================================

async def keep_session_alive(page, province: str, target_url: str) -> bool:
    """访问目标页面保持 session 活跃，返回是否需要重新登录"""
    try:
        await page.goto(target_url, timeout=15000, wait_until="domcontentloaded")
        await asyncio.sleep(1)

        page_url = page.url.lower()
        # 检查是否被重定向到登录页（session 过期标志）
        if any(kw in page_url for kw in ["login", "signin", "auth", "cas"]):
            logger.warning(f"[保活] {province} session 已过期，重定向到登录页")
            return False

        # 轻量操作：滚动页面触发 ajax
        await page.evaluate("window.scrollTo(0, 300)")
        await asyncio.sleep(0.5)
        await page.evaluate("window.scrollTo(0, 0)")

        logger.debug(f"[保活] {province} session 刷新成功")
        return True
    except Exception as e:
        logger.warning(f"[保活] {province} 异常: {e}")
        return False


async def ensure_valid_session(
    context,
    page,
    province: str,
    login_url: str,
    target_url: str,
    login_selectors: dict,
    credentials: dict,
) -> bool:
    """
    确保 session 有效 — 处理完整生命周期：
    1. 有有效 session → 直接用
    2. Session 过期 → 重新交互式登录
    3. 无 session → 交互式登录
    4. Session 过期且登录失败 → raise SessionExpired

    Returns: True if session is ready to use
    """
    if is_session_valid(province):
        # 尝试用已保存 session 访问目标页面
        if await keep_session_alive(page, province, target_url):
            logger.info(f"[session] {province} 复用有效 session (age={session_age_minutes(province):.0f}min)")
            return True
        else:
            logger.info(f"[session] {province} session 已过期，需重新登录")

    # 需要重新登录
    logger.info(f"[session] {province} 开始交互式登录...")
    success = await interactive_login(
        page=page,
        login_url=login_url,
        login_selectors=login_selectors,
        province=province,
        credentials=credentials,
    )

    if success:
        await save_session(context, province)
        return True

    raise SessionExpired(
        province,
        f"无法完成 {province} 登录。请检查: 1) 网络连通 2) 账号密码 3) UKey(老税号) 4) 短信验证码",
    )
