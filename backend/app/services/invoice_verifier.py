"""国税局发票真伪查验引擎 — Playwright 自动化查询 inv-veri.chinatax.gov.cn"""
import asyncio
import os
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from app.services.playwright_helpers import safe_fill, safe_click, detect_captcha, safe_goto, save_debug_snapshot, NeedHumanReview
from app.services.error_handler import log_error, log_info

SCREENSHOT_DIR = Path("screenshots/verify")

VERIFY_URL = "https://inv-veri.chinatax.gov.cn/"

# 验证平台选择器（基于当前国家税务总局发票查验平台页面结构）
VERIFY_SELECTORS = {
    "invoice_code": 'input[id*="fpdm"], input[name*="fpdm"], input[placeholder*="发票代码"]',
    "invoice_no": 'input[id*="fphm"], input[name*="fphm"], input[placeholder*="发票号码"]',
    "invoice_date": 'input[id*="kprq"], input[name*="kprq"], input[placeholder*="开票日期"]',
    "verify_code_input": 'input[id*="jym"], input[name*="jym"], input[placeholder*="校验码"]',
    "verify_code_img": 'img[id*="yzm"], img[src*="verify"], img[src*="captcha"], img[src*="code"]',
    "amount": 'input[id*="je"], input[name*="je"], input[placeholder*="开具金额"]',
    "btn_verify": 'button:has-text("查验"), button[type="submit"], button:has-text("查询"), a:has-text("查验")',
    "result_indicator": 'text=查验结果, text=发票信息, text=正常, #cxResult',
    "error_indicator": 'text=查无此票, text=不一致, text=验证码错误, text=请输入正确的',
    "result_table": '#cyResult table, .result-table, table[id*="result"]',
}


@dataclass
class VerifyResult:
    """发票查验结果"""
    success: bool
    invoice_code: str = ""
    invoice_no: str = ""
    is_valid: bool = False  # 发票是否真实有效
    message: str = ""
    # 发票明细（查验成功时返回）
    invoice_type: str = ""       # 发票类型（增值税专票/普票等）
    seller_name: str = ""        # 销售方名称
    seller_tax_no: str = ""      # 销售方纳税人识别号
    buyer_name: str = ""         # 购买方名称
    buyer_tax_no: str = ""       # 购买方纳税人识别号
    invoice_date: str = ""       # 开票日期
    total_amount: str = ""       # 金额（不含税）
    tax_amount: str = ""         # 税额
    grand_total: str = ""        # 价税合计
    verify_count: int = 0        # 查验次数（国税局记录）
    screenshot: str = ""
    raw_text: str = ""           # 原始结果文本（用于 debug）


