"""固定资产服务：批量折旧"""
import uuid
import json
from datetime import date as dt_date
from sqlalchemy.orm import Session
from app.models.fixed_asset import FixedAsset
from app.models.voucher import AccountingVoucher
from app.services.voucher_service import generate_voucher_no
from app.services.qr_service import create_trace
from app.services.version_control import commit


def run_depreciation_for_all_clients(db: Session, run_date: dt_date = None) -> dict:
    """对所有在用固定资产执行月度折旧，生成确认状态的折旧凭证"""
    if run_date is None:
        run_date = dt_date.today()
    period = f"{run_date.year}-{run_date.month:02d}"

    assets = db.query(FixedAsset).filter(
        FixedAsset.status == "in_use",
        FixedAsset.net_value > 0,
    ).all()

    total_depreciation = 0
    voucher_ids = []

    for asset in assets:
        dep = asset.monthly_depreciation
        if dep <= 0:
            continue
        # 确保残值后不再折旧
        residual = asset.original_value * asset.residual_rate / 100
        if asset.net_value - dep < residual:
            dep = round(asset.net_value - residual, 2)
        if dep <= 0:
            continue

        asset.accumulated_depreciation = round(asset.accumulated_depreciation + dep, 2)
        asset.net_value = round(asset.original_value - asset.accumulated_depreciation, 2)
        total_depreciation += dep

        vno = generate_voucher_no(db, run_date)
        entries_json = json.dumps([
            {"account_code": "660201", "account_name": "管理费用-折旧费", "debit": dep, "credit": 0, "summary": f"{asset.asset_name} 折旧"},
            {"account_code": "1602", "account_name": "累计折旧", "debit": 0, "credit": dep, "summary": f"{asset.asset_name} 折旧"},
        ], ensure_ascii=False)

        voucher = AccountingVoucher(
            id=str(uuid.uuid4()),
            voucher_no=vno,
            voucher_date=run_date,
            summary=f"系统自动折旧: {asset.asset_name} ({period})",
            entries=entries_json,
            total_debit=dep,
            total_credit=dep,
            status="confirmed",
            created_by="system",
            reviewer="自动关账引擎",
            review_comment=f"月末自动折旧 {period}",
            client_id=asset.client_id,
        )
        db.add(voucher)
        db.flush()
        create_trace(db, "voucher", voucher.id, "auto_depreciation")
        commit(db, "voucher", voucher.id, "auto_depreciation", "system",
               after={"voucher_no": vno, "asset": asset.asset_name, "depreciation": dep})
        voucher_ids.append(voucher.id)

    db.commit()
    return {
        "period": period,
        "vouchers_created": len(voucher_ids),
        "total_depreciation": round(total_depreciation, 2),
        "voucher_ids": voucher_ids,
    }
