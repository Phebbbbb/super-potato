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
from app.services.playwright_helpers import (
    detect_captcha, detect_anti_bot, retry_with_backoff, safe_goto, save_debug_snapshot,
    is_session_valid, save_session, ensure_valid_session, SessionExpired,
    SESSION_DIR, SESSION_MAX_AGE_MINUTES,
)
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

# ===== 新增税种选择器（通用，合并到所有省级 Profile） =====
_NEW_TAX_SELECTORS = {
    "consumption_tax": {
        "menu_declare": "text=我要办税, text=税费申报",
        "menu_item": "text=消费税申报",
        "input_taxable_amount": '#taxableAmount, input[name*="taxableAmount"], input[placeholder*="计税"]',
        "input_tax_payable": '#taxPayable, input[name*="tax"], input[placeholder*="消费税"]',
        "btn_submit": 'text=申报, button:has-text("申报"), button:has-text("提交")',
        "btn_confirm": 'text=确认, button:has-text("确认"), button:has-text("确定")',
        "success_indicator": 'text=申报成功, text=提交成功',
    },
    "individual_income": {
        "menu_declare": "text=我要办税, text=税费申报",
        "menu_item": "text=个人所得税申报, text=个税申报, text=个人所得税扣缴",
        "input_taxable_amount": '#taxableAmount, input[name*="taxableAmount"], input[placeholder*="应纳税所得额"]',
        "input_tax_payable": '#taxPayable, input[name*="tax"], input[placeholder*="个税"]',
        "btn_submit": 'text=申报, button:has-text("申报"), button:has-text("提交")',
        "btn_confirm": 'text=确认, button:has-text("确认"), button:has-text("确定")',
        "success_indicator": 'text=申报成功, text=提交成功',
    },
    "land_appreciation_tax": {
        "menu_declare": "text=我要办税, text=税费申报",
        "menu_item": "text=土地增值税申报, text=土增税申报",
        "input_taxable_amount": '#transferIncome, input[name*="transferIncome"], input[placeholder*="转让收入"]',
        "input_tax_payable": '#taxPayable, input[name*="tax"], input[placeholder*="土地增值税"]',
        "btn_submit": 'text=申报, button:has-text("申报"), button:has-text("提交")',
        "btn_confirm": 'text=确认, button:has-text("确认"), button:has-text("确定")',
        "success_indicator": 'text=申报成功, text=提交成功',
    },
    "deed_tax": {
        "menu_declare": "text=我要办税, text=税费申报",
        "menu_item": "text=契税申报",
        "input_taxable_amount": '#taxableAmount, input[name*="taxableAmount"], input[placeholder*="成交价格"]',
        "input_tax_payable": '#taxPayable, input[name*="tax"], input[placeholder*="契税"]',
        "btn_submit": 'text=申报, button:has-text("申报"), button:has-text("提交")',
        "btn_confirm": 'text=确认, button:has-text("确认"), button:has-text("确定")',
        "success_indicator": 'text=申报成功, text=提交成功',
    },
    "vehicle_vessel_tax": {
        "menu_declare": "text=我要办税, text=税费申报",
        "menu_item": "text=车船税申报",
        "input_taxable_amount": '#vehicleCount, input[name*="vehicleCount"], input[placeholder*="车辆"]',
        "input_tax_payable": '#taxPayable, input[name*="tax"], input[placeholder*="车船税"]',
        "btn_submit": 'text=申报, button:has-text("申报"), button:has-text("提交")',
        "btn_confirm": 'text=确认, button:has-text("确认"), button:has-text("确定")',
        "success_indicator": 'text=申报成功, text=提交成功',
    },
    "vehicle_purchase_tax": {
        "menu_declare": "text=我要办税, text=税费申报",
        "menu_item": "text=车辆购置税申报",
        "input_taxable_amount": '#taxableAmount, input[name*="taxableAmount"], input[placeholder*="计税价格"]',
        "input_tax_payable": '#taxPayable, input[name*="tax"], input[placeholder*="车辆购置税"]',
        "btn_submit": 'text=申报, button:has-text("申报"), button:has-text("提交")',
        "btn_confirm": 'text=确认, button:has-text("确认"), button:has-text("确定")',
        "success_indicator": 'text=申报成功, text=提交成功',
    },
    "resource_tax": {
        "menu_declare": "text=我要办税, text=税费申报",
        "menu_item": "text=资源税申报",
        "input_taxable_amount": '#taxableAmount, input[name*="taxableAmount"], input[placeholder*="销售额"]',
        "input_tax_payable": '#taxPayable, input[name*="tax"], input[placeholder*="资源税"]',
        "btn_submit": 'text=申报, button:has-text("申报"), button:has-text("提交")',
        "btn_confirm": 'text=确认, button:has-text("确认"), button:has-text("确定")',
        "success_indicator": 'text=申报成功, text=提交成功',
    },
    "environmental_tax": {
        "menu_declare": "text=我要办税, text=税费申报",
        "menu_item": "text=环境保护税申报, text=环保税申报",
        "input_pollution_equivalent": '#pollutionEquiv, input[name*="pollution"], input[placeholder*="当量"]',
        "input_tax_payable": '#taxPayable, input[name*="tax"], input[placeholder*="环保税"]',
        "btn_submit": 'text=申报, button:has-text("申报"), button:has-text("提交")',
        "btn_confirm": 'text=确认, button:has-text("确认"), button:has-text("确定")',
        "success_indicator": 'text=申报成功, text=提交成功',
    },
    "farmland_occupation_tax": {
        "menu_declare": "text=我要办税, text=税费申报",
        "menu_item": "text=耕地占用税申报",
        "input_land_area": '#landArea, input[name*="landArea"], input[placeholder*="面积"]',
        "input_tax_payable": '#taxPayable, input[name*="tax"], input[placeholder*="耕地占用税"]',
        "btn_submit": 'text=申报, button:has-text("申报"), button:has-text("提交")',
        "btn_confirm": 'text=确认, button:has-text("确认"), button:has-text("确定")',
        "success_indicator": 'text=申报成功, text=提交成功',
    },
    "tobacco_tax": {
        "menu_declare": "text=我要办税, text=税费申报",
        "menu_item": "text=烟叶税申报",
        "input_taxable_amount": '#taxableAmount, input[name*="taxableAmount"], input[placeholder*="收购金额"]',
        "input_tax_payable": '#taxPayable, input[name*="tax"], input[placeholder*="烟叶税"]',
        "btn_submit": 'text=申报, button:has-text("申报"), button:has-text("提交")',
        "btn_confirm": 'text=确认, button:has-text("确认"), button:has-text("确定")',
        "success_indicator": 'text=申报成功, text=提交成功',
    },
    "customs_duty": {
        "menu_declare": "text=我要办税, text=税费申报",
        "menu_item": "text=关税申报",
        "input_taxable_amount": '#taxableAmount, input[name*="taxableAmount"], input[placeholder*="完税价格"]',
        "input_tax_payable": '#taxPayable, input[name*="tax"], input[placeholder*="关税"]',
        "btn_submit": 'text=申报, button:has-text("申报"), button:has-text("提交")',
        "btn_confirm": 'text=确认, button:has-text("确认"), button:has-text("确定")',
        "success_indicator": 'text=申报成功, text=提交成功',
    },
}

