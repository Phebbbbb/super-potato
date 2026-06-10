"""
预检 + 税务优化 API — "模拟考"系统

核心价值：在提交到官方系统前，本地完整预检 + 算法优化
"""
from fastapi import APIRouter, Query, Depends
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.auth import get_current_user
from app.services.precheck_engine import run_precheck, run_batch_precheck
from app.services.tax_optimizer import run_tax_optimization
from app.services.tax_dp_optimizer import cliff_analysis, optimize_with_scenario, optimize_multi_period

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/precheck/{client_id}")
def precheck_client(client_id: str, period: str = Query(None), db: Session = Depends(get_db)):
    """单客户预检 — 返回就绪度评分 + 所有检查项"""
    return run_precheck(db, client_id, period)


@router.post("/precheck/batch")
def precheck_batch(data: dict, db: Session = Depends(get_db)):
    """
    批量预检

    body: {"client_ids": ["id1", "id2", ...]} 或 {"client_ids": []} 表示全部
    """
    client_ids = data.get("client_ids") or None
    results = run_batch_precheck(db, client_ids)
    summary = {
        "total": len(results),
        "passed": sum(1 for r in results if r.get("passed")),
        "excellent": sum(1 for r in results if r.get("grade") == "excellent"),
        "good": sum(1 for r in results if r.get("grade") == "good"),
        "warning": sum(1 for r in results if r.get("grade") == "warning"),
        "danger": sum(1 for r in results if r.get("grade") == "danger"),
    }
    return {"summary": summary, "clients": results}


@router.get("/optimize/{client_id}")
def optimize_client(client_id: str, period: str = Query(None), db: Session = Depends(get_db)):
    """单客户税务优化 — 算法驱动的合法节税方案"""
    return run_tax_optimization(db, client_id, period)


@router.post("/optimize/batch")
def optimize_batch(data: dict, db: Session = Depends(get_db)):
    """
    批量税务优化 — 找出最需要优化的客户

    body: {"client_ids": ["id1", ...]} 或空数组表示全部
    """
    from app.models.client import Client

    client_ids = data.get("client_ids") or None
    q = db.query(Client)
    if client_ids:
        q = q.filter(Client.id.in_(client_ids))
    clients = q.all()

    results = []
    total_savings = 0
    for c in clients:
        try:
            r = run_tax_optimization(db, c.id)
            results.append(r)
            total_savings += r.get("potential_savings", 0)
        except Exception as e:
            results.append({"client_id": c.id, "client_name": c.name, "error": str(e)})

    # 按潜在节税金额从大到小排序
    results.sort(key=lambda r: r.get("potential_savings", 0), reverse=True)

    return {
        "total_clients": len(clients),
        "total_potential_savings": round(total_savings, 2),
        "top_opportunities": [
            {
                "client_id": r["client_id"],
                "client_name": r.get("client_name", ""),
                "potential_savings": r.get("potential_savings", 0),
                "recommendation": r.get("recommendation", ""),
            }
            for r in results[:10]
            if r.get("potential_savings", 0) > 0
        ],
        "details": results,
    }


# ========================
# DP 多期优化 + 悬崖检测
# ========================

@router.get("/dp-optimize/{client_id}")
def dp_optimize_client(client_id: str, db: Session = Depends(get_db)):
    """多期 DP 税务优化 — 3年全局最优路径"""
    from app.models.client import Client
    from app.services.report_service import get_confirmed_entries, _sum_by_account, _month_range
    from datetime import date

    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        return {"error": "客户不存在"}

    today = date.today()
    year_start = date(today.year, 1, 1)
    year_end = date(today.year, 12, 31)
    entries = get_confirmed_entries(db, str(year_start), str(year_end))
    entries = [e for e in entries if e.get("client_id") == client_id]

    ytd_rev = _sum_by_account(entries, ["6001", "6051"], "credit")
    ytd_exp = (
        _sum_by_account(entries, ["6401", "6402", "6403"], "debit")
        + _sum_by_account(entries, ["6601", "6602", "6603"], "debit")
    )

    client_data = {
        "ytd_revenue": ytd_rev,
        "ytd_expense": ytd_exp,
        "months_elapsed": today.month,
        "growth_rate_estimate": 0.05,
    }
    return optimize_with_scenario(client_data)


@router.get("/cliff-check/{client_id}")
def cliff_check(client_id: str, db: Session = Depends(get_db)):
    """CIT 悬崖快速检测 — 轻量级，适合 Dashboard 实时展示"""
    from app.services.report_service import get_confirmed_entries, _sum_by_account, _month_range
    from datetime import date

    today = date.today()
    year_start = date(today.year, 1, 1)
    entries = get_confirmed_entries(db, str(year_start), str(today))
    entries = [e for e in entries if e.get("client_id") == client_id]

    ytd_rev = _sum_by_account(entries, ["6001", "6051"], "credit")
    ytd_exp = (
        _sum_by_account(entries, ["6401", "6402", "6403"], "debit")
        + _sum_by_account(entries, ["6601", "6602", "6603"], "debit")
    )
    ytd_profit = ytd_rev - ytd_exp
    months_elapsed = max(today.month, 1)
    monthly_avg = ytd_profit / months_elapsed

    return cliff_analysis(ytd_profit, months_elapsed, monthly_avg)
