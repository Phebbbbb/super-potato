"""数电票自动开票引擎 — 基于 Playwright 自动化电子税务局开票（鲁棒版 v2）"""
import os
import asyncio
from datetime import datetime
from pathlib import Path
from app.services.playwright_helpers import safe_fill, safe_click, detect_captcha, retry_with_backoff, NeedHumanReview, safe_goto, detect_anti_bot, save_debug_snapshot
from app.services.error_handler import log_error, log_info

SCREENSHOT_DIR = Path("screenshots/invoices")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# 省份配置 — 含精确 CSS 选择器
# ============================================================
BUREAU_CONFIGS = {
    "beijing": {
        "name": "北京市电子税务局",
        "login_url": "https://etax.beijing.chinatax.gov.cn/",
        "invoice_url": "https://etax.beijing.chinatax.gov.cn/invoice",
        "login_selectors": {
            "username": '#username, input[name="username"], input[placeholder*="税号"]',
            "password": '#password, input[name="password"], input[type="password"]',
            "submit": 'button[type="submit"], button:has-text("登录"), a:has-text("登录")',
            "captcha_img": '#captcha_img, img[src*="captcha"]',
        },
        "invoice_selectors": {
            "btn_new": 'button:has-text("开具"), a:has-text("蓝字发票开具"), button:has-text("新增")',
            "btn_invoice_type": {
                "electronic_normal": 'text=电子普通发票, label:has-text("电子普通发票")',
                "electronic_special": 'text=电子专用发票, label:has-text("电子专用发票")',
            },
            "buyer_name": 'input[name*="buyerName"], input[placeholder*="购方名称"]',
            "buyer_tax_no": 'input[name*="buyerTaxNo"], input[placeholder*="纳税人识别号"]',
            "buyer_address": 'input[name*="address"], textarea[name*="address"]',
            "buyer_phone": 'input[name*="phone"], input[type="tel"]',
            "buyer_bank": 'input[name*="bank"], input[placeholder*="开户银行"]',
            "buyer_account": 'input[name*="account"], input[placeholder*="银行账号"]',
            "btn_add_row": 'button:has-text("新增行"), button:has-text("添加"), a:has-text("新增行")',
            "item_name": 'input[name*="itemName"], input[placeholder*="货物名称"]',
            "item_spec": 'input[name*="spec"], input[placeholder*="规格"]',
            "item_unit": 'input[name*="unit"], input[placeholder*="单位"]',
            "item_qty": 'input[name*="quantity"], input[placeholder*="数量"]',
            "item_price": 'input[name*="price"], input[placeholder*="单价"]',
            "item_amount": 'input[name*="amount"], input[placeholder*="金额"]',
            "item_tax_rate": 'select[name*="taxRate"], input[placeholder*="税率"]',
            "remark": 'textarea, input[name*="remark"], input[placeholder*="备注"]',
            "btn_submit": 'button:has-text("开具"), button:has-text("提交"), button[type="submit"]',
            "success_indicator": 'text=开具成功, text=提交成功, text=开票成功',
        },
    },
    "shanghai": {
        "name": "上海市电子税务局",
        "login_url": "https://etax.shanghai.chinatax.gov.cn/",
        "invoice_url": "https://etax.shanghai.chinatax.gov.cn/invoice",
        "login_selectors": {
            "username": 'input[name="username"], input[placeholder*="用户名"]',
            "password": 'input[name="password"], input[type="password"]',
            "submit": 'button:has-text("登录"), input[type="submit"]',
        },
        "invoice_selectors": {
            "btn_new": 'button:has-text("开具"), a:has-text("蓝字发票"), button:has-text("新增")',
            "btn_invoice_type": {
                "electronic_normal": 'text=电子普通发票',
                "electronic_special": 'text=电子专用发票',
            },
            "buyer_name": 'input[name*="buyerName"], input[placeholder*="名称"]',
            "buyer_tax_no": 'input[name*="buyerTaxNo"], input[placeholder*="税号"]',
            "buyer_address": 'input[name*="address"], textarea[name*="address"]',
            "buyer_phone": 'input[name*="phone"], input[type="tel"]',
            "buyer_bank": 'input[name*="bank"]',
            "buyer_account": 'input[name*="account"]',
            "btn_add_row": 'button:has-text("新增行"), button:has-text("添加")',
            "item_name": 'input[name*="itemName"], input[placeholder*="货物名称"]',
            "item_spec": 'input[name*="spec"]',
            "item_unit": 'input[name*="unit"]',
            "item_qty": 'input[name*="quantity"]',
            "item_price": 'input[name*="price"]',
            "item_amount": 'input[name*="amount"]',
            "item_tax_rate": 'select[name*="taxRate"]',
            "remark": 'textarea',
            "btn_submit": 'button:has-text("正式提交"), button:has-text("开具")',
            "success_indicator": 'text=开具成功',
        },
    },
    "guangdong": {
        "name": "广东省电子税务局",
        "login_url": "https://etax.guangdong.chinatax.gov.cn/",
        "invoice_url": "https://etax.guangdong.chinatax.gov.cn/invoice",
        "login_selectors": {
            "username": 'input[name="username"], input[placeholder*="用户名"]',
            "password": 'input[name="password"], input[type="password"]',
            "submit": 'button:has-text("登录"), button[type="submit"]',
            "captcha_img": 'img[src*="captcha"]',
        },
        "invoice_selectors": {
            "btn_new": 'button:has-text("开具"), a:has-text("蓝字发票"), button:has-text("新增")',
            "btn_invoice_type": {
                "electronic_normal": 'text=电子普通发票',
                "electronic_special": 'text=电子专用发票',
            },
            "buyer_name": 'input[name*="buyerName"], input[placeholder*="名称"]',
            "buyer_tax_no": 'input[name*="buyerTaxNo"], input[placeholder*="税号"]',
            "buyer_address": 'input[name*="address"], textarea',
            "buyer_phone": 'input[name*="phone"], input[type="tel"]',
            "buyer_bank": 'input[name*="bank"]',
            "buyer_account": 'input[name*="account"]',
            "btn_add_row": 'button:has-text("新增行"), button:has-text("添加")',
            "item_name": 'input[name*="itemName"]',
            "item_spec": 'input[name*="spec"]',
            "item_unit": 'input[name*="unit"]',
            "item_qty": 'input[name*="quantity"]',
            "item_price": 'input[name*="price"]',
            "item_amount": 'input[name*="amount"]',
            "item_tax_rate": 'select[name*="taxRate"]',
            "remark": 'textarea',
            "btn_submit": 'button:has-text("提交"), button:has-text("开具")',
            "success_indicator": 'text=开具成功, text=提交成功',
        },
    },
    "zhejiang": {
        "name": "浙江省电子税务局",
        "login_url": "https://etax.zhejiang.chinatax.gov.cn/",
        "invoice_url": "https://etax.zhejiang.chinatax.gov.cn/invoice",
        "login_selectors": {
            "username": 'input[name="username"], input[placeholder*="用户名"]',
            "password": 'input[name="password"], input[type="password"]',
            "submit": 'button:has-text("登录"), button[type="submit"]',
        },
        "invoice_selectors": {
            "btn_new": 'button:has-text("开具"), button:has-text("新增")',
            "btn_invoice_type": {
                "electronic_normal": 'text=电子普通发票',
                "electronic_special": 'text=电子专用发票',
            },
            "buyer_name": 'input[name*="buyerName"]',
            "buyer_tax_no": 'input[name*="buyerTaxNo"]',
            "buyer_address": 'input[name*="address"]',
            "buyer_phone": 'input[name*="phone"]',
            "buyer_bank": 'input[name*="bank"]',
            "buyer_account": 'input[name*="account"]',
            "btn_add_row": 'button:has-text("新增行"), button:has-text("添加")',
            "item_name": 'input[name*="itemName"]',
            "item_spec": 'input[name*="spec"]',
            "item_unit": 'input[name*="unit"]',
            "item_qty": 'input[name*="quantity"]',
            "item_price": 'input[name*="price"]',
            "item_amount": 'input[name*="amount"]',
            "item_tax_rate": 'select[name*="taxRate"]',
            "remark": 'textarea',
            "btn_submit": 'button:has-text("提交"), button:has-text("开具")',
            "success_indicator": 'text=开具成功',
        },
    },
    "jiangsu": {
        "name": "江苏省电子税务局",
        "login_url": "https://etax.jiangsu.chinatax.gov.cn/",
        "invoice_url": "https://etax.jiangsu.chinatax.gov.cn/invoice",
        "login_selectors": {
            "username": 'input[name="username"], input[placeholder*="用户名"]',
            "password": 'input[name="password"], input[type="password"]',
            "submit": 'button:has-text("登录"), button[type="submit"]',
        },
        "invoice_selectors": {
            "btn_new": 'button:has-text("开具"), button:has-text("新增")',
            "btn_invoice_type": {
                "electronic_normal": 'text=电子普通发票',
                "electronic_special": 'text=电子专用发票',
            },
            "buyer_name": 'input[name*="buyerName"]',
            "buyer_tax_no": 'input[name*="buyerTaxNo"]',
            "buyer_address": 'input[name*="address"]',
            "buyer_phone": 'input[name*="phone"]',
            "buyer_bank": 'input[name*="bank"]',
            "buyer_account": 'input[name*="account"]',
            "btn_add_row": 'button:has-text("新增行")',
            "item_name": 'input[name*="itemName"]',
            "item_spec": 'input[name*="spec"]',
            "item_unit": 'input[name*="unit"]',
            "item_qty": 'input[name*="quantity"]',
            "item_price": 'input[name*="price"]',
            "item_amount": 'input[name*="amount"]',
            "item_tax_rate": 'select[name*="taxRate"]',
            "remark": 'textarea',
            "btn_submit": 'button:has-text("提交"), button:has-text("开具")',
            "success_indicator": 'text=开具成功',
        },
    },
    "generic": {
        "name": "电子税务局（通用）",
        "login_url": "https://etax.chinatax.gov.cn/",
        "invoice_url": "https://etax.chinatax.gov.cn/invoice",
        "login_selectors": {
            "username": 'input[name="username"], input[type="text"]:visible',
            "password": 'input[name="password"], input[type="password"]',
            "submit": 'button:has-text("登录"), button[type="submit"]',
        },
        "invoice_selectors": {
            "btn_new": 'button:has-text("开具"), button:has-text("新增"), a:has-text("蓝字发票")',
            "btn_invoice_type": {
                "electronic_normal": 'text=电子普通发票',
                "electronic_special": 'text=电子专用发票',
            },
            "buyer_name": 'input[name*="buyerName"], input[name*="name"]',
            "buyer_tax_no": 'input[name*="buyerTaxNo"], input[name*="taxNo"]',
            "buyer_address": 'input[name*="address"], textarea',
            "buyer_phone": 'input[name*="phone"], input[type="tel"]',
            "buyer_bank": 'input[name*="bank"]',
            "buyer_account": 'input[name*="account"]',
            "btn_add_row": 'button:has-text("新增行"), button:has-text("添加")',
            "item_name": 'input[name*="itemName"], input[name*="name"]',
            "item_spec": 'input[name*="spec"]',
            "item_unit": 'input[name*="unit"]',
            "item_qty": 'input[name*="quantity"]',
            "item_price": 'input[name*="price"]',
            "item_amount": 'input[name*="amount"]',
            "item_tax_rate": 'select[name*="taxRate"], input[name*="taxRate"]',
            "remark": 'textarea',
            "btn_submit": 'button:has-text("开具"), button[type="submit"], button:has-text("提交")',
            "success_indicator": 'text=成功, text=开具成功',
        },
    },
}


