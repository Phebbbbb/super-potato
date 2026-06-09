"""固定资产 API — CRUD + 自动折旧"""
import uuid
from datetime import date as dt_date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.fixed_asset import FixedAsset
from app.models.voucher import AccountingVoucher
from app.services.auth import require_modify, get_current_user, check_client_access
from app.services.qr_service import create_trace
from app.services.version_control import commit
from app.services.voucher_service import generate_voucher_no

router = APIRouter()

CATEGORY_MAP = {
    "building": {"name": "房屋建筑物", "life": 240, "rate": 5},
    "electronics": {"name": "电子设备", "life": 36, "rate": 5},
    "vehicle": {"name": "运输工具", "life": 48, "rate": 5},
    "furniture": {"name": "办公家具", "life": 60, "rate": 5},
    "machinery": {"name": "机器设备", "life": 120, "rate": 5},
    "other": {"name": "其他", "life": 36, "rate": 5},
}


def calc_depreciation(original_value: float, residual_rate: float, useful_life: int) -> float:
    """直线法月折旧额"""
    if useful_life <= 0:
        return 0
    residual = original_value * residual_rate / 100
    return round((original_value - residual) / useful_life, 2)


@router.get("/")
def list_assets(
    client_id: str = Query(None),
    category: str = Query(None),
    status: str = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(FixedAsset)
    if client_id:
        q = q.filter(FixedAsset.client_id == client_id)
    if category:
        q = q.filter(FixedAsset.category == category)
    if status:
        q = q.filter(FixedAsset.status == status)
    items = q.order_by(FixedAsset.purchase_date.desc()).all()
    total_original = sum(a.original_value for a in items)
    total_depreciation = sum(a.accumulated_depreciation for a in items)
    total_net = sum(a.net_value for a in items)
    return {
        "items": [{
            "id": a.id, "client_id": a.client_id, "asset_code": a.asset_code,
            "asset_name": a.asset_name, "category": a.category,
            "purchase_date": a.purchase_date.isoformat() if a.purchase_date else None,
            "original_value": a.original_value, "residual_rate": a.residual_rate,
            "useful_life": a.useful_life, "monthly_depreciation": a.monthly_depreciation,
            "accumulated_depreciation": a.accumulated_depreciation,
            "net_value": a.net_value, "status": a.status,
            "location": a.location, "remark": a.remark,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        } for a in items],
        "summary": {
            "total_original": total_original,
            "total_depreciation": total_depreciation,
            "total_net": total_net,
            "count": len(items),
        },
    }


@router.post("/")
def create_asset(
    data: dict,
    db: Session = Depends(get_db),
    user=Depends(require_modify),
):
    """新增固定资产 — 自动计算月折旧额"""
    cat = CATEGORY_MAP.get(data.get("category", "other"), CATEGORY_MAP["other"])
    useful_life = data.get("useful_life") or cat["life"]
    residual_rate = data.get("residual_rate") or cat["rate"]
    original_value = float(data.get("original_value", 0))
    monthly_dep = calc_depreciation(original_value, residual_rate, useful_life)

    asset = FixedAsset(
        id=str(uuid.uuid4()),
        client_id=data.get("client_id", ""),
        asset_code=data.get("asset_code", f"FA-{uuid.uuid4().hex[:8].upper()}"),
        asset_name=data["asset_name"],
        category=data.get("category", "other"),
        purchase_date=dt_date.fromisoformat(data["purchase_date"]) if data.get("purchase_date") else dt_date.today(),
        original_value=original_value,
        residual_rate=residual_rate,
        useful_life=useful_life,
        monthly_depreciation=monthly_dep,
        accumulated_depreciation=0,
        net_value=original_value,
        status=data.get("status", "in_use"),
        location=data.get("location", ""),
        remark=data.get("remark", ""),
    )
    db.add(asset)
    db.flush()

    commit(db, "fixed_asset", asset.id, "created", user.display_name or "",
           after={"asset_name": asset.asset_name, "original_value": asset.original_value})

    db.commit()
    return {"id": asset.id, "message": f"资产 {asset.asset_name} 已创建，月折旧 {monthly_dep} 元"}


@router.patch("/{asset_id}")
def update_asset(
    asset_id: str,
    data: dict,
    db: Session = Depends(get_db),
    user=Depends(require_modify),
):
    a = db.query(FixedAsset).filter(FixedAsset.id == asset_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="资产不存在")
    if a.client_id and not check_client_access(a.client_id, user, db):
        raise HTTPException(status_code=403, detail="无权操作")

    before = {"asset_name": a.asset_name, "original_value": a.original_value, "status": a.status}

    for field in ["asset_name", "category", "location", "remark", "status", "asset_code"]:
        if field in data and data[field] is not None:
            setattr(a, field, data[field])
    if "original_value" in data:
        a.original_value = float(data["original_value"])
    if "residual_rate" in data:
        a.residual_rate = float(data["residual_rate"])
    if "useful_life" in data:
        a.useful_life = int(data["useful_life"])
    if "purchase_date" in data and data["purchase_date"]:
        a.purchase_date = dt_date.fromisoformat(data["purchase_date"])

    a.monthly_depreciation = calc_depreciation(a.original_value, a.residual_rate, a.useful_life)
    a.net_value = round(a.original_value - a.accumulated_depreciation, 2)

    commit(db, "fixed_asset", asset_id, "updated", user.display_name or "", before=before,
           after={"asset_name": a.asset_name, "original_value": a.original_value})
    db.commit()
    return {"message": f"资产 {a.asset_name} 已更新"}


@router.delete("/{asset_id}")
def delete_asset(asset_id: str, db: Session = Depends(get_db), user=Depends(require_modify)):
    a = db.query(FixedAsset).filter(FixedAsset.id == asset_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="资产不存在")
    if a.client_id and not check_client_access(a.client_id, user, db):
        raise HTTPException(status_code=403, detail="无权操作")
    commit(db, "fixed_asset", asset_id, "deleted", user.display_name or "",
           before={"asset_name": a.asset_name, "original_value": a.original_value})
    db.delete(a)
    db.commit()
    return {"message": f"资产 {a.asset_name} 已删除"}


@router.post("/run-depreciation")
def run_depreciation(
    client_id: str = Query(...),
    period: str = Query(None),
    db: Session = Depends(get_db),
    user=Depends(require_modify),
):
    """
    执行月度折旧 — 为所有在用的固定资产生成折旧凭证
    借：管理费用-折旧费 / 贷：累计折旧
    """
    if not period:
        today = dt_date.today()
        period = f"{today.year}-{today.month:02d}"

    assets = db.query(FixedAsset).filter(
        FixedAsset.client_id == client_id,
        FixedAsset.status == "in_use",
        FixedAsset.net_value > 0,
    ).all()

    if not assets:
        return {"message": "没有需要折旧的资产", "vouchers_created": 0}

    total_depreciation = 0
    voucher_ids = []

    for asset in assets:
        dep = asset.monthly_depreciation
        if dep <= 0:
            continue

        asset.accumulated_depreciation = round(asset.accumulated_depreciation + dep, 2)
        asset.net_value = round(asset.original_value - asset.accumulated_depreciation, 2)
        total_depreciation += dep

        p_date = dt_date.fromisoformat(f"{period}-01")
        vno = generate_voucher_no(db, p_date)

        entries = [
            {"account_code": "660201", "account_name": "管理费用-折旧费", "debit": dep, "credit": 0, "summary": f"{asset.asset_name} 折旧"},
            {"account_code": "1602", "account_name": "累计折旧", "debit": 0, "credit": dep, "summary": f"{asset.asset_name} 折旧"},
        ]

        voucher = AccountingVoucher(
            id=str(uuid.uuid4()),
            voucher_no=vno,
            voucher_date=p_date,
            summary=f"固定资产折旧: {asset.asset_name} ({period})",
            entries=f'[{{"account_code":"660201","account_name":"管理费用-折旧费","debit":{dep},"credit":0,"summary":"{asset.asset_name} 折旧"}},{{"account_code":"1602","account_name":"累计折旧","debit":0,"credit":{dep},"summary":"{asset.asset_name} 折旧"}}]',
            total_debit=dep,
            total_credit=dep,
            status="confirmed",
            created_by="auto_depreciation",
            reviewer=user.display_name or "系统自动",
            review_comment=f"自动折旧 {period}",
            client_id=client_id,
        )
        db.add(voucher)
        db.flush()
        create_trace(db, "voucher", voucher.id, "depreciation")
        commit(db, "voucher", voucher.id, "auto_depreciation", "system",
               after={"voucher_no": vno, "asset": asset.asset_name, "depreciation": dep})
        voucher_ids.append(voucher.id)

    db.commit()
    return {
        "message": f"折旧完成：{len(voucher_ids)} 项资产，合计折旧 {total_depreciation} 元",
        "period": period,
        "vouchers_created": len(voucher_ids),
        "total_depreciation": total_depreciation,
        "voucher_ids": voucher_ids,
    }
