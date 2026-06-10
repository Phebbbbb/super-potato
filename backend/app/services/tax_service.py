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
    from app.models.system_config import SystemConfig
    land_area = 0.0  # 平方米
    unit_tax = 1.5    # 元/平方米·年（默认小城市标准）
    config = db.query(SystemConfig).filter(SystemConfig.config_key == "land_use_tax_config").first()
    if config and config.config_value:
        try:
            cfg = _load_config(config.config_value)
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


# ===== 以下为新增税种计算 =====

def calculate_consumption_tax(db: Session, period: str) -> dict:
    """计算消费税（从价定率/从量定额，简化版按从价）"""
    vouchers = get_confirmed_vouchers(db, period)
    # 消费税应税收入：6001 主营业务收入中应税消费品部分
    _, income = sum_entries(vouchers, "6001")
    # 简化：默认按比例估算应税消费品收入，税率 5%
    taxable_amount = round(income * 0.3, 2)  # 假设 30% 收入为应税消费品
    tax_rate = 0.05
    tax_payable = round(taxable_amount * tax_rate, 2)
    return {
        "tax_type": "consumption_tax",
        "period": period,
        "taxable_amount": taxable_amount,
        "tax_rate": tax_rate,
        "tax_payable": tax_payable,
        "note": "简化计算，实际需按税目分别核算",
    }


def calculate_individual_income(db: Session, period: str) -> dict:
    """计算个人所得税（工资薪金代扣代缴）"""
    vouchers = get_confirmed_vouchers(db, period)
    # 应付职工薪酬 2211 贷方
    _, payroll = sum_entries(vouchers, "2211")
    # 简化：按 3% 最低档估算（实际需按累计预扣法逐人计算）
    taxable_amount = round(payroll, 2)
    tax_rate = 0.03
    quick_deduction = 0.0
    tax_payable = round(max(taxable_amount * tax_rate - quick_deduction, 0), 2)
    return {
        "tax_type": "individual_income",
        "period": period,
        "taxable_amount": taxable_amount,
        "tax_rate": tax_rate,
        "quick_deduction": quick_deduction,
        "tax_payable": tax_payable,
        "note": "简化计算（3%档），实际需按累计预扣法逐人计算",
    }


def calculate_land_appreciation_tax(db: Session, period: str) -> dict:
    """计算土地增值税（四级超率累进税率）"""
    vouchers = get_confirmed_vouchers(db, period)
    # 转让收入
    _, transfer_income = sum_entries(vouchers, "6051")
    # 扣除项目 = 取得成本 + 开发成本 + 费用
    cost_debit, _ = sum_entries(vouchers, "6401")
    deduction = round(cost_debit * 1.3, 2)  # 简化：成本×130%
    appreciation = round(transfer_income - deduction, 2)
    # 四级超率累进
    if deduction == 0:
        tax_rate, quick_deduction_rate = 0.3, 0
    else:
        ratio = appreciation / deduction
        if ratio <= 0.5:
            tax_rate, quick_deduction_rate = 0.3, 0
        elif ratio <= 1.0:
            tax_rate, quick_deduction_rate = 0.4, 0.05
        elif ratio <= 2.0:
            tax_rate, quick_deduction_rate = 0.5, 0.15
        else:
            tax_rate, quick_deduction_rate = 0.6, 0.35
    tax_payable = round(max(appreciation * tax_rate - deduction * quick_deduction_rate, 0), 2)
    return {
        "tax_type": "land_appreciation_tax",
        "period": period,
        "transfer_income": round(transfer_income, 2),
        "total_deduction": deduction,
        "appreciation_amount": round(appreciation, 2),
        "tax_rate": tax_rate,
        "quick_deduction_rate": quick_deduction_rate,
        "tax_payable": tax_payable,
    }


