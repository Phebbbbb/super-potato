"""
零成本自动申报引擎 — 基于 Playwright 模拟浏览器操作电子税务局
替代商业 RPA（影刀/来也），年省 ¥3,000-8,000

支持的税局：
  - beijing: 北京市电子税务局
  - shanghai: 上海市电子税务局
  - guangdong: 广东省电子税务局
  - generic: 通用模板（需自行填写选择器）

用法：
  engine = TaxAutomationEngine(profile="beijing", headless=False)
  result = await engine.run_filing(
      tax_type="vat",
      period="2026-06",
      tax_data={"period_sales": 50000, "tax_payable": 1500},
      credentials={"username": "xxx", "password": "xxx"},
  )
"""
import json
import os
import asyncio
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from app.services.playwright_helpers import detect_captcha, detect_anti_bot, retry_with_backoff, safe_goto, save_debug_snapshot
from app.services.error_handler import log_error, log_info


# ============================================================
# 省份配置文件
# ============================================================

TAX_BUREAU_CONFIGS = {
    "beijing": {
        "name": "北京市电子税务局",
        "login_url": "https://etax.beijing.chinatax.gov.cn/",
        "login_selectors": {
            "username": '#username, input[name="username"], input[placeholder*="税号"], input[placeholder*="用户名"], input[placeholder*="账号"]',
            "password": '#password, input[name="password"], input[type="password"]',
            "submit": 'button[type="submit"], button:has-text("登录"), input[type="submit"]',
            "captcha_img": "#captcha_img",
            "captcha_input": "#captcha",
        },
        "filing_selectors": {
            "vat": {
                "menu_declare": 'text=我要办税, text=税费申报, a:has-text("办税")',
                "menu_item": 'text=增值税申报, text=增值税一般纳税人申报, text=增值税小规模纳税人申报',
                "input_period_sales": '#current_period_sales, input[name*="sales"], input[placeholder*="销售额"]',
                "input_tax_payable": '#tax_amount, input[name*="tax"], input[placeholder*="应纳税额"]',
                "btn_submit": 'text=申报, button:has-text("申报"), button:has-text("提交")',
                "btn_confirm": 'text=确认, button:has-text("确认"), button:has-text("确定")',
                "success_indicator": 'text=申报成功, text=提交成功',
            },
            "corporate_income": {
                "menu_declare": 'text=我要办税, text=税费申报, a:has-text("办税")',
                "menu_item": 'text=企业所得税申报, text=企业所得税月(季)度申报, text=居民企业所得税申报',
                "input_revenue": '#total_revenue, input[name*="revenue"], input[placeholder*="营业收入"]',
                "input_cost": '#total_cost, input[name*="cost"], input[placeholder*="营业成本"]',
                "input_profit": '#total_profit, input[name*="profit"], input[placeholder*="利润"]',
                "input_tax_payable": '#income_tax_payable, input[name*="incomeTax"], input[name*="tax"], input[placeholder*="所得税"]',
                "btn_submit": 'text=申报, button:has-text("申报"), button:has-text("提交")',
                "btn_confirm": 'text=确认, button:has-text("确认"), button:has-text("确定")',
                "success_indicator": 'text=申报成功, text=提交成功',
            },
            "surtax": {
                "menu_declare": 'text=我要办税, text=税费申报',
                "menu_item": 'text=附加税申报, text=附加税费申报',
                "input_vat_amount": '#vat_amount, input[name*="vatAmount"], input[name*="vat"], input[placeholder*="增值税"]',
                "btn_submit": 'text=申报, button:has-text("申报"), button:has-text("提交")',
                "btn_confirm": 'text=确认, button:has-text("确认"), button:has-text("确定")',
                "success_indicator": 'text=申报成功, text=提交成功',
            },
            "stamp_duty": {
                "menu_declare": 'text=我要办税, text=税费申报',
                "menu_item": 'text=印花税申报',
                "input_taxable_amount": '#taxableAmount, input[name*="taxableAmount"], input[placeholder*="计税金额"]',
                "input_tax_payable": '#stampTax, input[name*="stampTax"], input[name*="tax"], input[placeholder*="印花税"]',
                "btn_submit": 'text=申报, button:has-text("申报"), button:has-text("提交")',
                "btn_confirm": 'text=确认, button:has-text("确认"), button:has-text("确定")',
                "success_indicator": 'text=申报成功, text=提交成功',
            },
            "property_tax": {
                "menu_declare": 'text=我要办税, text=税费申报',
                "menu_item": 'text=房产税申报',
                "input_property_value": '#propertyValue, input[name*="propertyValue"], input[placeholder*="原值"]',
                "input_tax_payable": '#propertyTax, input[name*="propertyTax"], input[name*="tax"], input[placeholder*="房产税"]',
                "btn_submit": 'text=申报, button:has-text("申报"), button:has-text("提交")',
                "btn_confirm": 'text=确认, button:has-text("确认"), button:has-text("确定")',
                "success_indicator": 'text=申报成功, text=提交成功',
            },
            "land_use_tax": {
                "menu_declare": 'text=我要办税, text=税费申报',
                "menu_item": 'text=城镇土地使用税申报',
                "input_land_area": '#landArea, input[name*="landArea"], input[placeholder*="面积"]',
                "input_tax_payable": '#landTax, input[name*="landTax"], input[name*="tax"], input[placeholder*="土地使用税"]',
                "btn_submit": 'text=申报, button:has-text("申报"), button:has-text("提交")',
                "btn_confirm": 'text=确认, button:has-text("确认"), button:has-text("确定")',
                "success_indicator": 'text=申报成功, text=提交成功',
            },
        },
    },
    "shanghai": {
        "name": "上海市电子税务局",
        "login_url": "https://etax.shanghai.chinatax.gov.cn/",
        "login_selectors": {
            "username": 'input[name="username"], input[placeholder*="税号"], input[placeholder*="用户名"]',
            "password": 'input[name="password"], input[type="password"]',
            "submit": 'button:has-text("登录"), input[type="submit"]',
        },
        "filing_selectors": {
            "vat": {
                "menu_declare": "text=税费申报, text=我要办税",
                "menu_item": "text=增值税一般纳税人申报, text=增值税申报",
                "input_period_sales": 'input[name="sales"], input[placeholder*="销售额"]',
                "input_tax_payable": 'input[name="taxPayable"], input[name*="tax"]',
                "btn_submit": "text=正式提交申报, button:has-text(\"申报\")",
                "btn_confirm": "text=确定, button:has-text(\"确定\")",
                "success_indicator": "text=申报成功",
            },
            "corporate_income": {
                "menu_declare": "text=税费申报, text=我要办税",
                "menu_item": "text=企业所得税月(季)度申报, text=企业所得税申报",
                "input_revenue": 'input[name="revenue"], input[placeholder*="收入"]',
                "input_cost": 'input[name="cost"], input[placeholder*="成本"]',
                "input_profit": 'input[name="profit"], input[placeholder*="利润"]',
                "input_tax_payable": 'input[name="incomeTax"], input[name*="tax"]',
                "btn_submit": "text=正式提交申报, button:has-text(\"申报\")",
                "btn_confirm": "text=确定, button:has-text(\"确定\")",
                "success_indicator": "text=申报成功",
            },
            "surtax": {
                "menu_declare": "text=税费申报, text=我要办税",
                "menu_item": "text=附加税费申报, text=附加税申报",
                "input_vat_amount": 'input[name="vatAmount"], input[name*="vat"]',
                "btn_submit": "text=正式提交申报, button:has-text(\"申报\")",
                "btn_confirm": "text=确定, button:has-text(\"确定\")",
                "success_indicator": "text=申报成功",
            },
            "stamp_duty": {
                "menu_declare": "text=税费申报",
                "menu_item": "text=印花税申报",
                "input_taxable_amount": 'input[name="taxableAmount"], input[placeholder*="计税金额"]',
                "input_tax_payable": 'input[name="stampTax"], input[name*="tax"]',
                "btn_submit": "text=正式提交申报, button:has-text(\"申报\")",
                "btn_confirm": "text=确定, button:has-text(\"确定\")",
                "success_indicator": "text=申报成功",
            },
            "property_tax": {
                "menu_declare": "text=税费申报",
                "menu_item": "text=房产税申报",
                "input_property_value": 'input[name="propertyValue"], input[placeholder*="原值"]',
                "input_tax_payable": 'input[name="propertyTax"], input[name*="tax"]',
                "btn_submit": "text=正式提交申报, button:has-text(\"申报\")",
                "btn_confirm": "text=确定, button:has-text(\"确定\")",
                "success_indicator": "text=申报成功",
            },
            "land_use_tax": {
                "menu_declare": "text=税费申报",
                "menu_item": "text=城镇土地使用税申报",
                "input_land_area": 'input[name="landArea"], input[placeholder*="面积"]',
                "input_tax_payable": 'input[name="landTax"], input[name*="tax"]',
                "btn_submit": "text=正式提交申报, button:has-text(\"申报\")",
                "btn_confirm": "text=确定, button:has-text(\"确定\")",
                "success_indicator": "text=申报成功",
            },
        },
    },
    "guangdong": {
        "name": "广东省电子税务局",
        "login_url": "https://etax.guangdong.chinatax.gov.cn/",
        "login_selectors": {
            "username": 'input[name="username"], input[placeholder*="税号"], input[placeholder*="用户名"]',
            "password": 'input[name="password"], input[type="password"]',
            "submit": 'button:has-text("登录"), button[type="submit"]',
            "captcha_img": "#captcha_img, img[src*=\"captcha\"]",
            "captcha_input": "#captcha, input[placeholder*=\"验证码\"]",
        },
        "filing_selectors": {
            "vat": {
                "menu_declare": "text=我要办税, text=税费申报",
                "menu_item": "text=增值税申报",
                "input_period_sales": 'input[name="salesAmount"], input[placeholder*="销售额"]',
                "input_tax_payable": 'input[name="taxAmount"], input[name*="tax"]',
                "btn_submit": "text=申报, button:has-text(\"申报\")",
                "btn_confirm": "text=确认, button:has-text(\"确认\")",
                "success_indicator": "text=申报成功",
            },
            "corporate_income": {
                "menu_declare": "text=我要办税, text=税费申报",
                "menu_item": "text=企业所得税申报, text=企业所得税月(季)度申报",
                "input_revenue": 'input[name="totalRevenue"], input[placeholder*="收入"]',
                "input_cost": 'input[name="totalCost"], input[placeholder*="成本"]',
                "input_profit": 'input[name="totalProfit"], input[placeholder*="利润"]',
                "input_tax_payable": 'input[name="incomeTaxPayable"], input[name*="tax"]',
                "btn_submit": "text=申报, button:has-text(\"申报\")",
                "btn_confirm": "text=确认, button:has-text(\"确认\")",
                "success_indicator": "text=申报成功",
            },
            "surtax": {
                "menu_declare": "text=我要办税",
                "menu_item": "text=附加税申报, text=附加税费申报",
                "input_vat_amount": 'input[name="vatAmount"], input[name*="vat"]',
                "btn_submit": "text=申报, button:has-text(\"申报\")",
                "btn_confirm": "text=确认, button:has-text(\"确认\")",
                "success_indicator": "text=申报成功",
            },
            "stamp_duty": {
                "menu_declare": "text=我要办税",
                "menu_item": "text=印花税申报",
                "input_taxable_amount": 'input[name="taxableAmount"]',
                "input_tax_payable": 'input[name="stampTax"]',
                "btn_submit": "text=申报, button:has-text(\"申报\")",
                "btn_confirm": "text=确认, button:has-text(\"确认\")",
                "success_indicator": "text=申报成功",
            },
            "property_tax": {
                "menu_declare": "text=我要办税",
                "menu_item": "text=房产税申报",
                "input_property_value": 'input[name="propertyValue"]',
                "input_tax_payable": 'input[name="propertyTax"]',
                "btn_submit": "text=申报, button:has-text(\"申报\")",
                "btn_confirm": "text=确认, button:has-text(\"确认\")",
                "success_indicator": "text=申报成功",
            },
            "land_use_tax": {
                "menu_declare": "text=我要办税",
                "menu_item": "text=城镇土地使用税申报",
                "input_land_area": 'input[name="landArea"]',
                "input_tax_payable": 'input[name="landTax"]',
                "btn_submit": "text=申报, button:has-text(\"申报\")",
                "btn_confirm": "text=确认, button:has-text(\"确认\")",
                "success_indicator": "text=申报成功",
            },
        },
    },
    "zhejiang": {
        "name": "浙江省电子税务局",
        "login_url": "https://etax.zhejiang.chinatax.gov.cn/",
        "login_selectors": {
            "username": 'input[name="username"], input[placeholder*="税号"], input[placeholder*="用户名"]',
            "password": 'input[name="password"], input[type="password"]',
            "submit": 'button:has-text("登录"), button[type="submit"]',
        },
        "filing_selectors": {
            "vat": {
                "menu_declare": "text=我要办税, text=税费申报",
                "menu_item": "text=增值税申报, text=增值税一般纳税人申报",
                "input_period_sales": 'input[name="sales"], input[placeholder*="销售额"]',
                "input_tax_payable": 'input[name="taxPayable"], input[name*="tax"]',
                "btn_submit": "text=申报, button:has-text(\"申报\")",
                "btn_confirm": "text=确认, button:has-text(\"确认\")",
                "success_indicator": "text=申报成功",
            },
            "corporate_income": {
                "menu_declare": "text=我要办税",
                "menu_item": "text=企业所得税月(季)度申报, text=企业所得税申报",
                "input_revenue": 'input[name="revenue"], input[placeholder*="收入"]',
                "input_cost": 'input[name="cost"], input[placeholder*="成本"]',
                "input_profit": 'input[name="profit"], input[placeholder*="利润"]',
                "input_tax_payable": 'input[name="tax"], input[name*="incomeTax"]',
                "btn_submit": "text=申报, button:has-text(\"申报\")",
                "btn_confirm": "text=确认, button:has-text(\"确认\")",
                "success_indicator": "text=申报成功",
            },
            "surtax": {
                "menu_declare": "text=我要办税",
                "menu_item": "text=附加税费申报, text=附加税申报",
                "input_vat_amount": 'input[name="vatAmount"], input[name*="vat"]',
                "btn_submit": "text=申报, button:has-text(\"申报\")",
                "btn_confirm": "text=确认, button:has-text(\"确认\")",
                "success_indicator": "text=申报成功",
            },
            "stamp_duty": {
                "menu_declare": "text=我要办税",
                "menu_item": "text=印花税申报",
                "input_taxable_amount": 'input[name="taxableAmount"]',
                "input_tax_payable": 'input[name="stampTax"]',
                "btn_submit": "text=申报, button:has-text(\"申报\")",
                "btn_confirm": "text=确认, button:has-text(\"确认\")",
                "success_indicator": "text=申报成功",
            },
            "property_tax": {
                "menu_declare": "text=我要办税",
                "menu_item": "text=房产税申报",
                "input_property_value": 'input[name="propertyValue"]',
                "input_tax_payable": 'input[name="propertyTax"]',
                "btn_submit": "text=申报, button:has-text(\"申报\")",
                "btn_confirm": "text=确认, button:has-text(\"确认\")",
                "success_indicator": "text=申报成功",
            },
            "land_use_tax": {
                "menu_declare": "text=我要办税",
                "menu_item": "text=城镇土地使用税申报",
                "input_land_area": 'input[name="landArea"]',
                "input_tax_payable": 'input[name="landTax"]',
                "btn_submit": "text=申报, button:has-text(\"申报\")",
                "btn_confirm": "text=确认, button:has-text(\"确认\")",
                "success_indicator": "text=申报成功",
            },
        },
    },
    "jiangsu": {
        "name": "江苏省电子税务局",
        "login_url": "https://etax.jiangsu.chinatax.gov.cn/",
        "login_selectors": {
            "username": 'input[name="username"], input[placeholder*="税号"], input[placeholder*="用户名"]',
            "password": 'input[name="password"], input[type="password"]',
            "submit": 'button:has-text("登录"), button[type="submit"]',
        },
        "filing_selectors": {
            "vat": {
                "menu_declare": "text=我要办税, text=税费申报",
                "menu_item": "text=增值税申报, text=增值税一般纳税人申报",
                "input_period_sales": 'input[name="salesAmount"], input[placeholder*="销售额"]',
                "input_tax_payable": 'input[name="taxAmount"], input[name*="tax"]',
                "btn_submit": "text=申报, button:has-text(\"申报\")",
                "btn_confirm": "text=确认, button:has-text(\"确认\")",
                "success_indicator": "text=申报成功",
            },
            "corporate_income": {
                "menu_declare": "text=我要办税",
                "menu_item": "text=居民企业所得税月(季)度申报, text=企业所得税申报",
                "input_revenue": 'input[name="revenue"], input[placeholder*="收入"]',
                "input_cost": 'input[name="cost"], input[placeholder*="成本"]',
                "input_profit": 'input[name="profit"], input[placeholder*="利润"]',
                "input_tax_payable": 'input[name="taxPayable"], input[name*="tax"]',
                "btn_submit": "text=申报, button:has-text(\"申报\")",
                "btn_confirm": "text=确认, button:has-text(\"确认\")",
                "success_indicator": "text=申报成功",
            },
            "surtax": {
                "menu_declare": "text=我要办税",
                "menu_item": "text=附加税申报, text=附加税费申报",
                "input_vat_amount": 'input[name="vatAmount"], input[name*="vat"]',
                "btn_submit": "text=申报, button:has-text(\"申报\")",
                "btn_confirm": "text=确认, button:has-text(\"确认\")",
                "success_indicator": "text=申报成功",
            },
            "stamp_duty": {
                "menu_declare": "text=我要办税",
                "menu_item": "text=印花税申报",
                "input_taxable_amount": 'input[name="taxableAmount"]',
                "input_tax_payable": 'input[name="stampTax"]',
                "btn_submit": "text=申报, button:has-text(\"申报\")",
                "btn_confirm": "text=确认, button:has-text(\"确认\")",
                "success_indicator": "text=申报成功",
            },
            "property_tax": {
                "menu_declare": "text=我要办税",
                "menu_item": "text=房产税申报",
                "input_property_value": 'input[name="propertyValue"]',
                "input_tax_payable": 'input[name="propertyTax"]',
                "btn_submit": "text=申报, button:has-text(\"申报\")",
                "btn_confirm": "text=确认, button:has-text(\"确认\")",
                "success_indicator": "text=申报成功",
            },
            "land_use_tax": {
                "menu_declare": "text=我要办税",
                "menu_item": "text=城镇土地使用税申报",
                "input_land_area": 'input[name="landArea"]',
                "input_tax_payable": 'input[name="landTax"]',
                "btn_submit": "text=申报, button:has-text(\"申报\")",
                "btn_confirm": "text=确认, button:has-text(\"确认\")",
                "success_indicator": "text=申报成功",
            },
        },
    },
    "generic": {
        "name": "通用电子税务局",
        "login_url": "",
        "login_selectors": {
            "username": '#username, input[name="username"], input[placeholder*="税号"], input[placeholder*="用户名"]',
            "password": '#password, input[name="password"], input[type="password"]',
            "submit": 'button[type="submit"], button:has-text("登录"), input[type="submit"]',
        },
        "filing_selectors": {
            "vat": {
                "menu_declare": 'text=我要办税, text=税费申报',
                "menu_item": 'text=增值税申报, text=增值税一般纳税人申报',
                "input_period_sales": '#sales, input[name*="sales"], input[placeholder*="销售额"]',
                "input_tax_payable": '#tax, input[name*="tax"], input[placeholder*="应纳税额"]',
                "btn_submit": 'text=申报, button:has-text("申报"), button:has-text("提交")',
                "btn_confirm": 'text=确认, button:has-text("确认"), button:has-text("确定")',
                "success_indicator": 'text=成功, text=申报成功, text=提交成功',
            },
            "corporate_income": {
                "menu_declare": 'text=我要办税, text=税费申报',
                "menu_item": 'text=企业所得税申报, text=企业所得税月(季)度申报',
                "input_revenue": '#revenue, input[name*="revenue"], input[placeholder*="收入"]',
                "input_cost": '#cost, input[name*="cost"], input[placeholder*="成本"]',
                "input_profit": '#profit, input[name*="profit"], input[placeholder*="利润"]',
                "input_tax_payable": '#incomeTax, input[name*="incomeTax"], input[name*="taxPayable"]',
                "btn_submit": 'text=申报, button:has-text("申报"), button:has-text("提交")',
                "btn_confirm": 'text=确认, button:has-text("确认"), button:has-text("确定")',
                "success_indicator": 'text=成功, text=申报成功',
            },
            "surtax": {
                "menu_declare": 'text=我要办税, text=税费申报',
                "menu_item": 'text=附加税申报, text=附加税费申报',
                "input_vat_amount": '#vatAmount, input[name*="vatAmount"], input[name*="vat"]',
                "btn_submit": 'text=申报, button:has-text("申报")',
                "btn_confirm": 'text=确认, button:has-text("确认")',
                "success_indicator": 'text=成功, text=申报成功',
            },
            "stamp_duty": {
                "menu_declare": 'text=我要办税, text=税费申报',
                "menu_item": 'text=印花税申报',
                "input_taxable_amount": '#taxableAmount, input[name*="taxableAmount"]',
                "input_tax_payable": '#stampTax, input[name*="stampTax"]',
                "btn_submit": 'text=申报, button:has-text("申报")',
                "btn_confirm": 'text=确认, button:has-text("确认")',
                "success_indicator": 'text=成功, text=申报成功',
            },
            "property_tax": {
                "menu_declare": 'text=我要办税, text=税费申报',
                "menu_item": 'text=房产税申报',
                "input_property_value": '#propertyValue, input[name*="propertyValue"]',
                "input_tax_payable": '#propertyTax, input[name*="propertyTax"]',
                "btn_submit": 'text=申报, button:has-text("申报")',
                "btn_confirm": 'text=确认, button:has-text("确认")',
                "success_indicator": 'text=成功, text=申报成功',
            },
            "land_use_tax": {
                "menu_declare": 'text=我要办税, text=税费申报',
                "menu_item": 'text=城镇土地使用税申报',
                "input_land_area": '#landArea, input[name*="landArea"]',
                "input_tax_payable": '#landTax, input[name*="landTax"]',
                "btn_submit": 'text=申报, button:has-text("申报")',
                "btn_confirm": 'text=确认, button:has-text("确认")',
                "success_indicator": 'text=成功, text=申报成功',
            },
        },
    },
}


