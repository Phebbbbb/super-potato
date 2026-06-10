"""
智能任务优先级引擎 — 多因素加权评分算法

算法设计:
  Priority = Σ(wi × fi) 归一化到 [0, 100]

因子:
  f1: 截止日紧迫度 (0-1) — 越接近截止日分数越高, 权重 w=0.30
  f2: 税额规模      (0-1) — 税额越大越优先,       权重 w=0.25
  f3: 风险等级      (0-1) — 异常越多越优先,       权重 w=0.20
  f4: 客户等级      (0-1) — VIP优先,             权重 w=0.10
  f5: 积压程度      (0-1) — 待办越多越优先,       权重 w=0.10
  f6: 停滞时间      (0-1) — 越久没处理越优先,     权重 w=0.05

输出: 全局排序队列 + 每个客户/任务的细分得分
"""
import math
from datetime import date as dt_date, datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session


# 权重配置（可调）
WEIGHTS = {
    "deadline_proximity": 0.30,
    "tax_amount": 0.25,
    "risk_level": 0.20,
    "client_tier": 0.10,
    "backlog": 0.10,
    "staleness": 0.05,
}

# 客户等级映射
TIER_SCORE = {"vip": 1.0, "premium": 0.7, "standard": 0.4, "basic": 0.2}


def compute_client_priority(db: Session, client_id: str) -> dict:
    """
    计算单个客户的综合优先级

    Returns:
        {
            "client_id": "...",
            "client_name": "...",
            "priority_score": 78.5,       # 0-100
            "priority_level": "high",     # critical / high / medium / low
            "factor_scores": {...},       # 各因子得分
            "recommended_action": "立即处理 — 申报截止日临近且有高额税金待缴"
        }
    """
    from app.models.client import Client
    from app.models.filing import TaxFiling
    from app.models.voucher import AccountingVoucher
    from app.models.document import OriginalDocument

    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        return {"error": "客户不存在"}

    today = dt_date.today()

    # ================================================================
    # f1: 截止日紧迫度
    # ================================================================
    deadline_score = _calc_deadline_score(db, client_id, today)

    # ================================================================
    # f2: 税额规模
    # ================================================================
    tax_score = _calc_tax_amount_score(db, client_id, today)

    # ================================================================
    # f3: 风险等级
    # ================================================================
    risk_score = _calc_risk_score(db, client_id)

    # ================================================================
    # f4: 客户等级
    # ================================================================
    tier = getattr(client, "tier", "standard") or "standard"
    tier_score = TIER_SCORE.get(tier, 0.4)

    # ================================================================
    # f5: 积压程度
    # ================================================================
    backlog_score = _calc_backlog_score(db, client_id)

    # ================================================================
    # f6: 停滞时间
    # ================================================================
    staleness_score = _calc_staleness_score(db, client_id, today)

    # ================================================================
    # 加权综合
    # ================================================================
    raw = (
        WEIGHTS["deadline_proximity"] * deadline_score
        + WEIGHTS["tax_amount"] * tax_score
        + WEIGHTS["risk_level"] * risk_score
        + WEIGHTS["client_tier"] * tier_score
        + WEIGHTS["backlog"] * backlog_score
        + WEIGHTS["staleness"] * staleness_score
    )
    priority_score = round(raw * 100, 1)

    # 等级判定
    if priority_score >= 70:
        level = "critical"
        action = "立即处理 — 最高优先级"
    elif priority_score >= 50:
        level = "high"
        action = "优先处理 — 今日内完成"
    elif priority_score >= 30:
        level = "medium"
        action = "正常处理 — 本周内完成"
    else:
        level = "low"
        action = "按常规节奏处理"

    factor_scores = {
        "deadline_proximity": round(deadline_score, 3),
        "tax_amount": round(tax_score, 3),
        "risk_level": round(risk_score, 3),
        "client_tier": round(tier_score, 3),
        "backlog": round(backlog_score, 3),
        "staleness": round(staleness_score, 3),
    }

    return {
        "client_id": client_id,
        "client_name": client.name,
        "tier": tier,
        "priority_score": priority_score,
        "priority_level": level,
        "factor_scores": factor_scores,
        "weights": WEIGHTS,
        "recommended_action": action,
        "computed_at": today.isoformat(),
    }


def get_priority_queue(db: Session, client_ids: list[str] = None) -> list[dict]:
    """
    生成全局优先级队列（所有客户/指定客户按优先级排序）

    Returns:
        [{client_id, client_name, priority_score, priority_level, factor_scores, ...}, ...]
    """
    from app.models.client import Client

    q = db.query(Client).filter(Client.is_active == True)
    if client_ids:
        q = q.filter(Client.id.in_(client_ids))
    clients = q.all()

    results = []
    for c in clients:
        try:
            r = compute_client_priority(db, c.id)
            if "error" not in r:
                results.append(r)
        except Exception:
            pass

    results.sort(key=lambda r: r["priority_score"], reverse=True)
    return results


