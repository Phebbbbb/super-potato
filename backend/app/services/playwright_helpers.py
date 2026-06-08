"""Playwright 通用工具 — 鲁棒选择器、自动重试、步骤截图、验证码检测"""
import asyncio
import os
from pathlib import Path
from datetime import datetime

SCREENSHOT_DIR = Path("screenshots")


class NeedHumanReview(Exception):
    """检测到验证码或无法自动处理的页面，需人工介入"""

    def __init__(self, message: str, screenshot: str = ""):
        self.message = message
        self.screenshot = screenshot
        super().__init__(message)


def screenshot_path(prefix: str = "step") -> str:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return str(SCREENSHOT_DIR / f"{prefix}_{ts}.png")


async def safe_fill(page, label: str, value: str, fallback_selectors: list[str] = None):
    """
    多策略填充输入框：label 匹配 → placeholder 匹配 → name 匹配 → fallback → 第一个可见 input
    """
    if not value:
        return
    selectors = [
        f'input[placeholder*="{label}"]',
        f'input[name*="{label}"]',
        f'input[aria-label*="{label}"]',
    ]
    if fallback_selectors:
        selectors.extend(fallback_selectors)
    selectors.append("input:visible")

    for sel in selectors:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                await el.click()
                await el.fill(str(value))
                await asyncio.sleep(0.3)
                return
        except Exception:
            continue


async def safe_click(page, label: str, fallback_selectors: list[str] = None):
    """
    多策略点击按钮：文本匹配 → aria-label → 关键词 → fallback
    """
    selectors = [
        f'button:has-text("{label}")',
        f'a:has-text("{label}")',
        f'[role="button"]:has-text("{label}")',
    ]
    if fallback_selectors:
        selectors.extend(fallback_selectors)

    for sel in selectors:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                await el.click()
                await asyncio.sleep(1)
                return True
        except Exception:
            continue
    return False


async def detect_captcha(page) -> bool:
    """检测页面是否出现验证码"""
    captcha_indicators = [
        'img[src*="captcha"]',
        'img[src*="verification"]',
        'input[placeholder*="验证码"]',
        'text=验证码',
        '.captcha',
        '#captcha',
    ]
    for ind in captcha_indicators:
        try:
            if await page.locator(ind).count() > 0:
                return True
        except Exception:
            pass
    return False


async def retry_with_backoff(fn, max_retries: int = 3, base_delay: float = 2):
    """指数退避重试"""
    for attempt in range(max_retries):
        try:
            return await fn()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            await asyncio.sleep(delay)
    return None