@dataclass
class FilingResult:
    """申报结果"""
    success: bool
    message: str
    tax_type: str = ""
    period: str = ""
    screenshot_paths: list[str] = field(default_factory=list)
    transaction_id: str = ""
    filed_at: str = ""
    steps_completed: list[str] = field(default_factory=list)
    failed_step: str = ""
    error_detail: str = ""


class TaxAutomationEngine:
    """
    Playwright 自动申报引擎

    使用方式：
        engine = TaxAutomationEngine(profile="beijing", headless=False)
        result = await engine.run_filing(...)

    首次使用安装浏览器：
        playwright install chromium
    """

    def __init__(
        self,
        profile: str = "generic",
        headless: bool = False,
        screenshot_dir: str = "uploads/tax_screenshots",
        timeout: int = 30000,
    ):
        self.profile = profile
        self.config = TAX_BUREAU_CONFIGS.get(profile, TAX_BUREAU_CONFIGS["generic"])
        self.headless = headless
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.run_id = ""

    async def _screenshot(self, page, step: str) -> str:
        """截图留证"""
        path = self.screenshot_dir / f"{self.run_id}_{step}.png"
        await page.screenshot(path=str(path), full_page=True)
        return str(path)

    async def _save_debug(self, page, step: str) -> str:
        """保存调试信息（截图 + HTML）"""
        ss_path = await self._screenshot(page, step)
        html_path = self.screenshot_dir / f"{self.run_id}_{step}.html"
        try:
            html = await page.content()
            html_path.write_text(html, encoding="utf-8")
        except Exception:
            pass
        return ss_path

    async def _check_login_success(self, page) -> bool:
        """检测登录是否成功（失败特征：仍停留在登录页）"""
        login_indicators = [
            'input[type="password"]',
            'input[name="password"]',
            "#password",
            "text=登录",
            "text=验证码",
        ]
        count = 0
        for sel in login_indicators:
            try:
                if await page.locator(sel).count() > 0:
                    count += 1
            except Exception:
                pass
        return count < 2  # 少于 2 个登录特征 → 可能已登录

    async def _safe_click(self, page, selector: str, step_name: str = "") -> bool:
        """安全点击元素 — 支持逗号分隔的多策略回退链"""
        selectors = [s.strip() for s in selector.split(",") if s.strip()]
        for sel in selectors:
            try:
                await retry_with_backoff(
                    lambda s=sel: page.wait_for_selector(s, timeout=self.timeout),
                    max_retries=2,
                )
                await page.click(sel)
                return True
            except Exception:
                continue
        # 最终 fallback: text 匹配
        if step_name:
            try:
                await page.locator(f'text="{step_name}"').first.click(timeout=5000)
                return True
            except Exception:
                pass
        log_error("tax_auto", Exception(f"所有选择器均失败: {selector}"), {"step": step_name})
        return False

    async def _safe_fill(self, page, selector: str, value: str, step_name: str = "") -> bool:
        """安全填写输入框 — 支持逗号分隔的多策略回退链"""
        if not value:
            return True
        selectors = [s.strip() for s in selector.split(",") if s.strip()]
        for sel in selectors:
            try:
                await retry_with_backoff(
                    lambda s=sel: page.wait_for_selector(s, timeout=self.timeout),
                    max_retries=2,
                )
                await page.fill(sel, str(value))
                return True
            except Exception:
                continue
        # 最终 fallback: placeholder/name 模糊匹配
        if step_name:
            try:
                await page.locator(f'input[placeholder*="{step_name}"], input[name*="{step_name}"]').first.fill(str(value), timeout=5000)
                return True
            except Exception:
                pass
        log_error("tax_auto", Exception(f"所有选择器均失败: {selector}"), {"step": step_name, "value": str(value)[:50]})
        return False

    async def run_filing(
        self,
        tax_type: str,
        period: str,
        tax_data: dict,
        credentials: dict,
    ) -> FilingResult:
        """
        执行申报

        Args:
            tax_type: vat / corporate_income / surtax
            period: 2026-06
            tax_data: 申报数据（来自 tax_service.preview_filing）
            credentials: {"username": "税号/社会信用代码", "password": "登录密码"}

        Returns:
            FilingResult
        """
        self.run_id = uuid.uuid4().hex[:12]
        screenshots = []
        steps_completed = []
        failed_step = ""

        # --- 延迟导入，避免未安装 playwright 时阻塞 ---
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return FilingResult(
                success=False,
                message="未安装 Playwright。请运行: pip install playwright && playwright install chromium",
            )

        login_url = self.config["login_url"]
        if not login_url:
            return FilingResult(
                success=False,
                message=f"省份配置 [{self.profile}] 未设置 login_url，请在 TAX_BUREAU_CONFIGS 中补充",
            )

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
            )
            page = await context.new_page()

            try:
                # ===== Step 1: 登录 =====
                print(f"[自动申报] 登录 {self.config['name']}...")
                if not await safe_goto(page, login_url, timeout=self.timeout):
                    return FilingResult(
                        success=False,
                        message=f"无法访问 {self.config['name']} ({login_url})，请检查网络或URL配置",
                        failed_step="goto_login",
                    )

                login_s = self.config["login_selectors"]
                await self._safe_fill(page, login_s["username"], credentials.get("username", ""), "用户名")
                await self._safe_fill(page, login_s["password"], credentials.get("password", ""), "密码")

                # 检测验证码
                if await detect_captcha(page):
                    captcha_path = await self._screenshot(page, "captcha")
                    screenshots.append(captcha_path)
                    log_info("tax_auto", "captcha_detected", f"screenshot={captcha_path}")
                    print(f"[自动申报] ⚠️ 检测到验证码（截图: {captcha_path}），需人工处理")
                    if not self.headless:
                        captcha_input = login_s.get("captcha_input")
                        if captcha_input:
                            await page.wait_for_function(
                                f"document.querySelector('{captcha_input}')?.value?.length >= 4",
                                timeout=self.timeout * 2,
                            )

                await self._safe_click(page, login_s["submit"], "登录按钮")
                await page.wait_for_timeout(3000)

                login_ok = await self._check_login_success(page)
                await self._screenshot(page, "after_login")

                # 登录后检测风控
                anti_bot_risk = await detect_anti_bot(page)
                if anti_bot_risk:
                    await self._save_debug(page, f"anti_bot_{anti_bot_risk}")
                    return FilingResult(
                        success=False, tax_type=tax_type, period=period,
                        message=f"检测到风控限制({anti_bot_risk})，请稍后再试或切换网络环境",
                        screenshot_paths=screenshots, failed_step=f"anti_bot_{anti_bot_risk}",
                        steps_completed=steps_completed,
                    )
                screenshots.append(str(self.screenshot_dir / f"{self.run_id}_after_login.png"))

                if not login_ok:
                    await self._save_debug(page, "login_failed")
                    return FilingResult(
                        success=False, tax_type=tax_type, period=period,
                        message="登录失败：用户名或密码错误，或触发风控验证。请检查电子税务局凭据。",
                        screenshot_paths=screenshots, failed_step="login",
                        steps_completed=["goto_login", "fill_credentials"],
                    )

                steps_completed.append("login")
                log_info("tax_auto", "login_ok", f"profile={self.profile}")

                # ===== Step 2: 导航到申报页面 =====
                print(f"[自动申报] 导航到 {tax_type} 申报页面...")
                filing_configs = self.config.get("filing_selectors", {})
                filing_s = filing_configs.get(tax_type, filing_configs.get("vat", {}))
                steps_completed.append("navigate_menu")

                if not filing_s:
                    return FilingResult(
                        success=False,
                        message=f"不支持的税种: {tax_type}，当前只支持 vat / corporate_income / surtax",
                        steps_completed=steps_completed, failed_step="resolve_config",
                    )

                await self._safe_click(page, filing_s["menu_declare"], "我要办税")
                await page.wait_for_timeout(2000)
                await self._safe_click(page, filing_s["menu_item"], f"{tax_type}申报入口")
                await page.wait_for_timeout(3000)
                steps_completed.append("open_form")

                await self._screenshot(page, "filing_form")
                screenshots.append(str(self.screenshot_dir / f"{self.run_id}_filing_form.png"))

                # ===== Step 3: 填写申报数据 =====
                print(f"[自动申报] 填写申报数据 ({tax_type}): {json.dumps(tax_data, ensure_ascii=False)}")

                if tax_type == "vat":
                    await self._safe_fill(
                        page, filing_s.get("input_period_sales", "#sales"),
                        str(tax_data.get("period_sales", 0)), "销售额"
                    )
                    await self._safe_fill(
                        page, filing_s.get("input_tax_payable", "#tax"),
                        str(tax_data.get("tax_payable", 0)), "应纳税额"
                    )

                elif tax_type == "corporate_income":
                    await self._safe_fill(
                        page, filing_s.get("input_revenue", "#revenue"),
                        str(tax_data.get("total_revenue", 0)), "营业收入"
                    )
                    await self._safe_fill(
                        page, filing_s.get("input_cost", "#cost"),
                        str(tax_data.get("total_cost", 0)), "营业成本"
                    )
                    await self._safe_fill(
                        page, filing_s.get("input_profit", "#profit"),
                        str(tax_data.get("total_profit", 0)), "利润总额"
                    )
                    await self._safe_fill(
                        page, filing_s.get("input_tax_payable", "#incomeTax"),
                        str(tax_data.get("tax_payable", 0)), "应纳税所得额"
                    )

                elif tax_type == "surtax":
                    await self._safe_fill(
                        page, filing_s.get("input_vat_amount", "#vatAmount"),
                        str(tax_data.get("vat_paid", 0)), "实缴增值税"
                    )

                elif tax_type == "stamp_duty":
                    await self._safe_fill(
                        page, filing_s.get("input_taxable_amount", "#taxableAmount"),
                        str(tax_data.get("taxable_amount", 0)), "计税金额"
                    )
                    await self._safe_fill(
                        page, filing_s.get("input_tax_payable", "#stampTax"),
                        str(tax_data.get("tax_payable", 0)), "应纳税额"
                    )

                elif tax_type == "property_tax":
                    await self._safe_fill(
                        page, filing_s.get("input_property_value", "#propertyValue"),
                        str(tax_data.get("property_original_value", 0)), "房产原值"
                    )
                    await self._safe_fill(
                        page, filing_s.get("input_tax_payable", "#propertyTax"),
                        str(tax_data.get("tax_payable", 0)), "应纳税额"
                    )

                elif tax_type == "land_use_tax":
                    await self._safe_fill(
                        page, filing_s.get("input_land_area", "#landArea"),
                        str(tax_data.get("land_area", 0)), "占地面积"
                    )
                    await self._safe_fill(
                        page, filing_s.get("input_tax_payable", "#landTax"),
                        str(tax_data.get("tax_payable", 0)), "应纳税额"
                    )

                await self._screenshot(page, "filing_filled")
                screenshots.append(str(self.screenshot_dir / f"{self.run_id}_filing_filled.png"))

                # ===== Step 4: 提交申报 =====
                print("[自动申报] 提交申报...")
                steps_completed.append("fill_form")
                await self._safe_click(page, filing_s["btn_submit"], "提交申报")
                await page.wait_for_timeout(2000)

                # 确认弹窗
                await self._safe_click(page, filing_s["btn_confirm"], "确认提交")
                await page.wait_for_timeout(5000)
                steps_completed.append("submitted")

                # ===== Step 5: 验证结果 =====
                await self._screenshot(page, "filing_result")
                screenshots.append(str(self.screenshot_dir / f"{self.run_id}_filing_result.png"))

                success = await page.locator(filing_s.get("success_indicator", "text=成功")).count() > 0
                steps_completed.append("verify_result")

                result = FilingResult(
                    success=success,
                    message="申报成功" if success else "申报可能失败，请查看截图确认",
                    tax_type=tax_type,
                    period=period,
                    screenshot_paths=screenshots,
                    transaction_id=self.run_id,
                    filed_at=datetime.now().isoformat(),
                    steps_completed=steps_completed,
                )

            except Exception as e:
                log_error("tax_auto", e, {"tax_type": tax_type, "period": period, "run_id": self.run_id})
                failed_step = steps_completed[-1] if steps_completed else "unknown"
                try:
                    debug_path = await save_debug_snapshot(page, f"tax_auto_error_{self.run_id}_{failed_step}")
                    screenshots.append(debug_path)
                except Exception:
                    pass
                result = FilingResult(
                    success=False,
                    message=f"申报过程异常(步骤:{failed_step}): {str(e)[:150]}",
                    screenshot_paths=screenshots,
                    steps_completed=steps_completed,
                    failed_step=failed_step,
                    error_detail=str(e)[:500],
                )

            finally:
                await browser.close()

        print(f"[自动申报] 完成: {result.message}")
        return result


# ============================================================
# 便捷函数：同步调用（用于多线程场景）
# ============================================================

def run_filing_sync(
    profile: str,
    tax_type: str,
    period: str,
    tax_data: dict,
    credentials: dict,
    headless: bool = False,
) -> FilingResult:
    """同步包装器"""
    import asyncio
    engine = TaxAutomationEngine(profile=profile, headless=headless)
    return asyncio.run(engine.run_filing(tax_type, period, tax_data, credentials))
