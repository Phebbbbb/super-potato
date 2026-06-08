"""
Playwright 选择器验证脚本 — 检测硬编码 CSS 选择器在各省税局网站上是否仍然有效
用于 Hermes 定时巡检，发现失效选择器时输出报告供人工修复

用法:
    python scripts/check_selectors.py [--headless]

Hermes cron:
    每天凌晨 3:00 运行 → 如发现失效选择器，输出告警
"""
import json
import sys
import datetime
from pathlib import Path

# ===== 从 tax_automation.py 和 tax_invoice.py 提取的关键选择器 =====

CRITICAL_SELECTORS = {
    "tax_automation.py": {
        "beijing_login": [
            "#username", "#password", 'button[type="submit"]', "#captcha_img", "#captcha"
        ],
        "beijing_vat_filing": [
            "text=我要办税", "text=增值税申报",
            "#current_period_sales", "#tax_amount",
            "text=申报", "text=确认", "text=申报成功",
        ],
        "shanghai_login": [
            'input[name="username"]', 'input[name="password"]',
            'button:has-text("登录")',
        ],
        "shanghai_vat_filing": [
            "text=税费申报", "text=增值税一般纳税人申报",
            'input[name="sales"]', 'input[name="taxPayable"]',
            "text=正式提交申报", "text=确定", "text=申报成功",
        ],
        "guangdong_login": [
            'input[name="username"]', 'input[name="password"]',
            'button:has-text("登录")', "#captcha_img", "#captcha",
        ],
        "guangdong_vat_filing": [
            "text=我要办税", "text=增值税申报",
            'input[name="salesAmount"]', 'input[name="taxAmount"]',
            "text=申报", "text=确认", "text=申报成功",
        ],
    },
    "tax_invoice.py": {
        "beijing_login": [
            '#username, input[name="username"], input[placeholder*="税号"]',
            '#password, input[name="password"], input[type="password"]',
            'button[type="submit"], button:has-text("登录"), a:has-text("登录")',
        ],
        "beijing_invoice": [
            'button:has-text("开具"), a:has-text("蓝字发票开具"), button:has-text("新增")',
            'input[name*="buyerName"], input[placeholder*="购方名称"]',
            'input[name*="buyerTaxNo"], input[placeholder*="纳税人识别号"]',
            'button:has-text("开具"), button:has-text("提交")',
            "text=开具成功, text=提交成功, text=开票成功",
        ],
        "shanghai_login": [
            'input[name="username"], input[placeholder*="用户名"]',
            'input[name="password"], input[type="password"]',
            'button:has-text("登录"), input[type="submit"]',
        ],
        "shanghai_invoice": [
            'button:has-text("开具"), a:has-text("蓝字发票"), button:has-text("新增")',
            'input[name*="buyerName"], input[placeholder*="名称"]',
            'input[name*="buyerTaxNo"], input[placeholder*="税号"]',
        ],
    },
}

# 主要税局登录页 URL
TAX_BUREAU_URLS = {
    "beijing": "https://etax.beijing.chinatax.gov.cn/",
    "shanghai": "https://etax.shanghai.chinatax.gov.cn/",
    "guangdong": "https://etax.guangdong.chinatax.gov.cn/",
    "zhejiang": "https://etax.zhejiang.chinatax.gov.cn/",
    "jiangsu": "https://etax.jiangsu.chinatax.gov.cn/",
}


def check_selectors_on_page(page, selectors: list[str], label: str) -> list[dict]:
    """检查一组 CSS 选择器在页面上是否可定位"""
    results = []
    for sel in selectors:
        # 处理逗号分隔的 fallback 选择器
        parts = [s.strip() for s in sel.split(",")]
        found = False
        matched_part = ""
        for part in parts:
            try:
                count = page.locator(part).count()
                if count > 0:
                    found = True
                    matched_part = part
                    break
            except Exception:
                continue
        status = "ok" if found else "BROKEN"
        results.append({
            "selector": sel[:100],
            "matched": matched_part if found else "",
            "status": status,
            "group": label,
        })
    return results


def main():
    headless = "--headless" in sys.argv
    report = {
        "checked_at": datetime.datetime.now().isoformat(),
        "headless": headless,
        "results": [],
        "broken_count": 0,
        "total_count": 0,
    }

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        report["error"] = "Playwright not installed"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )
        page = context.new_page()

        for province, url in TAX_BUREAU_URLS.items():
            if not url:
                continue
            try:
                print(f"[检查] {province}: {url}")
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(3000)

                # 检查登录页面选择器
                login_key = f"{province}_login"
                for source_file, groups in CRITICAL_SELECTORS.items():
                    if login_key in groups:
                        results = check_selectors_on_page(
                            page, groups[login_key],
                            f"{source_file}/{login_key}"
                        )
                        report["results"].extend(results)

            except Exception as e:
                report["results"].append({
                    "selector": url,
                    "matched": "",
                    "status": "UNREACHABLE",
                    "group": f"{province}_url",
                    "error": str(e)[:150],
                })

        browser.close()

    # 统计
    report["total_count"] = len(report["results"])
    report["broken_count"] = sum(
        1 for r in report["results"] if r["status"] in ("BROKEN", "UNREACHABLE")
    )
    report["ok_count"] = report["total_count"] - report["broken_count"]

    print(json.dumps(report, ensure_ascii=False, indent=2))

    if report["broken_count"] > 0:
        print(f"\n⚠️  {report['broken_count']}/{report['total_count']} 选择器已失效，需要更新！")
        return 1
    else:
        print(f"\n✅ 全部 {report['total_count']} 个选择器验证通过")
        return 0


if __name__ == "__main__":
    sys.exit(main())
