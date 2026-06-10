"""
工商业务自动化引擎 — Playwright 驱动 + 自学习
覆盖：工商年报自动填报 / 企业信息爬取 / 表单自动填充 / 进度追踪
"""
import json
import re
import time
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any

# ===== 自学习知识库 =====
LEARNING_DB = Path(__file__).parent / "business_learning.json"


def _load_learning() -> dict:
    if LEARNING_DB.exists():
        try:
            return json.loads(LEARNING_DB.read_text("utf-8"))
        except Exception:
            pass
    return {"selectors": {}, "patterns": {}, "success_count": 0, "field_mappings": {}}


def _save_learning(data: dict):
    LEARNING_DB.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def learn_selector(task: str, field: str, selector: str, success: bool):
    """记录选择器学习结果"""
    data = _load_learning()
    key = f"{task}.{field}"
    if key not in data["selectors"]:
        data["selectors"][key] = []
    entry = {"selector": selector, "success": success, "ts": datetime.now(timezone.utc).isoformat()}
    # 成功的选择器移到最前面
    if success:
        data["selectors"][key] = [e for e in data["selectors"][key] if e["selector"] != selector]
        data["selectors"][key].insert(0, entry)
        data["success_count"] += 1
    else:
        data["selectors"][key].append(entry)
    # 限制每个 key 最多保留 20 条
    data["selectors"][key] = data["selectors"][key][:20]
    _save_learning(data)


def learn_field_mapping(task: str, label: str, value: str):
    """记录字段标签到填充值的映射"""
    data = _load_learning()
    key = f"{task}.mappings"
    if key not in data["field_mappings"]:
        data["field_mappings"][key] = {}
    data["field_mappings"][key][label] = value
    _save_learning(data)


def get_learned_selectors(task: str, field: str) -> list[str]:
    """获取已学习的成功选择器（优先）"""
    data = _load_learning()
    key = f"{task}.{field}"
    entries = data.get("selectors", {}).get(key, [])
    return [e["selector"] for e in entries if e["success"]]


def get_learning_stats() -> dict:
    data = _load_learning()
    return {
        "success_count": data.get("success_count", 0),
        "tasks_learned": len(data.get("selectors", {})),
        "field_mappings": len(data.get("field_mappings", {}).get("annual_report.mappings", {})),
    }


# ===== 自动化结果模型 =====

@dataclass
class AutoResult:
    success: bool
    task: str
    message: str = ""
    data: dict = field(default_factory=dict)
    screenshots: list[str] = field(default_factory=list)
    duration_seconds: float = 0
    learned: bool = False  # 是否触发了学习


# ===== 核心自动化引擎 =====

