"""
预测性税务分析引擎 — 时序预测 + 税负推演 + 现金流投影 + 风险预判

纯 Python 实现，零外部依赖。算法：
  1. 自适应指数平滑（α 自动调参）  — 月度收入/费用/税负预测
  2. 加权线性回归                  — 年度趋势外推
  3. 蒙特卡洛区间估计              — 250 次抽样给出 80%/95% 置信区间
  4. 税负仿真                      — 在企业所得税分段函数上推演
  5. 现金流投影                    — 应付/应收/税负/工资联合推演
  6. 综合风险评分                  — 多维归一化加权

所有预测附带置信区间，避免给用户虚假的精确感。
"""
import math
import random
from datetime import date as dt_date, timedelta
from collections import defaultdict
from typing import Optional
from sqlalchemy.orm import Session


# ═══════════════════════════════════════════════════════════════
# 基础统计算法
# ═══════════════════════════════════════════════════════════════

def _adaptive_smooth(series: list[float], horizon: int = 3) -> tuple[list[float], float]:
    """
    自适应指数平滑 — 用 SSE 最小化选择最优 α ∈ [0.1, 0.9]

    Returns: (forecast_list, alpha_used)
    """
    if len(series) < 3:
        return [series[-1]] * horizon if series else [0] * horizon, 0.5

    best_alpha, best_sse = 0.3, float("inf")
    n = len(series)

    for alpha in [a / 10 for a in range(1, 10)]:
        sse = 0
        smoothed = series[0]
        for t in range(1, n):
            forecast = smoothed
            sse += (series[t] - forecast) ** 2
            smoothed = alpha * series[t] + (1 - alpha) * smoothed
        if sse < best_sse:
            best_sse = sse
            best_alpha = alpha

    # 用最优 α 做预测
    smoothed = series[0]
    for v in series[1:]:
        smoothed = best_alpha * v + (1 - best_alpha) * smoothed

    forecast = [smoothed]
    for _ in range(1, horizon):
        forecast.append(forecast[-1])  # 纯水平预测（无趋势时最稳）
    return forecast, best_alpha


