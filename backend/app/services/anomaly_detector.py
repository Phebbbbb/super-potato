"""异常检测服务 — 原有 API + 新增 Benford/Z-Score 引擎"""
from sqlalchemy.orm import Session
from app.services.tax_anomaly_detector import analyze_tax_risk, check_benford, check_zscore_outliers


def detect_all_anomalies(db: Session, client_id: str, period: str = None) -> dict:
    """对指定客户执行全量异常检测"""
    from app.models.voucher import AccountingVoucher

    q = db.query(AccountingVoucher).filter(AccountingVoucher.client_id == client_id)
    vouchers = q.order_by(AccountingVoucher.created_at.desc()).limit(200).all()

    if not vouchers:
        return {"client_id": client_id, "has_anomaly": False, "findings": []}

    voucher_dicts = [
        {
            "id": v.id, "voucher_no": v.voucher_no,
            "voucher_date": v.voucher_date.isoformat() if v.voucher_date else "",
            "summary": v.summary, "total_debit": v.total_debit,
            "total_credit": v.total_credit, "status": v.status,
        }
        for v in vouchers
    ]
    amounts = [v.total_debit for v in vouchers if v.total_debit]

    result = analyze_tax_risk(voucher_dicts, amounts)

    return {
        "client_id": client_id,
        "period": period,
        "voucher_count": len(vouchers),
        "has_anomaly": result.has_anomaly,
        "risk_level": result.risk_level,
        "risk_score": result.risk_score,
        "findings": result.findings,
        "recommendation": result.recommendation,
    }


def run_batch_anomaly_detection(db: Session) -> list[dict]:
    """批量检测所有客户"""
    from app.models.voucher import AccountingVoucher
    from sqlalchemy import distinct
    from app.services.tax_anomaly_detector import analyze_tax_risk

    client_ids = [
        row[0] for row in
        db.query(distinct(AccountingVoucher.client_id)).filter(AccountingVoucher.client_id.isnot(None)).all()
    ]

    results = []
    for cid in client_ids[:20]:  # 限制最多20个客户
        vouchers = db.query(AccountingVoucher).filter(
            AccountingVoucher.client_id == cid
        ).order_by(AccountingVoucher.created_at.desc()).limit(100).all()

        if not vouchers:
            continue

        voucher_dicts = [
            {"id": v.id, "voucher_no": v.voucher_no,
             "voucher_date": v.voucher_date.isoformat() if v.voucher_date else "",
             "summary": v.summary, "total_debit": v.total_debit,
             "total_credit": v.total_credit, "status": v.status}
            for v in vouchers
        ]
        amounts = [v.total_debit for v in vouchers if v.total_debit]
        result = analyze_tax_risk(voucher_dicts, amounts)

        if result.has_anomaly:
            results.append({
                "client_id": cid,
                "risk_level": result.risk_level,
                "risk_score": result.risk_score,
                "findings_count": len(result.findings),
            })

    return results
