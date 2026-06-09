"""Playwright 通用工具 v3 — 鲁棒选择器、自动重试、步骤截图、验证码检测（极限版）"""
import asyncio
import os
from pathlib import Path
from datetime import datetime
from typing import Optional

SCREENSHOT_DIR = Path("screenshots")


class NeedHumanReview(Exception):
    """检测到验证码或无法自动处理的页面，需人工介入"""

    def __init__(self, message: str, screenshot: str = ""):
        self.message = message
        self.screenshot = screenshot
        super().__init__(message)


class SelectorExhausted(Exception):
    """所有选择器链均失败"""
    pass


def screenshot_path(prefix: str = "step") -> str:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return str(SCREENSHOT_DIR / f"{prefix}_{ts}.png")


# ============================================================
# 多策略填充（增强版）
# ============================================================

async def safe_fill(page, label: str, value: str, fallback_selectors: list[str] = None):
    """
    多策略填充输入框（七层回退）：
    1. placeholder 包含 label
    2. name 属性包含 label
    3. aria-label 包含 label
    4. id 包含 label
    5. label 文本匹配 → 关联 input
    6. fallback_selectors
    7. 第一个可见 input
    """
    if not value:
        return

    selectors = [
        f'input[placeholder*="{label}"]',
        f'input[name*="{label}"]',
        f'input[aria-label*="{label}"]',
        f'input[id*="{label}"]',
    ]

    # label 文本关联查找
    try:
        label_el = page.locator(f'label:has-text("{label}"), .form-label:has-text("{label}")').first
        if await label_el.count() > 0:
            label_for = await label_el.get_attribute("for")
            if label_for:
                selectors.insert(0, f'#{label_for}')
            else:
                # 同级/父级内的第一个 input
                pass
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
    return False


# ============================================================
# 多策略点击（增强版）
# ============================================================

async def safe_click(page, label: str, fallback_selectors: list[str] = None) -> bool:
    """
    多策略点击按钮（十层回退）：
    1. button:has-text(label)
    2. a:has-text(label)
    3. [role="button"]:has-text(label)
    4. input[type="submit"][value*="label"]
    5. button[name*="label"]
    6. 通用 class 匹配 (.btn, .submit-btn, etc)
    7. span:has-text(label) → 点击父元素
    8. fallback_selectors
    9. 带 title/aria-label 的元素
    10. 模糊文本匹配
    """
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
    # 更通用的回退
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

    # 终极 fallback: JavaScript 查找最匹配的 button
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

    return False


# ============================================================
# 验证码检测（增强版 — 支持滑块/点击/短信验证码）
# ============================================================

async def detect_captcha(page) -> bool:
    """检测页面是否出现任何形式的验证码"""
    captcha_indicators = [
        # 图片验证码
        'img[src*="captcha"]',
        'img[src*="verification"]',
        'img[src*="code"]',
        'img[id*="captcha"]',
        'img[id*="verify"]',
        # 输入框
        'input[placeholder*="验证码"]',
        'input[name*="captcha"]',
        'input[name*="verifyCode"]',
        'input[id*="captcha"]',
        # 通用类名
        '.captcha',
        '#captcha',
        '.verification',
        '.verify-code',
        # 滑块验证
        '.slider-captcha',
        '.slide-verify',
        '.nc_wrapper',  # 阿里滑块
        '#nc_1_n1z',    # 阿里滑块滑块
        '.captcha_container',
        # 短信验证码
        'input[placeholder*="短信"]',
        'button:has-text("发送验证码")',
        'button:has-text("获取验证码")',
        # 腾讯验证码
        '#tcaptcha_iframe',
        '.tcaptcha-transform',
        # 极验验证码
        '.geetest_panel',
        '.geetest_holder',
        # 文本提示
        'text=请完成验证',
        'text=请点击验证',
        'text=请拖动滑块',
    ]
    for ind in captcha_indicators:
        try:
            if await page.locator(ind).count() > 0:
                return True
        except Exception:
            pass
    return False


async def detect_anti_bot(page) -> Optional[str]:
    """检测反爬/风控页面特征"""
    indicators = {
        'frequent': ['text=操作太频繁', 'text=访问过于频繁', 'text=请稍后再试'],
        'blocked': ['text=IP已被限制', 'text=账号已被锁定', 'text=访问被拒绝'],
        'maintenance': ['text=系统维护中', 'text=暂未开放', 'text=不在申报期'],
    }
    for risk_type, selectors in indicators.items():
        for sel in selectors:
            try:
                if await page.locator(sel).count() > 0:
                    return risk_type
            except Exception:
                pass
    return None


# ============================================================
# 重试引擎（指数退避 + 抖动）
# ============================================================

async def retry_with_backoff(fn, max_retries: int = 3, base_delay: float = 2):
    """指数退避重试（含随机抖动）"""
    import random
    for attempt in range(max_retries):
        try:
            return await fn()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            jitter = random.uniform(0, base_delay * 0.5)
            delay = base_delay * (2 ** attempt) + jitter
            await asyncio.sleep(delay)
    return None


# ============================================================
# 安全导航（含网络空闲等待 + 重试）
# ============================================================

async def safe_goto(page, url: str, timeout: int = 30000, max_retries: int = 3) -> bool:
    """安全导航到 URL，含重试和网络状态等待"""
    for attempt in range(max_retries):
        try:
            await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            # 等待网络空闲（最多等 10s）
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            return True
        except Exception:
            if attempt == max_retries - 1:
                return False
            await asyncio.sleep(3 * (attempt + 1))
    return False


# ============================================================
# 等待任一选择器出现
# ============================================================

async def wait_for_any(page, selectors: list[str], timeout: int = 10000) -> Optional[str]:
    """等待列表中任一选择器出现，返回命中的选择器"""
    tasks = []
    for sel in selectors:
        try:
            await page.wait_for_selector(sel, timeout=timeout, state="visible")
            return sel
        except Exception:
            continue
    return None


# ============================================================
# 批量截图 + 调试信息保存
# ============================================================

async def save_debug_snapshot(page, prefix: str = "debug") -> str:
    """保存当前页面截图 + HTML 源码"""
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