def _weighted_linear_regression(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    """
    加权线性回归 y = a + b*x
    近期的点权重更高 (w[t] = t / sum(t))

    Returns: (intercept, slope, r_squared)
    """
    n = len(xs)
    if n < 2:
        return (ys[0], 0, 0) if ys else (0, 0, 0)

    weights = [i + 1 for i in range(n)]  # 近期权重更高
    w_sum = sum(weights)
    w_x = sum(w * x for w, x in zip(weights, xs)) / w_sum
    w_y = sum(w * y for w, y in zip(weights, ys)) / w_sum

    num = sum(w * (x - w_x) * (y - w_y) for w, x, y in zip(weights, xs, ys))
    den = sum(w * (x - w_x) ** 2 for w, x in zip(weights, xs))
    slope = num / max(den, 1e-9)
    intercept = w_y - slope * w_x

    # R²
    y_hats = [intercept + slope * x for x in xs]
    ss_res = sum((y - yh) ** 2 for y, yh in zip(ys, y_hats))
    ss_tot = sum((y - w_y) ** 2 for y in ys)
    r2 = max(0, 1 - ss_res / max(ss_tot, 1e-9))

    return intercept, slope, r2


def _monte_carlo_bands(
    forecast_fn,  # callable: () -> list[float]
    n_simulations: int = 250,
    horizon: int = 6,
) -> dict:
    """蒙特卡洛模拟 → 预测区间"""
    all_paths = []
    for _ in range(n_simulations):
        try:
            path = forecast_fn()
            all_paths.append(path[:horizon])
        except Exception:
            continue

    if not all_paths:
        return {"p50": [], "p80_low": [], "p80_high": [], "p95_low": [], "p95_high": []}

    bands = {"p50": [], "p80_low": [], "p80_high": [], "p95_low": [], "p95_high": []}
    for i in range(min(horizon, len(all_paths[0]))):
        vals = sorted([p[i] for p in all_paths if i < len(p)])
        if not vals:
            continue
        n_v = len(vals)
        bands["p50"].append(vals[n_v // 2])
        bands["p80_low"].append(vals[int(n_v * 0.10)])
        bands["p80_high"].append(vals[int(n_v * 0.90)])
        bands["p95_low"].append(vals[int(n_v * 0.025)])
        bands["p95_high"].append(vals[int(n_v * 0.975)])
    return bands


# ═══════════════════════════════════════════════════════════════
# 主预测入口
# ═══════════════════════════════════════════════════════════════

def run_predictive_analytics(db: Session, client_id: str, horizon_months: int = 6) -> dict:
    """
    全量预测分析

    Returns:
      {
        "client_id", "generated_at",
        "revenue_forecast":    {p50, p80_low, p80_high, p95_low, p95_high, trend, r2},
        "expense_forecast":    {...},
        "profit_forecast":     {...},
        "tax_liability":       {vat, cit, surtax, stamp_duty, total, by_month},
        "cash_flow_projection":{inflow, outflow, net_per_month, ending_cash, risk_level},
        "risk_assessment":     {overall_score, factors: [...], recommendations: [...]},
      }
    """
    from app.models.client import Client
    from app.services.report_service import get_confirmed_entries, _sum_by_account, _month_range

    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        return {"error": "客户不存在"}

    today = dt_date.today()
    horizon = max(3, min(horizon_months, 12))

    # ── 加载 24 个月历史 ──
    history = _load_monthly_history(db, client_id, today.year, today.month, months=24)
    if not history:
        return {"error": "历史数据不足，无法预测"}

    rev_series = [h["revenue"] for h in history]
    exp_series = [h["expense"] for h in history]
    periods = [h["period"] for h in history]

    # ── 1. 收入预测 ──
    rev_result = _forecast_series(rev_series, horizon, "revenue")

    # ── 2. 费用预测 ──
    exp_result = _forecast_series(exp_series, horizon, "expense")

    # ── 3. 利润预测 ──
    profit_series = [max(r - e, 0) for r, e in zip(rev_series, exp_series)]
    profit_result = _forecast_series(profit_series, horizon, "profit")

    # ── 4. 税负推演 ──
    tax_liability = _forecast_tax_liability(
        rev_result["p50"], exp_result["p50"], profit_result["p50"],
        client.taxpayer_type or "small",
    )

    # ── 5. 现金流投影 ──
    cash_flow = _project_cash_flow(db, client_id, rev_result["p50"], exp_result["p50"],
                                   tax_liability, horizon)

    # ── 6. 风险预判 ──
    risk = _assess_predictive_risk(db, client_id, rev_result, exp_result, profit_result,
                                   tax_liability, cash_flow, today)

    # 生成未来月份标签
    future_months = []
    y, m = today.year, today.month
    for i in range(1, horizon + 1):
        m += 1
        if m > 12:
            m = 1
            y += 1
        future_months.append(f"{y}-{m:02d}")

    return {
        "client_id": client_id,
        "client_name": client.name,
        "generated_at": today.isoformat(),
        "horizon_months": horizon,
        "forecast_months": future_months,
        "revenue_forecast": rev_result,
        "expense_forecast": exp_result,
        "profit_forecast": profit_result,
        "tax_liability": tax_liability,
        "cash_flow_projection": cash_flow,
        "risk_assessment": risk,
        "data_quality": {
            "historical_months": len(history),
            "revenue_r2": rev_result.get("r2", 0),
            "expense_r2": exp_result.get("r2", 0),
            "confidence": "high" if len(history) >= 12 and rev_result.get("r2", 0) > 0.6 else "medium" if len(history) >= 6 else "low",
        },
    }


def _load_monthly_history(db: Session, client_id: str, year: int, month: int, months: int = 24) -> list[dict]:
    """加载历史月度数据（同 anomaly_detector 优化逻辑 — 单次查询）"""
    from app.services.report_service import get_confirmed_entries, _sum_by_account, _month_range

    ty, tm = year, month
    for _ in range(months):
        tm -= 1
        if tm == 0:
            tm = 12
            ty -= 1
    earliest_start, _ = _month_range(ty, tm)
    _, latest_end = _month_range(year, month)

    all_entries = get_confirmed_entries(db, str(earliest_start), str(latest_end), client_id=client_id)

    by_period: dict[str, list] = {}
    for e in all_entries:
        vd = e.get("voucher_date", "")
        period_key = vd[:7] if vd else ""
        by_period.setdefault(period_key, []).append(e)

    history = []
    ty, tm = year, month
    for _ in range(months):
        tm -= 1
        if tm == 0:
            tm = 12
            ty -= 1
        period_key = f"{ty}-{tm:02d}"
        month_entries = by_period.get(period_key, [])

        history.append({
            "period": period_key,
            "revenue": _sum_by_account(month_entries, ["6001", "6051"], "credit"),
            "expense": _sum_by_account(month_entries, ["6401", "6402", "6403", "6601", "6602", "6603"], "debit"),
            "output_vat": _sum_by_account(month_entries, ["2221001"], "credit"),
            "input_vat": _sum_by_account(month_entries, ["2221002"], "debit"),
        })

    return history


def _forecast_series(series: list[float], horizon: int, label: str) -> dict:
    """混合预测：自适应平滑 + 加权线性回归 → 中位数 + 蒙特卡洛区间"""
    # 指数平滑基线
    ses_forecast, alpha = _adaptive_smooth(series, horizon)

    # 线性回归趋势
    xs = list(range(len(series)))
    intercept, slope, r2 = _weighted_linear_regression(xs, series)
    lr_forecast = [max(0, intercept + slope * (len(series) + i)) for i in range(horizon)]

    # 组合预测 (SES*0.6 + LR*0.4，短期更信平滑，长期更信趋势)
    combined = []
    for i in range(horizon):
        w_ses = 0.6 - i * 0.05  # 越远期越信回归
        w_ses = max(0.3, w_ses)
        w_lr = 1 - w_ses
        combined.append(round(ses_forecast[i] * w_ses + lr_forecast[i] * w_lr, 2))

    # 蒙特卡洛区间
    mean_val = sum(series) / max(len(series), 1)
    std_val = math.sqrt(sum((v - mean_val) ** 2 for v in series) / max(len(series), 1)) if len(series) > 1 else 0
    noise_pct = min(std_val / max(mean_val, 1), 0.3)  # 噪声比例上限 30%

    def mc_fn():
        return [round(v * (1 + random.gauss(0, noise_pct)), 2) for v in combined]

    bands = _monte_carlo_bands(mc_fn, n_simulations=250, horizon=horizon)

    return {
        "label": label,
        "p50": combined,
        "p80_low": bands.get("p80_low", []),
        "p80_high": bands.get("p80_high", []),
        "p95_low": bands.get("p95_low", []),
        "p95_high": bands.get("p95_high", []),
        "trend": "up" if slope > 0 else "down" if slope < 0 else "flat",
        "trend_pct_monthly": round(slope / max(mean_val, 1) * 100, 2),
        "alpha": round(alpha, 2),
        "r2": round(r2, 3),
        "volatility_pct": round(noise_pct * 100, 1),
    }


# ═══════════════════════════════════════════════════════════════
# 税负推演
# ═══════════════════════════════════════════════════════════════

def _forecast_tax_liability(
    rev_forecast: list[float],
    exp_forecast: list[float],
    profit_forecast: list[float],
    taxpayer_type: str,
) -> dict:
    """在预测利润上推演各税种应纳税额"""
    monthly = []
    total_vat = total_cit = total_surtax = total_stamp = 0.0

    for i, (rev, exp, profit) in enumerate(zip(rev_forecast, exp_forecast, profit_forecast)):
        # 增值税（简化：销项 = 收入 × 13%，进项 = 费用 × 13% × 0.6）
        output_vat = rev * 0.13
        input_vat = exp * 0.13 * 0.6
        vat = max(output_vat - input_vat, 0)

        # 企业所得税（分段函数）
        if profit <= 0:
            cit = 0
        elif profit <= 3_000_000:
            cit = profit * 0.05
        else:
            cit = profit * 0.25

        # 附加税
        surtax = vat * 0.12

        # 印花税（≈收入 × 0.03%）
        stamp = rev * 0.0003

        monthly.append({
            "month_index": i + 1,
            "vat": round(vat, 2),
            "corporate_income": round(cit, 2),
            "surtax": round(surtax, 2),
            "stamp_duty": round(stamp, 2),
            "total": round(vat + cit + surtax + stamp, 2),
        })
        total_vat += vat
        total_cit += cit
        total_surtax += surtax
        total_stamp += stamp

    return {
        "monthly": monthly,
        "total_vat": round(total_vat, 2),
        "total_cit": round(total_cit, 2),
        "total_surtax": round(total_surtax, 2),
        "total_stamp_duty": round(total_stamp, 2),
        "grand_total": round(total_vat + total_cit + total_surtax + total_stamp, 2),
        "avg_monthly": round((total_vat + total_cit + total_surtax + total_stamp) / max(len(monthly), 1), 2),
    }


# ═══════════════════════════════════════════════════════════════
# 现金流投影
# ═══════════════════════════════════════════════════════════════

def _project_cash_flow(
    db: Session,
    client_id: str,
    rev_forecast: list[float],
    exp_forecast: list[float],
    tax_liability: dict,
    horizon: int,
) -> dict:
    """现金流投影 — 结合应付/应收/税负/工资推演"""
    from app.models.bank import BankAccount, BankStatementLine
    from app.models.voucher import AccountingVoucher

    # 当前现金余额（从最近的银行流水余额汇总）
    bank_account_ids = [
        a[0] for a in db.query(BankAccount.id).filter(
            BankAccount.client_id == client_id,
            BankAccount.is_active == True,
        ).all()
    ]
    current_cash = 0.0
    if bank_account_ids:
        latest_balances = (
            db.query(BankStatementLine.balance)
            .filter(BankStatementLine.bank_account_id.in_(bank_account_ids))
            .order_by(BankStatementLine.transaction_date.desc())
            .limit(len(bank_account_ids))
            .all()
        )
        current_cash = sum(float(b[0] or 0) for b in latest_balances)

    # AR/AP 简单估算（本月收入30%未收，费用20%未付）
    ar_ratio = 0.30  # 应收账款比例
    ap_ratio = 0.20  # 应付账款比例

    # 估算工资（占费用 30%）
    salary_ratio = 0.30

    monthly = []
    ending_cash = current_cash

    for i, (rev, exp) in enumerate(zip(rev_forecast, exp_forecast)):
        # 现金流入 = 上月AR回收 + 本月收入 × (1-AR)
        prev_ar = rev_forecast[i - 1] * ar_ratio if i > 0 else 0
        inflow = prev_ar + rev * (1 - ar_ratio)

        # 现金流出 = 费用支出 + 税负 + 工资 + 上月AP支付
        prev_ap = exp_forecast[i - 1] * ap_ratio if i > 0 else 0
        tax_pmt = tax_liability["monthly"][i]["total"] if i < len(tax_liability["monthly"]) else 0
        salary = exp * salary_ratio
        outflow = exp * (1 - ap_ratio) + prev_ap + tax_pmt + salary

        net = inflow - outflow
        ending_cash += net

        monthly.append({
            "month_index": i + 1,
            "inflow": round(inflow, 2),
            "outflow": round(outflow, 2),
            "net": round(net, 2),
            "ending_cash": round(ending_cash, 2),
        })

    # 风险评估
    min_monthly_net = min(m["net"] for m in monthly) if monthly else 0
    if ending_cash < 0:
        cash_risk = "critical"  # 资金链断裂
    elif min_monthly_net < 0 and ending_cash < current_cash * 0.3:
        cash_risk = "high"
    elif min_monthly_net < 0:
        cash_risk = "medium"
    else:
        cash_risk = "low"

    return {
        "current_cash": round(current_cash, 2),
        "monthly": monthly,
        "ending_cash": round(ending_cash, 2),
        "cash_change": round(ending_cash - current_cash, 2),
        "risk_level": cash_risk,
        "min_monthly_net": round(min_monthly_net, 2),
        "warning": "预测期末现金为负，存在资金链断裂风险" if ending_cash < 0 else None,
    }


# ═══════════════════════════════════════════════════════════════
# 综合风险预判
# ═══════════════════════════════════════════════════════════════

def _assess_predictive_risk(
    db: Session,
    client_id: str,
    rev_result: dict,
    exp_result: dict,
    profit_result: dict,
    tax_liability: dict,
    cash_flow: dict,
    today: dt_date,
) -> dict:
    """多维风险预判 — 综合评分 0-100"""
    factors = []
    total_score = 0
    total_weight = 0

    # 1. 收入下滑风险 (权重 20)
    w = 20
    trend = rev_result.get("trend_pct_monthly", 0)
    if trend < -5:
        score = min(100, abs(trend) * 4)
        factors.append({"factor": "收入下滑", "score": round(score), "weight": w, "detail": f"月均趋势 {trend:+.1f}%，收入加速下滑"})
    elif trend < 0:
        score = abs(trend) * 2
        factors.append({"factor": "收入小幅下滑", "score": round(score), "weight": w, "detail": f"月均趋势 {trend:+.1f}%"})
    else:
        factors.append({"factor": "收入趋势健康", "score": 0, "weight": w, "detail": f"月均趋势 {trend:+.1f}%"})
    total_score += factors[-1]["score"] * w / 100
    total_weight += w

    # 2. 利润压缩风险 (权重 20)
    w = 20
    profit_margin = sum(profit_result["p50"]) / max(sum(rev_result["p50"]), 1) * 100
    if profit_margin < 5:
        score = 70
        factors.append({"factor": "利润率极低", "score": score, "weight": w, "detail": f"预测利润率 {profit_margin:.1f}%，接近亏损边缘"})
    elif profit_margin < 15:
        score = 30
        factors.append({"factor": "利润率偏低", "score": score, "weight": w, "detail": f"预测利润率 {profit_margin:.1f}%"})
    else:
        factors.append({"factor": "利润率健康", "score": 0, "weight": w, "detail": f"预测利润率 {profit_margin:.1f}%"})
    total_score += factors[-1]["score"] * w / 100
    total_weight += w

    # 3. 现金流风险 (权重 25)
    w = 25
    cash_risk = cash_flow.get("risk_level", "low")
    if cash_risk == "critical":
        score = 100
        factors.append({"factor": "资金链断裂风险", "score": score, "weight": w, "detail": "预测期末现金为负"})
    elif cash_risk == "high":
        score = 70
        factors.append({"factor": "现金流紧张", "score": score, "weight": w, "detail": "连续月度现金净流出"})
    elif cash_risk == "medium":
        score = 40
        factors.append({"factor": "现金流需关注", "score": score, "weight": w, "detail": "存在单月现金净流出"})
    else:
        factors.append({"factor": "现金流健康", "score": 0, "weight": w, "detail": "预测期现金流正向"})
    total_score += factors[-1]["score"] * w / 100
    total_weight += w

    # 4. 税负陡增风险 (权重 20)
    w = 20
    avg_monthly_tax = tax_liability.get("avg_monthly", 0)
    # 简单基准：小规模纳税人月均税负通常 <5000
    if avg_monthly_tax > 50000:
        score = 60
        factors.append({"factor": "税负陡增", "score": score, "weight": w, "detail": f"预测月均税负 ¥{avg_monthly_tax:,.0f}，显著偏高"})
    elif avg_monthly_tax > 20000:
        score = 30
        factors.append({"factor": "税负偏高", "score": score, "weight": w, "detail": f"预测月均税负 ¥{avg_monthly_tax:,.0f}"})
    else:
        factors.append({"factor": "税负正常", "score": 0, "weight": w, "detail": f"预测月均税负 ¥{avg_monthly_tax:,.0f}"})
    total_score += factors[-1]["score"] * w / 100
    total_weight += w

    # 5. 预测不确定性 (权重 15)
    w = 15
    r2 = rev_result.get("r2", 0)
    if r2 < 0.3:
        score = 50
        factors.append({"factor": "预测不确定性高", "score": score, "weight": w, "detail": f"R²={r2:.2f}，历史数据波动大"})
    elif r2 < 0.6:
        score = 25
        factors.append({"factor": "预测不确定性中", "score": score, "weight": w, "detail": f"R²={r2:.2f}"})
    else:
        factors.append({"factor": "预测可靠", "score": 0, "weight": w, "detail": f"R²={r2:.2f}"})
    total_score += factors[-1]["score"] * w / 100
    total_weight += w

    overall = round(total_score / max(total_weight, 1) * 100)

    # 风险等级
    if overall >= 60:
        level = "critical"
    elif overall >= 35:
        level = "high"
    elif overall >= 15:
        level = "medium"
    else:
        level = "low"

    # 生成建议
    recommendations = []
    for f in factors:
        if f["score"] >= 50:
            if "收入" in f["factor"]:
                recommendations.append("收入持续下滑，建议检查客户流失原因并开拓新客源")
            elif "利润" in f["factor"]:
                recommendations.append("利润率偏低，建议审查成本结构，寻找节支空间")
            elif "资金" in f["factor"]:
                recommendations.append("现金流预警，建议提前安排融资或压缩应付账款周转期")
            elif "税负" in f["factor"]:
                recommendations.append("税负偏高，建议启动税务优化分析，检查可享受的税收优惠")
            elif "不确定" in f["factor"]:
                recommendations.append("历史数据波动较大，建议积累更多数据后再做重大决策")

    return {
        "overall_score": overall,
        "risk_level": level,
        "factors": factors,
        "recommendations": recommendations,
        "assessed_at": today.isoformat(),
    }