# 合并到所有省份配置
for _profile_name, _profile_config in TAX_BUREAU_CONFIGS.items():
    if "filing_selectors" in _profile_config:
        _profile_config["filing_selectors"].update(_NEW_TAX_SELECTORS)

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

        session_file = str(SESSION_DIR / f"{self.profile}_session.json")
        use_saved_session = is_session_valid(self.profile)
        should_headless = self.headless and use_saved_session

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=should_headless)
            context_kwargs: dict = {"viewport": {"width": 1920, "height": 1080}, "locale": "zh-CN"}
            if use_saved_session and Path(session_file).exists():
                context_kwargs["storage_state"] = session_file
                log_info("tax_auto", "session_reuse", f"profile={self.profile}")

            context = await browser.new_context(**context_kwargs)
            page = await context.new_page()

            try:
                # ===== Step 0: Session 管理 =====
                log_info("tax_auto", "session_mgmt", f"profile={self.profile} saved={use_saved_session} headless={should_headless}")
                session_ok = use_saved_session

                if not use_saved_session:
                    if should_headless:
                        return FilingResult(
                            success=False,
                            message=f"{self.profile} 无有效 session，请先通过 API 触发一次人工登录。Session 有效期约 {SESSION_MAX_AGE_MINUTES} 分钟。",
                            failed_step="no_session",
                        )
                    session_ok = await ensure_valid_session(
                        context=context, page=page, province=self.profile,
                        login_url=login_url,
                        target_url=login_url,  # 登录后的起始页就是 login_url 跳转后的页面
                        login_selectors=self.config["login_selectors"],
                        credentials=credentials,
                    )
                    if not session_ok:
                        return FilingResult(
                            success=False, tax_type=tax_type, period=period,
                            message=f"{self.config['name']} 登录失败或超时",
                            screenshot_paths=screenshots, failed_step="login",
                        )

                if not session_ok:
                    return FilingResult(
                        success=False, tax_type=tax_type, period=period,
                        message="Session 无效且无法重新登录",
                        screenshot_paths=screenshots, failed_step="session",
                    )

                # 检测反爬
                anti_bot_risk = await detect_anti_bot(page)
                if anti_bot_risk:
                    await self._save_debug(page, f"anti_bot_{anti_bot_risk}")
                    return FilingResult(
                        success=False, tax_type=tax_type, period=period,
                        message=f"检测到风控限制({anti_bot_risk})，请稍后再试或切换网络环境",
                        screenshot_paths=screenshots, failed_step=f"anti_bot_{anti_bot_risk}",
                        steps_completed=steps_completed,
                    )

                await self._screenshot(page, "after_login")
                screenshots.append(str(self.screenshot_dir / f"{self.run_id}_after_login.png"))

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
                        message=f"该税种暂不支持自动申报: {tax_type}，请选择手动申报或等待功能更新",
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

                else:
                    # 通用填报：按 tax_data 中的字段自动填充
                    for key, val in tax_data.items():
                        if key in ("tax_type", "period", "message", "note"):
                            continue
                        selector = filing_s.get(f"input_{key}", f"#{key}")
                        await self._safe_fill(page, selector, str(val), key)

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

                # 刷新 session 有效期
                if success:
                    await save_session(context, self.profile)

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


    async def run_filing_with_checkpoints(
        self,
        tax_type: str,
        period: str,
        tax_data: dict,
        credentials: dict,
    ) -> FilingResult:
        """
        带检查点恢复的申报执行 — 每个步骤自动保存检查点，失败时从断点恢复

        与 run_filing 的区别：
          - 每个步骤执行前保存检查点（URL + cookies + screenshot）
          - 步骤失败时自动从上一个检查点恢复，而非从头重试
          - 幂等步骤（fill_form, submit）可安全重试
          - 非幂等步骤失败时跳过，继续后续步骤
        """
        from app.services.automation_checkpoint import (
            CheckpointEngine, AutomationStep, AutomationRun, get_checkpoint_engine,
        )

        self.run_id = uuid.uuid4().hex[:12]
        screenshots = []
        steps_completed = []
        failed_step = ""

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
                message=f"省份配置 [{self.profile}] 未设置 login_url",
            )

        checkpoint_engine = get_checkpoint_engine()

        session_file = str(SESSION_DIR / f"{self.profile}_session.json")
        use_saved_session = is_session_valid(self.profile)
        should_headless = self.headless and use_saved_session

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=should_headless)
            context_kwargs: dict = {"viewport": {"width": 1920, "height": 1080}, "locale": "zh-CN"}
            if use_saved_session and Path(session_file).exists():
                context_kwargs["storage_state"] = session_file

            context = await browser.new_context(**context_kwargs)
            page = await context.new_page()

            try:
                # 定义步骤（含幂等性标记）
                login_s = self.config["login_selectors"]
                filing_configs = self.config.get("filing_selectors", {})
                filing_s = filing_configs.get(tax_type, filing_configs.get("vat", {}))

                # 构建步骤函数闭包（session-first）
                async def step_login(p):
                    if use_saved_session:
                        # 已有 session，验证可用性
                        try:
                            await p.goto(login_url, timeout=self.timeout, wait_until="domcontentloaded")
                            await p.wait_for_timeout(2000)
                            if await self._check_login_success(p):
                                return True
                        except Exception:
                            pass
                        # session 过期，回退到交互式登录
                        return await ensure_valid_session(
                            context=context, page=p, province=self.profile,
                            login_url=login_url, target_url=login_url,
                            login_selectors=login_s, credentials=credentials,
                        )
                    else:
                        return await ensure_valid_session(
                            context=context, page=p, province=self.profile,
                            login_url=login_url, target_url=login_url,
                            login_selectors=login_s, credentials=credentials,
                        )

                async def step_navigate(p):
                    await self._safe_click(p, filing_s.get("menu_declare", ""), "我要办税")
                    await p.wait_for_timeout(2000)
                    await self._safe_click(p, filing_s.get("menu_item", ""), f"{tax_type}申报入口")
                    await p.wait_for_timeout(3000)
                    await self._screenshot(p, "filing_form")
                    return True

                async def step_fill(p):
                    if tax_type == "vat":
                        await self._safe_fill(p, filing_s.get("input_period_sales", ""), str(tax_data.get("period_sales", 0)), "销售额")
                        await self._safe_fill(p, filing_s.get("input_tax_payable", ""), str(tax_data.get("tax_payable", 0)), "应纳税额")
                    elif tax_type == "corporate_income":
                        await self._safe_fill(p, filing_s.get("input_revenue", ""), str(tax_data.get("total_revenue", 0)), "营业收入")
                        await self._safe_fill(p, filing_s.get("input_cost", ""), str(tax_data.get("total_cost", 0)), "营业成本")
                        await self._safe_fill(p, filing_s.get("input_profit", ""), str(tax_data.get("total_profit", 0)), "利润总额")
                        await self._safe_fill(p, filing_s.get("input_tax_payable", ""), str(tax_data.get("tax_payable", 0)), "应纳税所得额")
                    elif tax_type == "surtax":
                        await self._safe_fill(p, filing_s.get("input_vat_amount", ""), str(tax_data.get("vat_paid", 0)), "实缴增值税")
                    elif tax_type == "stamp_duty":
                        await self._safe_fill(p, filing_s.get("input_taxable_amount", ""), str(tax_data.get("taxable_amount", 0)), "计税金额")
                        await self._safe_fill(p, filing_s.get("input_tax_payable", ""), str(tax_data.get("tax_payable", 0)), "应纳税额")
                    elif tax_type == "property_tax":
                        await self._safe_fill(p, filing_s.get("input_property_value", ""), str(tax_data.get("property_original_value", 0)), "房产原值")
                        await self._safe_fill(p, filing_s.get("input_tax_payable", ""), str(tax_data.get("tax_payable", 0)), "应纳税额")
                    elif tax_type == "land_use_tax":
                        await self._safe_fill(p, filing_s.get("input_land_area", ""), str(tax_data.get("land_area", 0)), "占地面积")
                        await self._safe_fill(p, filing_s.get("input_tax_payable", ""), str(tax_data.get("tax_payable", 0)), "应纳税额")
                    else:
                        for key, val in tax_data.items():
                            if key in ("tax_type", "period", "message", "note"):
                                continue
                            selector = filing_s.get(f"input_{key}", f"#{key}")
                            await self._safe_fill(p, selector, str(val), key)
                    return True

                async def step_submit(p):
                    await self._safe_click(p, filing_s.get("btn_submit", ""), "提交申报")
                    await p.wait_for_timeout(2000)
                    await self._safe_click(p, filing_s.get("btn_confirm", ""), "确认提交")
                    await p.wait_for_timeout(5000)
                    return True

                async def step_verify(p):
                    await self._screenshot(p, "filing_result")
                    count = await p.locator(filing_s.get("success_indicator", "text=成功")).count()
                    return count > 0

                steps = [
                    AutomationStep("login", fn=step_login, is_idempotent=False, max_retries=1),
                    AutomationStep("navigate", fn=step_navigate, is_idempotent=True, max_retries=2),
                    AutomationStep("fill_form", fn=step_fill, is_idempotent=True, max_retries=2),
                    AutomationStep("submit", fn=step_submit, is_idempotent=False, max_retries=1),
                    AutomationStep("verify", fn=step_verify, is_idempotent=True, max_retries=1),
                ]

                run = checkpoint_engine.create_run("filing", steps)
                cp_result = await checkpoint_engine.execute(run, page, context)

                if cp_result["success"]:
                    result = FilingResult(
                        success=True,
                        message=f"申报成功（含 {cp_result['checkpoints']} 个检查点）",
                        tax_type=tax_type, period=period,
                        screenshot_paths=screenshots,
                        transaction_id=self.run_id,
                        filed_at=datetime.now().isoformat(),
                        steps_completed=[s.name for s in steps],
                    )
                else:
                    result = FilingResult(
                        success=False,
                        message=cp_result["message"],
                        tax_type=tax_type, period=period,
                        screenshot_paths=screenshots,
                        failed_step=cp_result.get("failed_step", ""),
                        steps_completed=[s.name for s in steps[:cp_result.get("step_index", 0)]],
                        error_detail=cp_result["message"],
                    )

            except Exception as e:
                log_error("tax_auto_cp", e, {"tax_type": tax_type, "period": period, "run_id": self.run_id})
                try:
                    debug_path = await save_debug_snapshot(page, f"tax_auto_cp_error_{self.run_id}")
                    screenshots.append(debug_path)
                except Exception:
                    pass
                result = FilingResult(
                    success=False,
                    message=f"申报异常: {str(e)[:150]}",
                    screenshot_paths=screenshots,
                    error_detail=str(e)[:500],
                )

            finally:
                await browser.close()

        print(f"[自动申报-CP] 完成: {result.message}")
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