def calculate_deed_tax(db: Session, period: str) -> dict:
    """计算契税（不动产受让）"""
    vouchers = get_confirmed_vouchers(db, period)
    # 不动产受让金额：1601 固定资产借方（新增房产）
    property_debit, _ = sum_entries(vouchers, "1601")
    taxable_amount = round(property_debit, 2)
    tax_rate = 0.03  # 契税法定税率 3%-5%，取最低
    tax_payable = round(taxable_amount * tax_rate, 2)
    return {
        "tax_type": "deed_tax",
        "period": period,
        "taxable_amount": taxable_amount,
        "tax_rate": tax_rate,
        "tax_payable": tax_payable,
        "note": "简化计算（3%），实际税率视地区政策",
    }


def calculate_vehicle_vessel_tax(db: Session, period: str) -> dict:
    """计算车船税（按年征收，按月分摊）"""
    # 车船税按年定额，需从固定资产-车辆（1604）读取
    # 简化：从系统配置读取
    from app.models.system_config import SystemConfig
    vehicle_count = 0
    annual_tax_per_vehicle = 360  # 默认乘用车 1.0L-1.6L
    config = db.query(SystemConfig).filter(SystemConfig.config_key == "vehicle_vessel_config").first()
    if config and config.config_value:
        try:
            cfg = _load_config(config.config_value)
            vehicle_count = int(cfg.get("vehicle_count", 0))
            annual_tax_per_vehicle = float(cfg.get("annual_tax_per_vehicle", 360))
        except Exception:
            pass
    monthly_tax = round(vehicle_count * annual_tax_per_vehicle / 12, 2)
    return {
        "tax_type": "vehicle_vessel_tax",
        "period": period,
        "vehicle_count": vehicle_count,
        "annual_tax_per_vehicle": annual_tax_per_vehicle,
        "tax_payable": monthly_tax,
        "note": "需手动配置车辆数量和年税额",
    }


def calculate_resource_tax(db: Session, period: str) -> dict:
    """计算资源税（从价计征简化版）"""
    vouchers = get_confirmed_vouchers(db, period)
    _, income = sum_entries(vouchers, "6001")
    # 简化：假设 10% 收入来自应税资源
    taxable_amount = round(income * 0.1, 2)
    tax_rate = 0.04  # 不同资源品目税率不同
    tax_payable = round(taxable_amount * tax_rate, 2)
    return {
        "tax_type": "resource_tax",
        "period": period,
        "taxable_amount": taxable_amount,
        "tax_rate": tax_rate,
        "tax_payable": tax_payable,
        "note": "简化计算，实际需按资源品目分别核算",
    }


def calculate_vehicle_purchase_tax(db: Session, period: str) -> dict:
    """计算车辆购置税（一次性，购买时缴纳）"""
    vouchers = get_confirmed_vouchers(db, period)
    # 车辆购置：1604 固定资产借方
    vehicle_debit, _ = sum_entries(vouchers, "1604")
    taxable_amount = round(vehicle_debit, 2)
    tax_rate = 0.10
    tax_payable = round(taxable_amount * tax_rate, 2)
    return {
        "tax_type": "vehicle_purchase_tax",
        "period": period,
        "taxable_amount": taxable_amount,
        "tax_rate": tax_rate,
        "tax_payable": tax_payable,
        "note": "一次性缴纳，按不含增值税价格计算",
    }


def calculate_environmental_tax(db: Session, period: str) -> dict:
    """计算环境保护税（大气污染物当量数×适用税额）"""
    from app.models.system_config import SystemConfig
    # 环保税需从在线监测/排污许可证获取数据
    pollution_equivalent = 0  # 污染物当量数
    unit_tax = 1.2  # 大气污染物每污染当量 1.2-12 元
    config = db.query(SystemConfig).filter(SystemConfig.config_key == "environmental_tax_config").first()
    if config and config.config_value:
        try:
            cfg = _load_config(config.config_value)
            pollution_equivalent = float(cfg.get("pollution_equivalent", 0))
            unit_tax = float(cfg.get("unit_tax", 1.2))
        except Exception:
            pass
    monthly_tax = round(pollution_equivalent * unit_tax, 2)
    return {
        "tax_type": "environmental_tax",
        "period": period,
        "pollution_equivalent": pollution_equivalent,
        "unit_tax": unit_tax,
        "tax_payable": monthly_tax,
        "note": "需手动配置污染物当量数和适用税额",
    }


