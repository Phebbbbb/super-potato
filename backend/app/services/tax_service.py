"""税务计算服务 — 从已确认凭证自动汇总各税种申报数据"""
from sqlalchemy.orm import Session
from app.models.voucher import AccountingVoucher
import json


def get_confirmed_vouchers(db: Session, period: str):
    """获取指定期间所有已确认凭证"""
    start = f"{period}-01"
    # 月末日
    parts = period.split("-")
    y, m = int(parts[0]), int(parts[1])
    if m == 12:
        end = f"{y+1}-01-01"
    else:
        end = f"{y}-{m+1:02d}-01"
    return db.query(AccountingVoucher).filter(
        AccountingVoucher.status == "confirmed",
        AccountingVoucher.voucher_date >= start,
        AccountingVoucher.voucher_date < end,
    ).all()


def sum_entries(vouchers, account_code_prefix=None):
    """汇总凭证分录金额，可按科目编码前缀过滤"""
    debit_total = 0.0
    credit_total = 0.0
    for v in vouchers:
        entries = json.loads(v.entries) if isinstance(v.entries, str) else v.entries
        for e in entries:
            code = e.get("account_code", "")
            if account_code_prefix is None or code.startswith(account_code_prefix):
                debit_total += float(e.get("debit", 0) or 0)
                credit_total += float(e.get("credit", 0) or 0)
    return debit_total, credit_total


def calculate_vat(db: Session, period: str, taxpayer_type: str = "small"):
    """计算增值税申报数据"""
    vouchers = get_confirmed_vouchers(db, period)

    # 销售额 = 6001 主营业务收入 贷方发生额
    _, sales = sum_entries(vouchers, "6001")
    # 销项税额 = 222101 贷方发生额
    _, output_tax = sum_entries(vouchers, "222101")
    # 进项税额 = 222101 借方发生额
    input_tax, _ = sum_entries(vouchers, "222101")

    if taxpayer_type == "small":
        tax_rate = 0.03
        tax_payable = round(sales * tax_rate, 2)
        tax_reduction = 0.0
        if sales <= 100000:
            tax_reduction = tax_payable
            tax_payable = 0.0
        return {
            "tax_type": "vat_small",
            "period": period,
            "period_sales": round(sales, 2),
            "tax_rate": tax_rate,
            "tax_payable": tax_payable,
            "tax_reduction": tax_reduction,
        }
    else:
        tax_payable = round(output_tax - input_tax, 2)
        return {
            "tax_type": "vat",
            "period": period,
            "period_sales": round(sales, 2),
            "period_output_tax": round(output_tax, 2),
            "period_input_tax": round(input_tax, 2),
            "tax_payable": tax_payable,
        }


def calculate_corporate_income(db: Session, period: str):
    """计算企业所得税季度预缴数据"""
    vouchers = get_confirmed_vouchers(db, period)

    _, income = sum_entries(vouchers, "6001")   # 收入类贷方
    cost_debit, _ = sum_entries(vouchers, "6401")  # 成本
    expense_debit, _ = sum_entries(vouchers, "660")  # 费用类 (6601,6602,6603)

    total_revenue = round(income, 2)
    total_cost = round(cost_debit + expense_debit, 2)
    profit = round(total_revenue - total_cost, 2)
    tax_rate = 0.25

    tax_payable = round(max(profit, 0) * tax_rate, 2)

    return {
        "tax_type": "corporate_income",
        "period": period,
        "cumulative_income": total_revenue,
        "cumulative_cost": total_cost,
        "cumulative_profit": profit,
        "tax_rate": tax_rate,
        "tax_payable": tax_payable,
        "prepaid_tax": 0.0,
        "actual_payable": tax_payable,
    }


