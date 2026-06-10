"""工商年报 API — 企业年度报告公示管理"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date as dt_date
from app.db import get_db
from app.models.annual_report import AnnualReport
from app.services.auth import get_current_user, require_modify
from app.services.version_control import commit as vc_commit

router = APIRouter()


@router.get("/")
def list_reports(
    client_id: str = Query(None),
    report_year: int = Query(None),
    db: Session = Depends(get_db),
):
    """列出工商年报"""
    q = db.query(AnnualReport)
    if client_id:
        q = q.filter(AnnualReport.client_id == client_id)
    if report_year:
        q = q.filter(AnnualReport.report_year == report_year)
    q = q.order_by(AnnualReport.report_year.desc())
    items = q.all()

    # 计算哪些年份缺失年报
    current_year = dt_date.today().year
    existing_years = {r.report_year for r in items}
    missing_years = [y for y in range(current_year - 3, current_year)
                     if y not in existing_years and y >= current_year - 2]

    return {
        "items": [
            {
                "id": r.id, "client_id": r.client_id, "report_year": r.report_year,
                "company_name": r.company_name, "unified_social_credit_code": r.unified_social_credit_code,
                "annual_revenue": r.annual_revenue, "annual_profit": r.annual_profit,
                "total_assets": r.total_assets, "net_assets": r.net_assets,
                "employee_count": r.employee_count, "status": r.status,
                "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in items
        ],
        "missing_years": missing_years,
        "report_count": len(items),
    }


@router.get("/{report_id}")
def get_report(report_id: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    """获取单个年报详情"""
    r = db.query(AnnualReport).filter(AnnualReport.id == report_id).first()
    if not r:
        raise HTTPException(404, "年报不存在")
    import json
    return {
        "id": r.id, "client_id": r.client_id, "report_year": r.report_year,
        "company_name": r.company_name, "unified_social_credit_code": r.unified_social_credit_code,
        "legal_representative": r.legal_representative,
        "contact_phone": r.contact_phone, "contact_email": r.contact_email,
        "business_address": r.business_address, "postal_code": r.postal_code,
        "website_url": r.website_url, "business_scope": r.business_scope,
        "employee_count": r.employee_count, "is_listed": r.is_listed,
        "shareholders": json.loads(r.shareholders) if r.shareholders else [],
        "total_assets": r.total_assets, "total_liabilities": r.total_liabilities,
        "net_assets": r.net_assets, "annual_revenue": r.annual_revenue,
        "annual_profit": r.annual_profit, "annual_net_profit": r.annual_net_profit,
        "annual_tax_paid": r.annual_tax_paid,
        "external_guarantees": json.loads(r.external_guarantees) if r.external_guarantees else [],
        "party_members_count": r.party_members_count, "has_party_org": r.has_party_org,
        "social_insurance_participants": r.social_insurance_participants,
        "social_insurance_base": r.social_insurance_base,
        "social_insurance_paid": r.social_insurance_paid,
        "social_insurance_arrears": r.social_insurance_arrears,
        "status": r.status, "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
        "published_at": r.published_at.isoformat() if r.published_at else None,
        "samr_receipt_no": r.samr_receipt_no,
        "created_by": r.created_by, "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


@router.post("/")
def create_report(data: dict, db: Session = Depends(get_db)):
    """创建工商年报"""
    import json
    # 检查重复
    existing = db.query(AnnualReport).filter(
        AnnualReport.client_id == data["client_id"],
        AnnualReport.report_year == data["report_year"],
    ).first()
    if existing:
        raise HTTPException(409, f"{data['report_year']}年度年报已存在")

    r = AnnualReport(
        client_id=data["client_id"],
        report_year=data["report_year"],
        company_name=data.get("company_name", ""),
        unified_social_credit_code=data.get("unified_social_credit_code", ""),
        legal_representative=data.get("legal_representative", ""),
        contact_phone=data.get("contact_phone", ""),
        contact_email=data.get("contact_email", ""),
        business_address=data.get("business_address", ""),
        postal_code=data.get("postal_code", ""),
        website_url=data.get("website_url", ""),
        business_scope=data.get("business_scope", ""),
        employee_count=data.get("employee_count"),
        is_listed=data.get("is_listed", "否"),
        shareholders=json.dumps(data.get("shareholders", []), ensure_ascii=False),
        total_assets=data.get("total_assets"),
        total_liabilities=data.get("total_liabilities"),
        net_assets=data.get("net_assets"),
        annual_revenue=data.get("annual_revenue"),
        annual_profit=data.get("annual_profit"),
        annual_net_profit=data.get("annual_net_profit"),
        annual_tax_paid=data.get("annual_tax_paid"),
        external_guarantees=json.dumps(data.get("external_guarantees", []), ensure_ascii=False),
        party_members_count=data.get("party_members_count"),
        has_party_org=data.get("has_party_org", "否"),
        social_insurance_participants=data.get("social_insurance_participants"),
        social_insurance_base=data.get("social_insurance_base"),
        social_insurance_paid=data.get("social_insurance_paid"),
        social_insurance_arrears=data.get("social_insurance_arrears"),
        created_by=data.get("created_by", ""),
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    vc_commit(db, "annual_report", r.id, None, {"report_year": r.report_year, "status": "draft"},
              operator=data.get("created_by", ""), client_id=r.client_id)
    return {"id": r.id, "message": f"{r.report_year}年度年报已创建"}


@router.patch("/{report_id}")
def update_report(report_id: str, data: dict, db: Session = Depends(get_db)):
    """更新工商年报"""
    import json
    r = db.query(AnnualReport).filter(AnnualReport.id == report_id).first()
    if not r:
        raise HTTPException(404, "年报不存在")
    before = {"status": r.status}

    updatable = [
        "company_name", "unified_social_credit_code", "legal_representative",
        "contact_phone", "contact_email", "business_address", "postal_code",
        "website_url", "business_scope", "employee_count", "is_listed",
        "total_assets", "total_liabilities", "net_assets", "annual_revenue",
        "annual_profit", "annual_net_profit", "annual_tax_paid",
        "party_members_count", "has_party_org",
        "social_insurance_participants", "social_insurance_base",
        "social_insurance_paid", "social_insurance_arrears", "status",
    ]
    for k in updatable:
        if k in data:
            setattr(r, k, data[k])

    if "shareholders" in data:
        r.shareholders = json.dumps(data["shareholders"], ensure_ascii=False)
    if "external_guarantees" in data:
        r.external_guarantees = json.dumps(data["external_guarantees"], ensure_ascii=False)

    if data.get("status") == "submitted" and r.status != "submitted":
        r.submitted_at = dt_date.today()

    db.commit()
    db.refresh(r)
    vc_commit(db, "annual_report", r.id, before, {"status": r.status, "report_year": r.report_year},
              operator=data.get("operator", ""), client_id=r.client_id)
    return {"id": r.id, "message": "年报已更新"}


@router.delete("/{report_id}")
def delete_report(report_id: str, db: Session = Depends(get_db), _=Depends(require_modify)):
    """删除工商年报"""
    r = db.query(AnnualReport).filter(AnnualReport.id == report_id).first()
    if not r:
        raise HTTPException(404, "年报不存在")
    db.delete(r)
    db.commit()
    return {"message": "年报已删除"}


@router.get("/check/missing")
def check_missing_reports(client_id: str = Query(...), db: Session = Depends(get_db)):
    """检查指定客户缺失的年报年度"""
    current_year = dt_date.today().year
    existing = {
        r[0] for r in
        db.query(AnnualReport.report_year).filter(AnnualReport.client_id == client_id).all()
    }
    must_report = list(range(current_year - 2, current_year))  # 前两个年度
    if dt_date.today().month <= 6:
        must_report.append(current_year - 1)  # 6月30日前可报上年度
    missing = [y for y in must_report if y not in existing]
    return {"client_id": client_id, "current_year": current_year, "missing_years": missing,
            "deadline": f"{current_year}-06-30" if current_year - 1 in missing else "无逾期",
            "message": f"缺失 {len(missing)} 个年度年报: {missing}" if missing else "所有应报年度均已覆盖"}