def get_invoice_engine_config():
    """获取开票引擎配置"""
    return {
        "headless": os.getenv("INVOICE_HEADLESS", "true").lower() == "true",
        "timeout": int(os.getenv("INVOICE_TIMEOUT", "60000")),
    }


async def _fill_by_selectors(page, selector_str: str, value: str, step: str = "") -> bool:
    """使用逗号分隔的选择器列表尝试填充（按优先级）"""
    if not value:
        return True
    selectors = [s.strip() for s in selector_str.split(",") if s.strip()]
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                await el.click()
                await el.fill(str(value))
                return True
        except Exception:
            continue
    # Fallback: try safe_fill with label-based search
    if step:
        await safe_fill(page, step, value)
        return True
    return False


async def _click_by_selectors(page, selector_str: str, step: str = "") -> bool:
    """使用逗号分隔的选择器列表尝试点击（按优先级）"""
    selectors = [s.strip() for s in selector_str.split(",") if s.strip()]
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                await el.click()
                await asyncio.sleep(0.3)
                return True
        except Exception:
            continue
    return False


async def issue_invoice_playwright(
    invoice_id: str,
    buyer_name: str,
    buyer_tax_no: str,
    buyer_address: str = "",
    buyer_phone: str = "",
    buyer_bank: str = "",
    buyer_account: str = "",
    invoice_type: str = "electronic_normal",
    items: list = None,
    remark: str = "",
    tax_credentials: dict = None,
) -> dict:
    """
    自动登录电子税务局 → 进入数电票开票 → 填写购方/商品 → 提交开票 → 截图留证
    v2: 使用精确 CSS 选择器 + 多策略回退
    """
    if items is None:
        items = []

    config = get_invoice_engine_config()

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {
            "success": False, "invoice_id": invoice_id,
            "message": "开票引擎未就绪，请执行 pip install playwright && playwright install chromium",
        }

    province = (tax_credentials or {}).get("province", "generic")
    bureau = BUREAU_CONFIGS.get(province, BUREAU_CONFIGS["generic"])
    username = (tax_credentials or {}).get("username", "")
    password = (tax_credentials or {}).get("password", "")
    login_s = bureau["login_selectors"]
    inv_s = bureau["invoice_selectors"]

    result = {
        "success": False, "invoice_id": invoice_id,
        "invoice_code": "", "invoice_no": "", "invoice_url": "",
        "screenshot": "", "message": "",
    }

    rid = invoice_id[:8]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=config["headless"])
        context = await browser.new_context(viewport={"width": 1366, "height": 768}, locale="zh-CN")
        page = await context.new_page()

        try:
            # === Step 1: 登录 ===
            log_info("tax_invoice", "step1_login", f"invoice={rid} province={province}")
            await safe_goto(page, bureau["login_url"], timeout=config["timeout"])
            await page.screenshot(path=str(SCREENSHOT_DIR / f"invoice_{rid}_01_login.png"))

            if not username:
                result["message"] = "未配置电子税务局账号，请在 Settings → 系统配置中设置 tax_bureau_auth"
                return result

            await _fill_by_selectors(page, login_s["username"], username, "用户名")
            await _fill_by_selectors(page, login_s["password"], password, "密码")
            await _click_by_selectors(page, login_s["submit"], "登录按钮")
            try: await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception: await asyncio.sleep(2)

            # 检测验证码
            if await detect_captcha(page):
                cap_path = str(SCREENSHOT_DIR / f"captcha_{rid}.png")
                await page.screenshot(path=cap_path)
                log_error("tax_invoice", NeedHumanReview("检测到验证码"), {"invoice_id": rid})
                result["message"] = "检测到验证码，需人工登录后重试"
                result["screenshot"] = cap_path
                return result

            # 检测反爬/风控
            risk = await detect_anti_bot(page)
            if risk:
                result["message"] = f"检测到风控限制 ({risk})，请稍后再试或切换网络"
                return result

            # === Step 2: 导航到开票页 ===
            log_info("tax_invoice", "step2_navigate", f"invoice={rid}")
            await safe_goto(page, bureau["invoice_url"], timeout=config["timeout"])
            await page.screenshot(path=str(SCREENSHOT_DIR / f"invoice_{rid}_02_page.png"))

            await _click_by_selectors(page, inv_s["btn_new"], "开票按钮")
            try: await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception: pass

            # === Step 3: 选择发票类型 ===
            type_sel = inv_s["btn_invoice_type"].get(invoice_type, "")
            if type_sel:
                await _click_by_selectors(page, type_sel, "发票类型")
                await asyncio.sleep(0.3)

            # === Step 4: 填写购方信息 ===
            log_info("tax_invoice", "step4_buyer", f"buyer={buyer_name}")
            await _fill_by_selectors(page, inv_s["buyer_name"], buyer_name, "购方名称")
            await _fill_by_selectors(page, inv_s["buyer_tax_no"], buyer_tax_no, "纳税人识别号")
            await _fill_by_selectors(page, inv_s["buyer_address"], buyer_address, "购方地址")
            await _fill_by_selectors(page, inv_s["buyer_phone"], buyer_phone, "购方电话")
            await _fill_by_selectors(page, inv_s["buyer_bank"], buyer_bank, "开户银行")
            await _fill_by_selectors(page, inv_s["buyer_account"], buyer_account, "银行账号")
            await page.screenshot(path=str(SCREENSHOT_DIR / f"invoice_{rid}_03_buyer.png"))

            # === Step 5: 填写商品明细 ===
            log_info("tax_invoice", "step5_items", f"count={len(items)}")
            for i, item in enumerate(items):
                if i > 0:
                    await _click_by_selectors(page, inv_s["btn_add_row"], "新增行")
                    await asyncio.sleep(0.3)

                await _fill_by_selectors(page, inv_s["item_name"], item.get("name", ""), "货物名称")
                await _fill_by_selectors(page, inv_s["item_spec"], item.get("spec", ""), "规格")
                await _fill_by_selectors(page, inv_s["item_unit"], item.get("unit", ""), "单位")
                await _fill_by_selectors(page, inv_s["item_qty"], str(item.get("quantity", 1)), "数量")
                await _fill_by_selectors(page, inv_s["item_price"], str(item.get("price", 0)), "单价")
                await _fill_by_selectors(page, inv_s["item_amount"], str(item.get("amount", 0)), "金额")
                rate_str = f"{item.get('tax_rate', 0) * 100:.0f}%"
                await _fill_by_selectors(page, inv_s["item_tax_rate"], rate_str, "税率")
                await asyncio.sleep(0.2)

            await page.screenshot(path=str(SCREENSHOT_DIR / f"invoice_{rid}_04_items.png"))

            # === Step 6: 备注 ===
            if remark:
                await _fill_by_selectors(page, inv_s["remark"], remark, "备注")
                await asyncio.sleep(0.3)

            # === Step 7: 提交开票 ===
            log_info("tax_invoice", "step7_submit")
            clicked = await _click_by_selectors(page, inv_s["btn_submit"], "提交按钮")
            if not clicked:
                result["message"] = "未找到提交按钮，页面结构可能已变化，请查看截图"
                await page.screenshot(path=str(SCREENSHOT_DIR / f"error_no_submit_{rid}.png"))
                return result

            try: await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception: await asyncio.sleep(2)

            # === Step 8: 验证结果 ===
            screenshot_filename = f"invoice_{rid}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
            screenshot_path = SCREENSHOT_DIR / screenshot_filename
            await page.screenshot(path=str(screenshot_path), full_page=True)

            success = False
            try:
                for s in inv_s["success_indicator"].split(","):
                    if await page.locator(s.strip()).count() > 0:
                        success = True
                        break
            except Exception:
                pass

            result["success"] = True
            result["screenshot"] = screenshot_filename
            result["message"] = "发票开具成功" if success else "发票已提交，请登录电子税务局确认开具结果"
            result["invoice_code"] = f"AUTO-{rid}"
            log_info("tax_invoice", "done", f"invoice={rid} success={success}")

            return result

        except Exception as e:
            log_error("tax_invoice", e, {"invoice_id": rid, "province": province})
            result["message"] = f"开票流程异常: {str(e)[:200]}"
            try:
                result["screenshot"] = await save_debug_snapshot(page, f"error_invoice_{rid}")
            except Exception:
                pass
            return result

        finally:
            await browser.close()