def calculate_surtax(db: Session, period: str):
    """计算附加税（城建税+教育费附加+地方教育附加）"""
    vat_data = calculate_vat(db, period, "general")
    vat_payable = vat_data.get("tax_payable", 0)

    urban = round(vat_payable * 0.07, 2)
    education = round(vat_payable * 0.03, 2)
    local_education = round(vat_payable * 0.02, 2)
    total = round(urban + education + local_education, 2)

    return {
        "tax_type": "surtax",
        "period": period,
        "base_vat": round(vat_payable, 2),
        "urban_construction": urban,
        "education_surcharge": education,
        "local_education_surcharge": local_education,
        "total_surtax": total,
    }


def calculate_stamp_duty(db: Session, period: str) -> dict:
    """计算印花税"""
    vouchers = get_confirmed_vouchers(db, period)
    # 购销合同金额 = 收入 + 成本（简化：按收入+成本合计算印花税）
    _, income = sum_entries(vouchers, "6001")  # 收入类贷方
    cost_debit, _ = sum_entries(vouchers, "6401")  # 成本借方
    # 购销合同: 价款 × 0.3‰
    taxable_amount = round(income + cost_debit, 2)
    tax_payable = round(taxable_amount * 0.0003, 2)
    return {
        "tax_type": "stamp_duty",
        "period": period,
        "taxable_amount": taxable_amount,
        "tax_rate": 0.0003,
        "tax_payable": tax_payable,
    }


def calculate_property_tax(db: Session, period: str) -> dict:
    """计算房产税（从价计征简化版）"""
    # 从固定资产科目（1601）借方余额估算房产原值
    vouchers = get_confirmed_vouchers(db, period)
    property_debit, property_credit = sum_entries(vouchers, "1601")
    # 房产原值 × (1-30%) × 1.2% / 12（月）
    property_value = round(property_debit - property_credit, 2)
    monthly_tax = round(property_value * 0.7 * 0.012 / 12, 2) if property_value > 0 else 0
    return {
        "tax_type": "property_tax",
        "period": period,
        "property_original_value": property_value,
        "deduction_ratio": 0.3,
        "annual_tax_rate": 0.012,
        "tax_payable": monthly_tax,
    }


def calculate_land_use_tax(db: Session, period: str) -> dict:
    """计算城镇土地使用税（简化版，需手动配置占地面积和适用税额）"""
    # 城镇土地使用税需要占地面积和适用税额，通常从配置读取
    # 此处使用默认值，实际使用时需在系统配置中设置
    from app.models.system_config import SystemConfig
    land_area = 0.0  # 平方米
    unit_tax = 1.5    # 元/平方米·年（默认小城市标准）
    config = db.query(SystemConfig).filter(SystemConfig.config_key == "land_use_tax_config").first()
    if config and config.config_value:
        import json as _json
        try:
            cfg = _json.loads(config.config_value) if isinstance(config.config_value, str) else config.config_value
            land_area = float(cfg.get("land_area", 0))
            unit_tax = float(cfg.get("unit_tax", 1.5))
        except Exception:
            pass
    monthly_tax = round(land_area * unit_tax / 12, 2)
    return {
        "tax_type": "land_use_tax",
        "period": period,
        "land_area": land_area,
        "unit_tax": unit_tax,
        "tax_payable": monthly_tax,
    }


def preview_filing(db: Session, tax_type: str, period: str, taxpayer_type: str = "small"):
    """预览申报数据（不保存）"""
    if tax_type == "vat":
        return calculate_vat(db, period, taxpayer_type)
    elif tax_type == "corporate_income":
        return calculate_corporate_income(db, period)
    elif tax_type == "surtax":
        return calculate_surtax(db, period)
    elif tax_type == "stamp_duty":
        return calculate_stamp_duty(db, period)
    elif tax_type == "property_tax":
        return calculate_property_tax(db, period)
    elif tax_type == "land_use_tax":
        return calculate_land_use_tax(db, period)
    else:
        return {"tax_type": tax_type, "period": period, "message": "暂不支持该税种自动计算"}
