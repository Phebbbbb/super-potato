"""薪酬管理 API"""
import json, uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.payroll import Employee, PayrollBatch, PayrollDetail
from app.services.payroll_service import generate_payroll_batch, confirm_payroll_batch
from app.services.auth import get_current_user, require_modify
from app.services.version_control import commit
from app.schemas.core import EmployeeCreate
from app.models.user import User

router = APIRouter()


# === 员工花名册 ===
@router.get("/employees/")
def list_employees(client_id: str = Query(None), status: str = Query(None),
                   page: int = Query(1), page_size: int = Query(100),
                   db: Session = Depends(get_db), _=Depends(get_current_user)):
    q = db.query(Employee)
    if client_id: q = q.filter(Employee.client_id == client_id)
    if status: q = q.filter(Employee.status == status)
    total = q.count()
    items = q.offset((page-1)*page_size).limit(page_size).all()
    return {"items": [{"id": e.id, "name": e.name, "position": e.position, "department": e.department,
            "base_salary": e.base_salary, "social_insurance_base": e.social_insurance_base,
            "housing_fund_base": e.housing_fund_base, "status": e.status,
            "hire_date": str(e.hire_date) if e.hire_date else None} for e in items],
            "total": total, "page": page, "page_size": page_size}


@router.post("/employees/")
def create_employee(data: EmployeeCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user), _=Depends(require_modify)):
    emp = Employee(id=uuid.uuid4().hex, client_id=data.client_id, name=data.name,
                   position=data.position, department=data.department,
                   base_salary=data.base_salary, social_insurance_base=data.social_insurance_base,
                   housing_fund_base=data.housing_fund_base, phone=data.phone,
                   id_card=data.id_card, bank_account=data.bank_account,
                   bank_name=data.bank_name)
    db.add(emp)
    commit(db, "employee", emp.id, "created", user.display_name or "",
           after={"name": emp.name, "client_id": emp.client_id})
    db.commit()
    return {"id": emp.id, "message": "员工添加成功"}


@router.patch("/employees/{emp_id}")
def update_employee(emp_id: str, data: dict, db: Session = Depends(get_db), _=Depends(require_modify)):
    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp: raise HTTPException(404, "员工不存在")
    for f in ["name","position","department","base_salary","social_insurance_base","housing_fund_base","phone","id_card","bank_account","bank_name","status"]:
        if f in data: setattr(emp, f, data[f])
    db.commit(); return {"message": "员工信息已更新"}


# === 工资批次 ===
@router.get("/batches/")
def list_batches(client_id: str = Query(None), period: str = Query(None),
                 page: int = Query(1), page_size: int = Query(50),
                 db: Session = Depends(get_db), _=Depends(get_current_user)):
    q = db.query(PayrollBatch)
    if client_id: q = q.filter(PayrollBatch.client_id == client_id)
    if period: q = q.filter(PayrollBatch.period == period)
    total = q.count()
    items = q.order_by(PayrollBatch.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    return {"items": [{"id": b.id, "client_id": b.client_id, "period": b.period, "status": b.status,
            "total_gross": b.total_gross, "total_social_insurance": b.total_social_insurance,
            "total_housing_fund": b.total_housing_fund, "total_taxable": b.total_taxable,
            "total_iit": b.total_iit, "total_net_pay": b.total_net_pay,
            "confirmed_by": b.confirmed_by, "created_at": str(b.created_at)} for b in items],
            "total": total, "page": page, "page_size": page_size}


@router.get("/batches/{batch_id}")
def get_batch(batch_id: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    batch = db.query(PayrollBatch).filter(PayrollBatch.id == batch_id).first()
    if not batch: raise HTTPException(404, "批次不存在")
    details = db.query(PayrollDetail).filter(PayrollDetail.batch_id == batch_id).all()
    return {"batch": {"id": batch.id, "period": batch.period, "status": batch.status,
            "total_gross": batch.total_gross, "total_social_insurance": batch.total_social_insurance,
            "total_housing_fund": batch.total_housing_fund, "total_taxable": batch.total_taxable,
            "total_iit": batch.total_iit, "total_net_pay": batch.total_net_pay,
            "confirmed_by": batch.confirmed_by},
            "details": [{"id": d.id, "employee_name": d.employee_name, "base_salary": d.base_salary,
            "overtime_pay": d.overtime_pay, "bonus": d.bonus, "allowance": d.allowance,
            "deduction": d.deduction, "gross_pay": d.gross_pay,
            "social_insurance_personal": d.social_insurance_personal,
            "housing_fund_personal": d.housing_fund_personal,
            "special_deduction": d.special_deduction, "taxable_income": d.taxable_income,
            "iit": d.iit, "net_pay": d.net_pay, "remark": d.remark} for d in details]}


@router.post("/batches/generate")
def create_batch(data: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user), _=Depends(require_modify)):
    result = generate_payroll_batch(db, data.get("client_id", ""), data.get("period", ""), data.get("operator", ""))
    if "error" in result: raise HTTPException(400, result["error"])
    batch_id = result.get("batch_id") or result.get("id", "")
    if batch_id:
        commit(db, "payroll_batch", batch_id, "generated", user.display_name or "",
               after={"period": data.get("period"), "client_id": data.get("client_id")})
    return result


@router.post("/batches/{batch_id}/confirm")
def confirm_batch(batch_id: str, data: dict, db: Session = Depends(get_db), _=Depends(require_modify)):
    result = confirm_payroll_batch(db, batch_id, data.get("confirmed_by", "审核员"))
    if "error" in result: raise HTTPException(400, result["error"])
    commit(db, "payroll_batch", batch_id, "confirmed", data.get("confirmed_by", "审核员"),
           after={"status": "confirmed"})
    return result


@router.patch("/batches/{batch_id}/detail/{detail_id}")
def update_detail(batch_id: str, detail_id: str, data: dict, db: Session = Depends(get_db), _=Depends(require_modify)):
    d = db.query(PayrollDetail).filter(PayrollDetail.id == detail_id, PayrollDetail.batch_id == batch_id).first()
    if not d: raise HTTPException(404, "明细不存在")
    for f in ["overtime_pay","bonus","allowance","deduction","remark"]:
        if f in data: setattr(d, f, data[f])
    d.gross_pay = d.base_salary + d.overtime_pay + d.bonus + d.allowance - d.deduction
    d.taxable_income = max(d.gross_pay - 5000 - d.social_insurance_personal - d.housing_fund_personal - d.special_deduction, 0)
    from app.services.payroll_service import calc_iit
    d.iit = calc_iit(d.taxable_income)
    d.net_pay = d.gross_pay - d.social_insurance_personal - d.housing_fund_personal - d.iit
    db.commit()
    return {"message": "已更新"}