class BusinessAutomation:
    """工商业务自动化引擎"""

    OFFICIAL_URLS = {
        "annual_report": "https://www.gsxt.gov.cn/corp-query-search-1.html",
        "registration": "https://zwfw.samr.gov.cn/",
        "company_lookup": "https://www.gsxt.gov.cn/index.html",
    }

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.screenshot_dir = Path("screenshots/business")
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    # ========== 工商年报自动填报 ==========

    async def auto_fill_annual_report(
        self,
        company_name: str,
        report_data: dict,
        credentials: dict = None,
    ) -> AutoResult:
        """
        自动填报工商年报
        report_data: {year, revenue, profit, assets, tax_total, employees, ...}
        """
        start = time.time()
        screenshots: list[str] = []
        result = AutoResult(success=False, task="annual_report")

        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=self.headless)
                ctx = await browser.new_context(viewport={"width": 1400, "height": 900}, locale="zh-CN")
                page = await ctx.new_page()

                # 导航到公示系统
                await self._safe_goto(page, self.OFFICIAL_URLS["annual_report"])
                await asyncio.sleep(2)
                screenshots.append(await self._shot(page, "01_home"))

                # 搜索企业
                await self._smart_fill(page, "annual_report", "search_keyword", company_name)
                await self._smart_click(page, "annual_report", "search_btn")
                await self._wait_stable(page, timeout=8)
                screenshots.append(await self._shot(page, "02_search_result"))

                # 点击企业进入详情
                await self._smart_click(page, "annual_report", "company_link")
                await self._wait_stable(page, timeout=8)
                screenshots.append(await self._shot(page, "03_company_detail"))

                # 找到年报填报入口
                await self._smart_click(page, "annual_report", "annual_report_tab")
                await self._wait_stable(page, timeout=5)

                # 选择年份
                year = report_data.get("year", str(datetime.now().year - 1))
                await self._smart_fill(page, "annual_report", "report_year", year)

                # === 填报各字段 ===
                field_mappings = self._get_annual_report_field_mappings()

                for field_key, form_value in report_data.items():
                    if field_key in field_mappings:
                        selector_info = field_mappings[field_key]
                        await self._fill_by_strategy(page, "annual_report", field_key,
                                                     str(form_value), selector_info)
                        await asyncio.sleep(0.3)

                screenshots.append(await self._shot(page, "04_form_filled"))

                # 预览/暂存（不直接提交，需人工确认）
                await self._smart_click(page, "annual_report", "preview_btn")
                await self._wait_stable(page, timeout=5)
                screenshots.append(await self._shot(page, "05_preview"))

                # 记录学习
                for field_key in report_data:
                    if field_key in field_mappings:
                        learn_field_mapping("annual_report", field_key, str(report_data[field_key]))

                await browser.close()

                result.success = True
                result.message = f"工商年报 {year} 已自动填报（待人工确认提交）"
                result.data = {"year": year, "company": company_name, "status": "filled_pending_review"}
                result.learned = True

        except ImportError:
            result.message = "Playwright 未安装，无法执行自动化"
        except Exception as e:
            result.message = f"自动填报异常: {str(e)[:200]}"
            # 失败时也学习：记录失败的 selector
            learn_selector("annual_report", "search_keyword", "input[placeholder*='企业名称']", False)

        result.duration_seconds = round(time.time() - start, 1)
        result.screenshots = screenshots
        return result

    # ========== 企业信息自动采集（增强版 + 自学习）==========

    async def auto_lookup_company(self, keyword: str) -> AutoResult:
        """自动查询企业工商信息（增强版，含自学习）"""
        start = time.time()
        screenshots: list[str] = []
        result = AutoResult(success=False, task="company_lookup")

        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=self.headless)
                ctx = await browser.new_context(viewport={"width": 1400, "height": 900}, locale="zh-CN")
                page = await ctx.new_page()

                await self._safe_goto(page, self.OFFICIAL_URLS["company_lookup"])
                await asyncio.sleep(3)
                screenshots.append(await self._shot(page, "01_gsxt_home"))

                # 智能定位搜索框（优先用已学习的 selector）
                await self._smart_fill(page, "company_lookup", "keyword", keyword)
                await self._smart_click(page, "company_lookup", "search_btn")
                await asyncio.sleep(4)
                screenshots.append(await self._shot(page, "02_search_done"))

                # 点击第一个结果
                await self._smart_click(page, "company_lookup", "first_result")
                await asyncio.sleep(3)
                screenshots.append(await self._shot(page, "03_detail_page"))

                # 提取信息
                page_text = await page.inner_text("body")
                info = self._parse_company_info(page_text, keyword)
                result.data = info

                await browser.close()

                result.success = bool(info.get("name"))
                result.message = f"已查询到 {info.get('name', keyword)} 的工商信息"
                result.learned = True

        except ImportError:
            result.message = "Playwright 未安装"
        except Exception as e:
            result.message = f"查询异常: {str(e)[:200]}"

        result.duration_seconds = round(time.time() - start, 1)
        result.screenshots = screenshots
        return result

    # ========== 官网表单自动生成 ==========

    def generate_filled_forms(self, task_type: str, client_data: dict) -> dict:
        """
        根据客户数据自动生成预填好的表单（供下载/打印）
        支持：registration（注册）、deregistration（注销）、equity（股权变更）
        """
        if task_type == "registration":
            return {
                "form_name": "公司登记（备案）申请书",
                "fields": {
                    "公司名称": client_data.get("company_name", ""),
                    "住所": client_data.get("address", ""),
                    "法定代表人": client_data.get("legal_person", ""),
                    "注册资本": f"{client_data.get('registered_capital', 0)}万元",
                    "经营范围": client_data.get("business_scope", ""),
                    "股东姓名/名称": client_data.get("shareholders", ""),
                    "联系电话": client_data.get("contact_phone", ""),
                },
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "official_url": "https://zwfw.samr.gov.cn/",
            }
        elif task_type == "deregistration":
            return {
                "form_name": "企业注销登记申请书",
                "fields": {
                    "公司名称": client_data.get("company_name", ""),
                    "统一社会信用代码": client_data.get("tax_no", ""),
                    "注销原因": client_data.get("reason", ""),
                    "税务清税情况": "已结清" if client_data.get("tax_cleared") else "未结清",
                    "债务清偿情况": "已清偿" if client_data.get("debt_cleared") else "未清偿",
                    "公告日期": client_data.get("announcement_date", ""),
                },
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "official_url": "https://www.gsxt.gov.cn/",
            }
        elif task_type == "equity":
            return {
                "form_name": "公司变更登记申请书（股权变更）",
                "fields": {
                    "公司名称": client_data.get("company_name", ""),
                    "变更类型": {"transfer": "股权转让", "increase": "增资", "decrease": "减资"}.get(
                        client_data.get("change_type", ""), client_data.get("change_type", "")
                    ),
                    "转让方": client_data.get("from_person", ""),
                    "受让方": client_data.get("to_person", ""),
                    "转让比例": f"{client_data.get('ratio', 0)}%",
                    "转让金额": f"{client_data.get('amount', 0)}万元",
                    "生效日期": client_data.get("effective_date", ""),
                },
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "official_url": "https://zwfw.samr.gov.cn/",
            }
        return {"error": "未知任务类型"}

    # ========== 内部辅助方法 ==========

    async def _safe_goto(self, page, url: str, timeout: int = 30000):
        """安全导航（带重试）"""
        for attempt in range(3):
            try:
                await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
                return
            except Exception:
                if attempt == 2:
                    raise
                await asyncio.sleep(2)

    async def _wait_stable(self, page, timeout: int = 10):
        """等待页面稳定"""
        try:
            await page.wait_for_load_state("networkidle", timeout=timeout * 1000)
        except Exception:
            pass
        await asyncio.sleep(1)

    async def _shot(self, page, name: str) -> str:
        """截图并返回路径"""
        ts = datetime.now().strftime("%H%M%S")
        path = str(self.screenshot_dir / f"{ts}_{name}.png")
        try:
            await page.screenshot(path=path, full_page=False)
        except Exception:
            pass
        return path

    async def _smart_fill(self, page, task: str, field: str, value: str):
        """智能填充：优先已学习的 selector，然后 fallback 链"""
        # 1. 尝试已学习的成功 selector
        learned = get_learned_selectors(task, field)
        for sel in learned[:5]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click()
                    await el.fill(value)
                    learn_selector(task, field, sel, True)
                    return
            except Exception:
                learn_selector(task, field, sel, False)

        # 2. Fallback 链
        fallbacks = self._get_fallback_selectors(task, field)
        for sel in fallbacks:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click()
                    await el.fill(value)
                    learn_selector(task, field, sel, True)
                    return
            except Exception:
                continue

        # 3. 通用兜底：遍历所有 input
        try:
            inputs = page.locator("input:visible")
            count = await inputs.count()
            for i in range(min(count, 30)):
                inp = inputs.nth(i)
                placeholder = await inp.get_attribute("placeholder") or ""
                name = await inp.get_attribute("name") or ""
                label = await inp.get_attribute("aria-label") or ""
                combined = f"{placeholder}{name}{label}".lower()
                if any(kw in combined for kw in field.split("_")):
                    await inp.fill(value)
                    sel_desc = f"input:nth({i})"
                    learn_selector(task, field, sel_desc, True)
                    return
        except Exception:
            pass

    async def _smart_click(self, page, task: str, field: str):
        """智能点击：优先已学习的 selector，然后 fallback"""
        learned = get_learned_selectors(task, field)
        for sel in learned[:5]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click()
                    learn_selector(task, field, sel, True)
                    return
            except Exception:
                learn_selector(task, field, sel, False)

        fallbacks = self._get_fallback_selectors(task, field)
        for sel in fallbacks:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click()
                    learn_selector(task, field, sel, True)
                    return
            except Exception:
                continue

    def _get_fallback_selectors(self, task: str, field: str) -> list[str]:
        """获取各任务/字段的 fallback 选择器"""
        base = {
            # 通用搜索
            ("company_lookup", "keyword"): [
                'input[id*="keyword"]', 'input[name*="keyword"]',
                'input[placeholder*="企业名称"]', 'input[placeholder*="统一社会信用代码"]',
                '#searchText', '.search-input input', 'input[type="text"]',
            ],
            ("company_lookup", "search_btn"): [
                'button:has-text("搜索")', 'button:has-text("查询")',
                'input[type="submit"]', '.search-btn', '#searchBtn',
            ],
            ("company_lookup", "first_result"): [
                '.search-result-item a', '.result-list a:first-child',
                'a:has-text("' + "" + '")', 'tr:first-child a',
            ],
            # 年报填报
            ("annual_report", "search_keyword"): [
                'input[id*="keyword"]', 'input[placeholder*="企业名称"]',
                '#searchText', 'input[type="text"]',
            ],
            ("annual_report", "search_btn"): [
                'button:has-text("搜索")', 'button:has-text("查询")', '#searchBtn',
            ],
            ("annual_report", "company_link"): [
                '.search-result-item a:first-child', 'a:has-text("' + "" + '")',
            ],
            ("annual_report", "annual_report_tab"): [
                'a:has-text("年报")', 'li:has-text("年报")', '.tab-annual',
            ],
            ("annual_report", "report_year"): [
                'select[id*="year"]', 'input[placeholder*="年份"]', '.year-select',
            ],
            ("annual_report", "preview_btn"): [
                'button:has-text("预览")', 'button:has-text("暂存")', 'button:has-text("保存")',
                '.btn-preview', '#previewBtn',
            ],
        }
        return base.get((task, field), [f'[id*="{field}"]', f'[name*="{field}"]'])

    def _get_annual_report_field_mappings(self) -> dict:
        """年报字段 → DOM 选择器映射"""
        return {
            "revenue": {"label": "营业收入", "selectors": ['input[id*="revenue"]', 'input[placeholder*="营业"]']},
            "profit": {"label": "利润总额", "selectors": ['input[id*="profit"]', 'input[placeholder*="利润"]']},
            "assets": {"label": "资产总额", "selectors": ['input[id*="asset"]', 'input[placeholder*="资产"]']},
            "tax_total": {"label": "纳税总额", "selectors": ['input[id*="tax"]', 'input[placeholder*="纳税"]']},
            "employees": {"label": "从业人数", "selectors": ['input[id*="employee"]', 'input[placeholder*="从业"]']},
            "liabilities": {"label": "负债总额", "selectors": ['input[id*="liabilit"]', 'input[placeholder*="负债"]']},
            "equity": {"label": "所有者权益", "selectors": ['input[id*="equity"]', 'input[placeholder*="权益"]']},
        }

    def _parse_company_info(self, page_text: str, keyword: str) -> dict:
        """从页面文本中解析企业信息"""
        patterns = {
            "name": r"企业名称[：:]\s*(.+)",
            "tax_no": r"统一社会信用代码[：:]\s*([A-Z0-9]{18})",
            "legal_person": r"法定代表人[：:]\s*(.+)",
            "registered_capital": r"注册资本[：:]\s*(.+)",
            "established_date": r"成立日期[：:]\s*(\d{4}[年-]\d{1,2}[月-]\d{1,2})",
            "business_status": r"(?:登记状态|经营状态)[：:]\s*(.+)",
            "company_type": r"企业类型[：:]\s*(.+)",
            "address": r"(?:住\s*所|注册地址)[：:]\s*(.+)",
            "business_scope": r"经营范围[：:]\s*(.+?)(?:依法须经批准|\n)",
            "registration_authority": r"登记机关[：:]\s*(.+)",
        }
        info = {}
        for key, pat in patterns.items():
            m = re.search(pat, page_text)
            info[key] = m.group(1).strip()[:300] if m else ""
        return info

    async def _fill_by_strategy(self, page, task: str, field: str, value: str, mapping: dict):
        """按映射策略填充字段"""
        selectors = mapping.get("selectors", [])
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    tag = await el.evaluate("e => e.tagName.toLowerCase()")
                    if tag == "select":
                        await el.select_option(value)
                    else:
                        await el.fill(value)
                    learn_selector(task, field, sel, True)
                    return
            except Exception:
                continue
        # Fallback: 按映射的 label 找
        label = mapping.get("label", field)
        try:
            label_el = page.locator(f'text="{label}"').first
            if await label_el.count() > 0:
                parent = label_el.locator("..")
                inp = parent.locator("input, select, textarea").first
                if await inp.count() > 0:
                    await inp.fill(value)
                    learn_selector(task, field, f'label:"{label}" + input', True)
        except Exception:
            pass


# ===== 便捷调用 =====

async def run_annual_report_auto(company_name: str, report_data: dict, headless: bool = True) -> AutoResult:
    return await BusinessAutomation(headless=headless).auto_fill_annual_report(company_name, report_data)


async def run_company_lookup(keyword: str, headless: bool = True) -> AutoResult:
    return await BusinessAutomation(headless=headless).auto_lookup_company(keyword)


def run_auto_sync(coro):
    """同步包装器"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
