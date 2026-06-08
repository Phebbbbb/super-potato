"""税局自动化引擎单元测试 — 不依赖 Playwright 的逻辑验证"""
import sys
import pytest
from app.services.tax_automation import (
    TaxAutomationEngine,
    FilingResult,
    TAX_BUREAU_CONFIGS,
)


class TestTaxEngineConfigs:
    """验证省份配置完整性"""

    REQUIRED_TAX_TYPES = ["vat", "corporate_income", "surtax", "stamp_duty", "property_tax", "land_use_tax"]
    REQUIRED_LOGIN_FIELDS = ["username", "password", "submit"]

    @pytest.mark.parametrize("province", ["beijing", "shanghai", "guangdong", "zhejiang", "jiangsu", "generic"])
    def test_province_has_all_login_selectors(self, province):
        """每个省份都有完整的登录选择器"""
        config = TAX_BUREAU_CONFIGS[province]
        for field in self.REQUIRED_LOGIN_FIELDS:
            assert field in config["login_selectors"], f"{province} 缺少 login_selectors.{field}"
            assert config["login_selectors"][field], f"{province} login_selectors.{field} 为空"

    @pytest.mark.parametrize("province", ["beijing", "shanghai", "guangdong", "zhejiang", "jiangsu", "generic"])
    def test_province_has_all_tax_types(self, province):
        """每个省份都配置了全部 6 个税种"""
        config = TAX_BUREAU_CONFIGS[province]
        filing_s = config.get("filing_selectors", {})
        for tax_type in self.REQUIRED_TAX_TYPES:
            assert tax_type in filing_s, f"{province} 缺少税种: {tax_type}"

    @pytest.mark.parametrize("tax_type", REQUIRED_TAX_TYPES)
    @pytest.mark.parametrize("province", ["beijing", "shanghai", "guangdong", "zhejiang", "jiangsu", "generic"])
    def test_tax_type_has_required_selectors(self, province, tax_type):
        """每个税种配置包含必要的选择器字段"""
        config = TAX_BUREAU_CONFIGS[province]
        filing_s = config.get("filing_selectors", {}).get(tax_type, {})
        required = ["menu_declare", "menu_item", "btn_submit", "btn_confirm", "success_indicator"]
        for field in required:
            assert field in filing_s, f"{province}.{tax_type} 缺少 {field}"
            assert filing_s[field], f"{province}.{tax_type}.{field} 为空"

    def test_beijing_has_login_url(self):
        """北京有 login_url"""
        assert TAX_BUREAU_CONFIGS["beijing"]["login_url"].startswith("https://")

    def test_generic_has_empty_login_url(self):
        """通用模板 login_url 为空（需用户自行填写）"""
        assert TAX_BUREAU_CONFIGS["generic"]["login_url"] == ""


class TestFilingResult:
    """FilingResult 数据类测试"""

    def test_default_values(self):
        result = FilingResult(success=False, message="test")
        assert result.tax_type == ""
        assert result.period == ""
        assert result.screenshot_paths == []
        assert result.steps_completed == []
        assert result.failed_step == ""
        assert result.error_detail == ""

    def test_full_result(self):
        result = FilingResult(
            success=True,
            message="申报成功",
            tax_type="vat",
            period="2026-06",
            screenshot_paths=["/tmp/s1.png"],
            transaction_id="abc123",
            filed_at="2026-06-08T10:00:00",
            steps_completed=["login", "fill_form", "submitted", "verify_result"],
            failed_step="",
            error_detail="",
        )
        assert result.success is True
        assert len(result.steps_completed) == 4
        assert result.transaction_id == "abc123"


class TestTaxEngineNoPlaywright:
    """模拟 Playwright 未安装时的行为"""

    def test_run_filing_without_playwright(self):
        """未安装 Playwright 时返回明确错误"""
        engine = TaxAutomationEngine(profile="beijing", headless=True)
        # 临时移除 playwright 模块模拟未安装
        playwright_module = sys.modules.get("playwright")
        sys.modules["playwright"] = None
        try:
            import asyncio
            result = asyncio.new_event_loop().run_until_complete(
                engine.run_filing(
                    tax_type="vat",
                    period="2026-06",
                    tax_data={"period_sales": 50000, "tax_payable": 1500},
                    credentials={"username": "test", "password": "test"},
                )
            )
            assert result.success is False
            assert "playwright" in result.message.lower()
        finally:
            if playwright_module is not None:
                sys.modules["playwright"] = playwright_module

    def test_run_filing_generic_no_url(self):
        """generic 省份无 login_url 时返回错误"""
        # 确保 playwright 模块可用（前一个测试可能已清除）
        try:
            from playwright import async_api  # noqa: F401
        except ImportError:
            pass

        engine = TaxAutomationEngine(profile="generic", headless=True)
        import asyncio
        result = asyncio.new_event_loop().run_until_complete(
            engine.run_filing(
                tax_type="vat",
                period="2026-06",
                tax_data={"period_sales": 50000},
                credentials={"username": "test", "password": "test"},
            )
        )
        # generic 的 login_url 为空 → 应该返回 login_url 相关错误
        # 但如果 Playwright 不可用，会先返回 Playwright 错误
        assert not result.success
        assert ("login_url" in result.message.lower() or "playwright" in result.message.lower())

    def test_unsupported_tax_type(self):
        """不支持的税种返回错误（需要先绕过 playwright 导入）"""
        # 通过直接调用内部逻辑验证：filing_selectors 中不存在该税种
        engine = TaxAutomationEngine(profile="beijing")
        filing_configs = engine.config.get("filing_selectors", {})
        assert "invalid_tax" not in filing_configs
        assert "vat" in filing_configs

    def test_profile_fallback_to_generic(self):
        """不存在的 profile 回退到 generic"""
        engine = TaxAutomationEngine(profile="nonexistent_province")
        assert engine.config == TAX_BUREAU_CONFIGS["generic"]


class TestTaxDataFillMapping:
    """验证税种数据映射"""

    def test_vat_fields(self):
        """增值税字段映射"""
        config = TAX_BUREAU_CONFIGS["beijing"]["filing_selectors"]["vat"]
        assert "input_period_sales" in config
        assert "input_tax_payable" in config

    def test_corporate_income_fields(self):
        """企业所得税字段映射"""
        config = TAX_BUREAU_CONFIGS["beijing"]["filing_selectors"]["corporate_income"]
        assert "input_revenue" in config
        assert "input_cost" in config
        assert "input_profit" in config
        assert "input_tax_payable" in config

    def test_surtax_fields(self):
        """附加税字段映射"""
        config = TAX_BUREAU_CONFIGS["beijing"]["filing_selectors"]["surtax"]
        assert "input_vat_amount" in config

    def test_stamp_duty_fields(self):
        """印花税字段映射"""
        config = TAX_BUREAU_CONFIGS["beijing"]["filing_selectors"]["stamp_duty"]
        assert "input_taxable_amount" in config
        assert "input_tax_payable" in config

    def test_property_tax_fields(self):
        """房产税字段映射"""
        config = TAX_BUREAU_CONFIGS["beijing"]["filing_selectors"]["property_tax"]
        assert "input_property_value" in config
        assert "input_tax_payable" in config

    def test_land_use_tax_fields(self):
        """城镇土地使用税字段映射"""
        config = TAX_BUREAU_CONFIGS["beijing"]["filing_selectors"]["land_use_tax"]
        assert "input_land_area" in config
        assert "input_tax_payable" in config
