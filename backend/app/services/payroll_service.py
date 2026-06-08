"""薪酬计算服务"""
import json, uuid
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.payroll import Employee, PayrollBatch, PayrollDetail

# 社保个人比例
SOCIAL_RATES = {"pension": 0.08, "medical": 0.02, "unemployment": 0.005}
HOUSING_FUND_RATE = 0.05
STANDARD_DEDUCTION = 5000  # 个税起征点

# 7级超额累进税率表（年累计）
IIT_BRACKETS = [
    (0, 36000, 0.03, 0),
    (36000, 144000, 0.10, 2520),
    (144000, 300000, 0.20, 16920),
    (300000, 420000, 0.25, 31920),
    (420000, 660000, 0.30, 52920),
    (660000, 960000, 0.35, 85920),
    (960000, float("inf"), 0.45, 181920),
]


def calc_iit(cumulative_taxable: float, month_index: int = 1) -> float:
    """计算累计预扣预缴个税（简化版：不累计历史月份）"""
    annual_taxable = cumulative_taxable * month_index
    annual_tax = 0
    for lo, hi, rate, quick in IIT_BRACKETS:
        if annual_taxable > lo:
            taxable_in_bracket = min(annual_taxable, hi) - lo
            annual_tax += taxable_in_bracket * rate
    return round(annual_tax / month_index, 2)


def generate_payroll_batch(db: Session, client_id: str, period: str, operator: str = "") -> dict:
    """为指定客户生成工资批次"""
    employees = db.query(Employee).filter(
        Employee.client_id == client_id,
        Employee.status == "active",
    ).all()

    if not employees:
        return {"error": "无在职员工，请先添加员工"}

    batch = PayrollBatch(
        id=uuid.uuid4().hex,
        client_id=client_id,
        period=period,
        status="draft",
    )
    db.add(batch)
    db.flush()

    total_gross = total_si = total_hf = total_sd = total_taxable = total_iit = total_net = 0.0

    for emp in employees:
        gross = emp.base_salary
        si_personal = round(emp.social_insurance_base * sum(SOCIAL_RATES.values()), 2) if emp.social_insurance_base else 0
        hf_personal = round(emp.housing_fund_base * HOUSING_FUND_RATE, 2) if emp.housing_fund_base else 0
        special = 0  # 专项附加扣除（简化，实际应读取员工配置）
        taxable = max(gross - STANDARD_DEDUCTION - si_personal - hf_personal - special, 0)
        iit = calc_iit(taxable)

        detail = PayrollDetail(
            id=uuid.uuid4().hex,
            batch_id=batch.id,
            employee_id=emp.id,
            employee_name=emp.name,
            base_salary=emp.base_salary,
            gross_pay=gross,
            social_insurance_personal=si_personal,
            housing_fund_personal=hf_personal,
            special_deduction=special,
            taxable_income=taxable,
            iit=iit,
            net_pay=round(gross - si_personal - hf_personal - iit, 2),
        )
        db.add(detail)

        total_gross += gross
        total_si += si_personal
        total_hf += hf_personal
        total_taxable += taxable
        total_iit += iit
        total_net += detail.net_pay

    batch.total_gross = round(total_gross, 2)
    batch.total_social_insurance = round(total_si, 2)
    batch.total_housing_fund = round(total_hf, 2)
    batch.total_special_deduction = round(total_sd, 2)
    batch.total_taxable = round(total_taxable, 2)
    batch.total_iit = round(total_iit, 2)
    batch.total_net_pay = round(total_net, 2)

    db.commit()
    return {"batch_id": batch.id, "employee_count": len(employees), "total_net_pay": round(total_net, 2)}


def confirm_payroll_batch(db: Session, batch_id: str, confirmed_by: str) -> dict:
    """确认工资批次，自动生成记账凭证"""
    batch = db.query(PayrollBatch).filter(PayrollBatch.id == batch_id).first()
    if not batch:
        return {"error": "批次不存在"}
    if batch.status != "draft":
        return {"error": "该批次已确认"}

    batch.status = "confirmed"
    batch.confirmed_by = confirmed_by
    batch.confirmed_at = datetime.now()

    # 生成记账凭证
    from app.models.voucher import AccountingVoucher
    from app.services.voucher_service import generate_voucher_no
    from app.services.qr_service import create_trace

    voucher_no = generate_voucher_no(db, datetime.now().date())
    entries = [
        {"account_code": "660207", "account_name": "管理费用-工资", "debit": batch.total_gross, "credit": 0, "summary": f"{batch.period} 工资"},
        {"account_code": "221101", "account_name": "应付职工薪酬-工资", "debit": 0, "credit": batch.total_gross - batch.total_iit, "summary": f"{batch.period} 应付工资"},
        {"account_code": "222122", "account_name": "应交个人所得税", "debit": 0, "credit": batch.total_iit, "summary": f"{batch.period} 代扣个税"},
    ]

    voucher = AccountingVoucher(
        id=uuid.uuid4().hex,
        voucher_no=voucher_no,
        voucher_date=datetime.now().date(),
        summary=f"{batch.period} 工资计提凭证（自动生成）",
        entries=json.dumps(entries, ensure_ascii=False),
        total_debit=batch.total_gross,
        total_credit=batch.total_gross,
        status="confirmed",
        created_by="system",
        reviewer=confirmed_by,
        reviewed_at=datetime.now(),
        client_id=batch.client_id,
    )
    db.add(voucher)
    db.flush()
    create_trace(db, "voucher", voucher.id, "ai_voucher")
    db.commit()

    return {"message": "工资已确认，记账凭证已自动生成", "voucher_no": voucher_no}
