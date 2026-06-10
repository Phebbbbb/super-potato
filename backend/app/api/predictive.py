"""预测性分析 API"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.user import User
from app.services import auth
from app.services.predictive import run_predictive_analytics

router = APIRouter()


@router.get("/predictive/analytics")
def get_predictive_analytics(
    client_id: str = Query(..., description="客户ID"),
    horizon: int = Query(6, ge=3, le=12, description="预测月数"),
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    预测性税务分析 — 收入/费用/利润预测 + 税负推演 + 现金流投影 + 风险预判
    """
    auth.check_client_access(client_id, user, db)
    return run_predictive_analytics(db, client_id, horizon)


@router.get("/predictive/summary")
def get_predictive_summary(
    client_id: str = Query(..., description="客户ID"),
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    轻量摘要 — 仅返回预测趋势方向和关键风险指标，用于 Dashboard 卡片
    """
    result = run_predictive_analytics(db, client_id, horizon_months=6)
    if "error" in result:
        return result

    rev = result["revenue_forecast"]
    risk = result["risk_assessment"]
    cf = result["cash_flow_projection"]

    return {
        "client_id": client_id,
        "generated_at": result["generated_at"],
        "revenue_trend": rev.get("trend"),
        "revenue_trend_pct": rev.get("trend_pct_monthly"),
        "revenue_next_month": rev["p50"][0] if rev.get("p50") else 0,
        "profit_margin": round(
            sum(result["profit_forecast"]["p50"]) / max(sum(rev["p50"]), 1) * 100, 1
        ) if rev.get("p50") else 0,
        "tax_next_6m": result["tax_liability"]["grand_total"],
        "cash_risk": cf.get("risk_level"),
        "ending_cash": cf.get("ending_cash", 0),
        "risk_score": risk.get("overall_score"),
        "risk_level": risk.get("risk_level"),
        "top_risk": risk["factors"][0]["factor"] if risk.get("factors") else "无",
        "top_recommendation": risk["recommendations"][0] if risk.get("recommendations") else "",
        "data_confidence": result["data_quality"]["confidence"],
    }
