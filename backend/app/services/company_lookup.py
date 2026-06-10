"""
企业信息自动查询 — 基于 Playwright 爬取国家企业信用信息公示系统
替代企查查/天眼查，零成本自动获取企业工商信息
"""
import asyncio
import re
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class CompanyInfo:
    """企业工商信息"""
    name: str = ""                    # 企业名称
    tax_no: str = ""                  # 统一社会信用代码
    legal_person: str = ""            # 法定代表人
    registered_capital: str = ""      # 注册资本
    paid_capital: str = ""            # 实缴资本
    established_date: str = ""        # 成立日期
    business_status: str = ""         # 经营状态（存续/在业/吊销/注销）
    company_type: str = ""            # 企业类型（有限责任公司等）
    industry: str = ""                # 所属行业
    address: str = ""                 # 注册地址
    business_scope: str = ""          # 经营范围
    registration_authority: str = ""  # 登记机关
    shareholders: list = field(default_factory=list)   # [{name, ratio, amount}]
    key_personnel: list = field(default_factory=list)  # [{name, title}]
    change_records: list = field(default_factory=list) # [{date, item, before, after}]
    annual_reports: list = field(default_factory=list) # [{year}]
    risk_info: list = field(default_factory=list)       # 风险信息
    source_url: str = ""              # 数据来源 URL


class CompanyLookup:
    """企业信息查询器"""

    GSXT_URL = "https://www.gsxt.gov.cn/index.html"
    GSXT_SEARCH = "https://www.gsxt.gov.cn/corp-query-search-1.html"
    # 备用：部分地区直连
    ALT_URLS = [
        "https://www.gsxt.gov.cn/",
        "http://gsxt.scjgj.beijing.gov.cn/",
    ]

    def __init__(self, headless: bool = True):
        self.headless = headless

    async def lookup(self, keyword: str) -> CompanyInfo:
        """根据企业名称或税号查询"""
        info = CompanyInfo()
        info.source_url = self.GSXT_SEARCH

        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=self.headless)
                context = await browser.new_context(
                    viewport={"width": 1400, "height": 900},
                    locale="zh-CN",
                )
                page = await context.new_page()

                # 导航到公示系统
                try:
                    await page.goto(self.GSXT_URL, timeout=30000, wait_until="domcontentloaded")
                    await asyncio.sleep(2)
                except Exception:
                    pass

                # 查找搜索框并输入
                search_selectors = [
                    'input[id*="keyword"]', 'input[name*="keyword"]',
                    'input[placeholder*="企业名称"]', 'input[placeholder*="统一社会信用代码"]',
                    'input[placeholder*="搜索"]', '#searchText', '.search-input input',
                ]
                filled = False
                for sel in search_selectors:
                    try:
                        el = page.locator(sel).first
                        if await el.count() > 0:
                            await el.click()
                            await el.fill(keyword)
                            filled = True
                            break
                    except Exception:
                        continue

                if not filled:
                    # 尝试直接打开搜索页
                    try:
                        await page.goto(self.GSXT_SEARCH, timeout=15000)
                        await asyncio.sleep(2)
                        for sel in search_selectors:
                            try:
                                el = page.locator(sel).first
                                if await el.count() > 0:
                                    await el.fill(keyword)
                                    filled = True
                                    break
                            except Exception:
                                continue
                    except Exception:
                        pass

                if not filled:
                    await browser.close()
                    return info

                # 点击搜索
                search_btns = [
                    'button:has-text("搜索")', 'button:has-text("查询")',
                    'input[type="submit"]', 'a:has-text("搜索")',
                    '.search-btn', '#searchBtn',
                ]
                for btn_sel in search_btns:
                    try:
                        btn = page.locator(btn_sel).first
                        if await btn.count() > 0:
                            await btn.click()
                            await asyncio.sleep(3)
                            break
                    except Exception:
                        continue

                # 等待搜索结果
                try:
                    await page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass

                # 解析结果列表，点击第一条
                result_selectors = [
                    '.search-result-item a', '.result-list a', '.company-item a',
                    'a:has-text("' + keyword[:6] + '")',
                    'tr a', 'table a',
                ]
                clicked = False
                for rs in result_selectors:
                    try:
                        el = page.locator(rs).first
                        if await el.count() > 0:
                            await el.click()
                            await asyncio.sleep(3)
                            clicked = True
                            break
                    except Exception:
                        continue

                if not clicked:
                    await browser.close()
                    return info

                # 等待详情页加载
                try:
                    await page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                await asyncio.sleep(1)

                # 提取页面文本
                page_text = ""
                try:
                    page_text = await page.inner_text("body")
                except Exception:
                    pass

                info.name = self._extract(page_text, r"企业名称[：:]\s*(.+)")
                info.tax_no = self._extract(page_text, r"统一社会信用代码[：:]\s*([A-Z0-9]{18})")
                info.legal_person = self._extract(page_text, r"法定代表人[：:]\s*(.+)")
                info.registered_capital = self._extract(page_text, r"注册资本[：:]\s*(.+)")
                info.established_date = self._extract(page_text, r"成立日期[：:]\s*(\d{4}[年-]\d{1,2}[月-]\d{1,2})")
                info.business_status = self._extract(page_text, r"登记状态[：:]\s*(.+)") or self._extract(page_text, r"经营状态[：:]\s*(.+)")
                info.company_type = self._extract(page_text, r"企业类型[：:]\s*(.+)")
                info.address = self._extract(page_text, r"(?:住\s*所|注册地址)[：:]\s*(.+)")
                info.business_scope = self._extract(page_text, r"经营范围[：:]\s*(.+?)(?:依法须经批准|\n)")
                info.registration_authority = self._extract(page_text, r"登记机关[：:]\s*(.+)")

                await browser.close()

        except ImportError:
            pass
        except Exception:
            pass

        return info

    def _extract(self, text: str, pattern: str) -> str:
        m = re.search(pattern, text)
        if m:
            return m.group(1).strip()[:300]
        return ""


async def lookup_company(keyword: str) -> CompanyInfo:
    """快捷查询"""
    return await CompanyLookup(headless=True).lookup(keyword)


def lookup_company_sync(keyword: str) -> CompanyInfo:
    return asyncio.run(lookup_company(keyword))