async def verify_invoice(
    invoice_code: str,
    invoice_no: str,
    invoice_date: str,   # YYYY-MM-DD 或 YYYYMMDD
    amount: str = "",     # 开具金额（不含税）
    check_code: str = "", # 校验码后6位（新版发票需要）
    headless: bool = True,
) -> VerifyResult:
    """
    自动登录国家税务总局发票查验平台，查询发票真伪

    Args:
        invoice_code: 发票代码（10或12位）
        invoice_no: 发票号码（8位）
        invoice_date: 开票日期
        amount: 开具金额（不含税），可选
        check_code: 校验码后6位，可选
    """
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    rid = invoice_code[-6:] + invoice_no[:4]

    result = VerifyResult(
        success=False, invoice_code=invoice_code, invoice_no=invoice_no,
    )

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        result.message = "Playwright 未安装，无法进行自动化发票查验"
        return result

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768}, locale="zh-CN",
        )
        page = await context.new_page()

        try:
            # Step 1: 打开查验平台
            log_info("invoice_verify", "step1_open", f"code={invoice_code} no={invoice_no}")
            if not await safe_goto(page, VERIFY_URL, timeout=30000):
                result.message = "无法访问国家税务总局发票查验平台"
                return result

            await asyncio.sleep(3)
            await page.screenshot(path=str(SCREENSHOT_DIR / f"verify_{rid}_01_platform.png"))

            # Step 2: 填写发票信息
            s = VERIFY_SELECTORS

            await safe_fill(page, "发票代码", invoice_code)
            await safe_fill(page, "发票号码", invoice_no)

            # 日期格式转换
            date_str = invoice_date.replace("-", "")
            if len(date_str) == 8:
                # 按 YYYYMMDD 格式逐段填写（某些平台需要分三个输入框）
                y, m, d = date_str[:4], date_str[4:6], date_str[6:8]
                # 尝试统一输入框
                await safe_fill(page, "开票日期", f"{y}-{m}-{d}")
            else:
                await safe_fill(page, "开票日期", invoice_date)

            if check_code:
                await safe_fill(page, "校验码", check_code)

            if amount:
                await safe_fill(page, "开具金额", amount)

            await asyncio.sleep(1)
            await page.screenshot(path=str(SCREENSHOT_DIR / f"verify_{rid}_02_filled.png"))

            # Step 3: 处理验证码
            captcha_detected = await detect_captcha(page)
            if captcha_detected:
                # 保存验证码截图
                cap_path = str(SCREENSHOT_DIR / f"verify_captcha_{rid}.png")
                await page.screenshot(path=cap_path)

                if headless:
                    # Headless 模式下无法处理验证码 → 抛 NeedHumanReview
                    log_info("invoice_verify", "captcha_blocked", f"screenshot={cap_path}")
                    result.message = "发票查验平台要求验证码，请在 headless=false 模式下重试，或手动登录 https://inv-veri.chinatax.gov.cn/ 查验"
                    result.screenshot = cap_path
                    return result
                else:
                    # 非 headless → 等待人工输入验证码（60秒）
                    print(f"[发票查验] 检测到验证码，请手动输入（60秒超时）→ 截图: {cap_path}")
                    try:
                        verify_input = s.get("verify_code_input", 'input[placeholder*="验证码"]')
                        await page.wait_for_function(
                            f"document.querySelector('{verify_input}')?.value?.length >= 3",
                            timeout=60000,
                        )
                    except Exception:
                        result.message = f"验证码输入超时，请重试。截图: {cap_path}"
                        result.screenshot = cap_path
                        return result

            # Step 4: 点击查验
            await safe_click(page, "查验")
            await asyncio.sleep(5)

            # Step 5: 读取结果
            await page.screenshot(path=str(SCREENSHOT_DIR / f"verify_{rid}_03_result.png"), full_page=True)

            # 检测是否验证码错误
            try:
                for err_sel in s["error_indicator"].split(","):
                    if await page.locator(err_sel.strip()).count() > 0:
                        error_text = await page.locator(err_sel.strip()).first.text_content() or "查询失败"
                        result.message = f"查验失败: {error_text[:200]}"
                        return result
            except Exception:
                pass

            # 尝试提取结果表格
            try:
                result_table = page.locator(s["result_table"]).first
                if await result_table.count() > 0:
                    result.raw_text = (await result_table.text_content() or "")[:2000]

                    # 解析表格行
                    rows = result_table.locator("tr")
                    row_count = await rows.count()
                    cell_data: dict[str, str] = {}
                    for i in range(row_count):
                        cells = rows.nth(i).locator("td, th")
                        cell_count = await cells.count()
                        if cell_count >= 2:
                            key = (await cells.nth(0).text_content() or "").strip()
                            val = (await cells.nth(1).text_content() or "").strip()
                            if key:
                                cell_data[key] = val

                    result.invoice_type = cell_data.get("发票类型", cell_data.get("票据类型", ""))
                    result.seller_name = cell_data.get("销售方名称", cell_data.get("销方名称", ""))
                    result.seller_tax_no = cell_data.get("销售方纳税人识别号", cell_data.get("销方识别号", ""))
                    result.buyer_name = cell_data.get("购买方名称", cell_data.get("购方名称", ""))
                    result.buyer_tax_no = cell_data.get("购买方纳税人识别号", cell_data.get("购方识别号", ""))
                    result.invoice_date = cell_data.get("开票日期", "")
                    result.total_amount = cell_data.get("金额", cell_data.get("合计金额", ""))
                    result.tax_amount = cell_data.get("税额", cell_data.get("合计税额", ""))
                    result.grand_total = cell_data.get("价税合计", cell_data.get("价税合计(大写)", ""))
                    verify_count_str = cell_data.get("查验次数", "0")
                    try:
                        result.verify_count = int(verify_count_str)
                    except ValueError:
                        result.verify_count = 0
            except Exception:
                pass

            # 判断最终结果
            try:
                for ok_sel in s["result_indicator"].split(","):
                    if await page.locator(ok_sel.strip()).count() > 0:
                        result.is_valid = True
                        result.success = True
                        result.message = "发票查验通过 — 该发票为真"
                        break
            except Exception:
                pass

            if not result.is_valid and result.raw_text:
                # 有结果但非正常 → 可能是红冲/作废
                if "作废" in result.raw_text:
                    result.message = "发票查验结果: 该发票已作废"
                elif "红冲" in result.raw_text:
                    result.message = "发票查验结果: 该发票已被红冲"
                elif "查无此票" in result.raw_text:
                    result.message = "发票查验结果: 查无此票 — 可能为假发票或数据尚未同步"
                else:
                    result.success = True  # 查验操作成功
                    result.message = f"查验完成，结果: {result.raw_text[:100]}"
            elif not result.raw_text:
                result.success = True
                result.message = result.message or "查验完成，未提取到明细数据，请查看截图确认"

            result.screenshot = f"verify_{rid}_03_result.png"
            log_info("invoice_verify", "done", f"valid={result.is_valid} code={invoice_code}")

        except Exception as e:
            log_error("invoice_verify", e, {"invoice_code": invoice_code, "invoice_no": invoice_no})
            result.message = f"查验流程异常: {str(e)[:200]}"
            try:
                await save_debug_snapshot(page, f"verify_error_{rid}")
            except Exception:
                pass

        finally:
            await browser.close()

    return result


# ============================================================
# 批量查验
# ============================================================

async def batch_verify_invoices(
    invoices: list[dict],
    headless: bool = True,
    max_concurrent: int = 2,
) -> list[VerifyResult]:
    """批量查验发票（限流并发，避免触发国税局风控）"""
    sem = asyncio.Semaphore(max_concurrent)

    async def _verify_one(inv: dict):
        async with sem:
            return await verify_invoice(
                invoice_code=inv.get("invoice_code", ""),
                invoice_no=inv.get("invoice_no", ""),
                invoice_date=inv.get("invoice_date", ""),
                amount=inv.get("amount", ""),
                check_code=inv.get("check_code", ""),
                headless=headless,
            )

    tasks = [_verify_one(inv) for inv in invoices]
    return list(await asyncio.gather(*tasks))