def get_daily_worklist(db: Session, top_n: int = 10) -> dict:
    """
    今日工作清单 — 按优先级排序的待办事项

    返回按优先级排序的具体可执行任务列表
    """
    from app.models.client import Client
    from app.models.filing import TaxFiling

    today = dt_date.today()
    priority_queue = get_priority_queue(db)

    worklist = []
    for item in priority_queue:
        cid = item["client_id"]
        # 获取该客户的待办申报
        pending_filings = db.query(TaxFiling).filter(
            TaxFiling.client_id == cid,
            TaxFiling.status.in_(["pending", "draft"]),
        ).all()

        tasks = []
        for pf in pending_filings:
            tasks.append({
                "task_type": "filing",
                "tax_type": pf.tax_type,
                "period": pf.period,
                "status": pf.status,
                "task_id": pf.id,
            })

        worklist.append({
            **item,
            "pending_tasks": tasks,
            "pending_count": len(tasks),
        })

    return {
        "date": today.isoformat(),
        "total_clients": len(worklist),
        "critical_count": sum(1 for w in worklist if w["priority_level"] == "critical"),
        "high_count": sum(1 for w in worklist if w["priority_level"] == "high"),
        "worklist": worklist[:top_n],
    }


# ================================================================
# 因子计算函数
# ================================================================

def _calc_deadline_score(db: Session, client_id: str, today: dt_date) -> float:
    """截止日紧迫度: 越近越高"""
    from app.models.filing import TaxFiling

    # 找最近的 pending 申报
    pending = db.query(TaxFiling).filter(
        TaxFiling.client_id == client_id,
        TaxFiling.status.in_(["pending", "draft"]),
    ).order_by(TaxFiling.period.asc()).all()

    if not pending:
        return 0.0

    # 默认每月15号截止
    min_days = 365
    for pf in pending:
        try:
            y, m = map(int, pf.period.split("-"))
        except Exception:
            continue
        deadline = dt_date(y, m, 15)
        # 周末顺延
        while deadline.weekday() >= 5:
            deadline += timedelta(days=1)
        days_left = (deadline - today).days
        min_days = min(min_days, days_left)

    if min_days <= 0:
        return 1.0  # 已逾期
    elif min_days <= 1:
        return 0.95
    elif min_days <= 3:
        return 0.80
    elif min_days <= 7:
        return 0.55
    elif min_days <= 14:
        return 0.30
    elif min_days <= 30:
        return 0.10
    else:
        return 0.02


def _calc_tax_amount_score(db: Session, client_id: str, today: dt_date) -> float:
    """税额规模: 税金越大越高（对数归一化）"""
    from app.services.report_service import get_confirmed_entries, _sum_by_account, _month_range

    ms, me = _month_range(today.year, today.month)
    entries = get_confirmed_entries(db, str(ms), str(me), client_id=client_id)

    output_vat = _sum_by_account(entries, ["2221001"], "credit")
    input_vat = _sum_by_account(entries, ["2221002"], "debit")
    net_vat = max(output_vat - input_vat, 0)

    revenue = _sum_by_account(entries, ["6001", "6051"], "credit")
    expense = _sum_by_account(entries, ["6401", "6402", "6403", "6601", "6602", "6603"], "debit")
    profit = revenue - expense
    est_cit = profit * 0.05 if 0 < profit <= 3_000_000 else (profit * 0.25 if profit > 3_000_000 else 0)

    total_tax = net_vat + est_cit

    if total_tax <= 0:
        return 0.0

    # 对数归一化: 1万→0.3, 10万→0.6, 100万→0.9
    log_val = math.log10(max(total_tax, 1))
    return min(1.0, log_val / 7.0)  # log10(10^7=1千万) → 1.0


def _calc_risk_score(db: Session, client_id: str) -> float:
    """风险等级: 预检分数越低、异常越多，分越高"""
    try:
        from app.services.precheck_engine import run_precheck
        precheck = run_precheck(db, client_id)
        score = precheck.get("score", 100)
        # 分数越低风险越高 → 归一化
        risk = max(0, (100 - score) / 100)
    except Exception:
        risk = 0.0

    return risk


def _calc_backlog_score(db: Session, client_id: str) -> float:
    """积压程度: 待办越多越高"""
    from app.models.filing import TaxFiling
    from app.models.document import OriginalDocument

    pending_filings = db.query(TaxFiling).filter(
        TaxFiling.client_id == client_id,
        TaxFiling.status.in_(["pending", "draft", "failed"]),
    ).count()

    pending_docs = db.query(OriginalDocument).filter(
        OriginalDocument.client_id == client_id,
        OriginalDocument.ocr_status == "pending",
    ).count()

    total_pending = pending_filings + pending_docs

    if total_pending == 0:
        return 0.0
    elif total_pending <= 2:
        return 0.2
    elif total_pending <= 5:
        return 0.5
    elif total_pending <= 10:
        return 0.75
    else:
        return 1.0


def _calc_staleness_score(db: Session, client_id: str, today: dt_date) -> float:
    """停滞时间: 越久没活动越高"""
    from app.models.voucher import AccountingVoucher

    last_voucher = db.query(AccountingVoucher).filter(
        AccountingVoucher.client_id == client_id,
    ).order_by(AccountingVoucher.created_at.desc()).first()

    if not last_voucher or not last_voucher.created_at:
        return 0.5  # 无历史，中性

    last_date = last_voucher.created_at.date() if hasattr(last_voucher.created_at, 'date') else last_voucher.created_at
    days_since = (today - last_date).days if hasattr(last_date, 'days') else (today - dt_date.fromisoformat(str(last_date)[:10])).days

    if days_since <= 1:
        return 0.0
    elif days_since <= 3:
        return 0.1
    elif days_since <= 7:
        return 0.3
    elif days_since <= 14:
        return 0.5
    elif days_since <= 30:
        return 0.75
    else:
        return 1.0