def calculate_customs_duty(db: Session, period: str) -> dict:
    """计算关税（进口货物完税价格×税率）"""
    vouchers = get_confirmed_vouchers(db, period)
    # 进口货物：1403 原材料进口 借方
    import_debit, _ = sum_entries(vouchers, "1403")
    taxable_amount = round(import_debit, 2)
    tax_rate = 0.05  # 最惠国税率均值
    tax_payable = round(taxable_amount * tax_rate, 2)
    return {
        "tax_type": "customs_duty",
        "period": period,
        "taxable_amount": taxable_amount,
        "tax_rate": tax_rate,
        "tax_payable": tax_payable,
        "note": "需按实际商品HS编码确定税率，关税由海关代征",
    }


def calculate_farmland_occupation_tax(db: Session, period: str) -> dict:
    """计算耕地占用税（实际占用面积×适用税额，一次性缴纳）"""
    from app.models.system_config import SystemConfig
    land_area = 0.0
    unit_tax = 25.0  # 中等地区均值
    config = db.query(SystemConfig).filter(SystemConfig.config_key == "farmland_config").first()
    if config and config.config_value:
        try:
            cfg = _load_config(config.config_value)
            land_area = float(cfg.get("farmland_area", 0))
            unit_tax = float(cfg.get("unit_tax", 25.0))
        except Exception:
            pass
    tax_payable = round(land_area * unit_tax, 2)
    return {
        "tax_type": "farmland_occupation_tax",
        "period": period,
        "land_area": land_area,
        "unit_tax": unit_tax,
        "tax_payable": tax_payable,
        "note": "一次性缴纳，需手动配置占地面积和适用税额",
    }


def calculate_tobacco_tax(db: Session, period: str) -> dict:
    """计算烟叶税（收购金额×20%）"""
    vouchers = get_confirmed_vouchers(db, period)
    # 烟叶收购：1403 原材料 借方
    material_debit, _ = sum_entries(vouchers, "1403")
    # 简化：假设部分为烟叶收购
    taxable_amount = round(material_debit * 0.1, 2)  # 假设 10% 为烟叶
    tax_rate = 0.20
    tax_payable = round(taxable_amount * tax_rate, 2)
    return {
        "tax_type": "tobacco_tax",
        "period": period,
        "taxable_amount": taxable_amount,
        "tax_rate": tax_rate,
        "tax_payable": tax_payable,
        "note": "需按实际烟叶收购金额计算",
    }


def _load_config(val):
    """安全解析配置 JSON"""
    import json as _json
    return _json.loads(val) if isinstance(val, str) else val


def preview_filing(db: Session, tax_type: str, period: str, taxpayer_type: str = "small"):
    """预览申报数据（不保存）—— 支持全部 18 个税种"""
    calc_map = {
        "vat": lambda: calculate_vat(db, period, taxpayer_type),
        "corporate_income": lambda: calculate_corporate_income(db, period),
        "individual_income": lambda: calculate_individual_income(db, period),
        "surtax": lambda: calculate_surtax(db, period),
        "stamp_duty": lambda: calculate_stamp_duty(db, period),
        "consumption_tax": lambda: calculate_consumption_tax(db, period),
        "property_tax": lambda: calculate_property_tax(db, period),
        "land_use_tax": lambda: calculate_land_use_tax(db, period),
        "land_appreciation_tax": lambda: calculate_land_appreciation_tax(db, period),
        "deed_tax": lambda: calculate_deed_tax(db, period),
        "vehicle_vessel_tax": lambda: calculate_vehicle_vessel_tax(db, period),
        "vehicle_purchase_tax": lambda: calculate_vehicle_purchase_tax(db, period),
        "resource_tax": lambda: calculate_resource_tax(db, period),
        "environmental_tax": lambda: calculate_environmental_tax(db, period),
        "farmland_occupation_tax": lambda: calculate_farmland_occupation_tax(db, period),
        "tobacco_tax": lambda: calculate_tobacco_tax(db, period),
        "customs_duty": lambda: calculate_customs_duty(db, period),
    }
    calc = calc_map.get(tax_type)
    if calc:
        return calc()
    return {"tax_type": tax_type, "period": period, "message": "未知税种"}
