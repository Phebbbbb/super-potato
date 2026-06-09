"""
税务优化引擎 — 基于约束优化的合法税务筹划

核心算法：
  1. 利润阈值优化 — 小微企业 CIT 悬崖检测与避让
  2. 场景树搜索     — 多决策点的最优路径
  3. 增值税进项优化 — 抵扣时点选择

算法哲学：
  不是帮企业逃税，而是在合法边界内找到最优解。
  所有推荐方案都附带法规依据，确保合规。
"""
import json
from datetime import date as dt_date, timedelta
from typing import Optional
from dataclasses import dataclass, field
from sqlalchemy.orm import Session


# ============================================================
# 中国小微企业 CIT 税率结构（2023-2027）
# ============================================================
# 年应纳税所得额 ≤ 100万    : 减按25%计入 → 实际税率 5%  (2023起调整为5%)
# 100万 < 所得额 ≤ 300万   : 减按25%计入 → 实际税率 5%  (统一为5%)
# 所得额 > 300万            : 正常税率 25%

# 实际执行（最新政策 2023年第6号公告）:
# 小型微利企业，年应纳税所得额不超过300万元的部分，
#   减按25%计入应纳税所得额，按20%税率缴纳 → 实际税率 5%
# 超过300万元的部分按25%全额征税

# 悬崖效应：299.99万 → ~15万税; 300.01万 → ~75万税
# 多了200元利润，多了60万税！


@dataclass
class TaxScenario:
    """一个税务场景"""
    name: str
    description: str
    revenue_adjust: float = 0.0   # 收入调整（正=增加/提前确认，负=减少/递延）
    expense_adjust: float = 0.0   # 费用调整（正=增加/加速扣除，负=减少）
    annual_profit: float = 0.0
    estimated_cit: float = 0.0
    tax_saved_vs_default: float = 0.0
    feasibility: str = "feasible"  # feasible / conditional / not_recommended
    legal_basis: str = ""
    risk_level: str = "low"  # low / medium / high


@dataclass
class OptimizationResult:
    """优化结果"""
    client_id: str
    client_name: str
    period: str
    current_annual_profit: float
    current_estimated_cit: float
    threshold_proximity: dict  # 距各阈值的距离
    scenarios: list[TaxScenario]
    recommendation: str
    potential_savings: float
    algorithm_version: str = "2.0-cliff-detection"


def run_tax_optimization(db: Session, client_id: str, period: str = None) -> dict:
    """
    税务优化主入口

    算法流程:
      1. 统计 YTD 利润 + 预测全年
      2. 检测利润是否接近税率跳档阈值
      3. 搜索最优调整方案（场景树剪枝）
      4. 输出具体可执行建议 + 法规依据
    """
    from app.models.client import Client
    from app.services.report_service import get_confirmed_entries, _sum_by_account, _month_range

    today = dt_date.today()
    if period:
        y, m = map(int, period.split("-"))
    else:
        y, m = today.year, today.month

    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        return {"error": "客户不存在"}

    # ============================================================
    # Step 1: 统计 YTD 数据
    # ============================================================
    year_start = dt_date(y, 1, 1)
    year_end = dt_date(y, 12, 31)

    entries = get_confirmed_entries(db, str(year_start), str(year_end))
    entries = [e for e in entries if e.get("client_id") == client_id]

    ytd_revenue = _sum_by_account(entries, ["6001", "6051"], "credit")
    ytd_cost = _sum_by_account(entries, ["6401", "6402", "6403"], "debit")
    ytd_expenses = (
        ytd_cost
        + _sum_by_account(entries, ["6601"], "debit")
        + _sum_by_account(entries, ["6602"], "debit")
        + _sum_by_account(entries, ["6603"], "debit")
    )
    ytd_profit = ytd_revenue - ytd_expenses

    # ============================================================
    # Step 2: 预测全年利润（简单线性外推 + 季节性修正）
    # ============================================================
    months_elapsed = m  # 已过去月份数
    months_remaining = 12 - m

    # 历史月度均值
    monthly_avg_revenue = ytd_revenue / max(months_elapsed, 1)
    monthly_avg_expenses = ytd_expenses / max(months_elapsed, 1)

    # 季节性因子（基于历史数据）
    seasonal_factor = _compute_seasonal_factor(db, client_id, y, m)

    # 预测全年
    forecast_remaining_revenue = monthly_avg_revenue * months_remaining * seasonal_factor.get("revenue", 1.0)
    forecast_remaining_expenses = monthly_avg_expenses * months_remaining * seasonal_factor.get("expense", 1.0)

    forecast_annual_profit = ytd_profit + forecast_remaining_revenue - forecast_remaining_expenses

    # ============================================================
    # Step 3: 检测阈值临近度 + 场景搜索
    # ============================================================
    thresholds = _cit_thresholds()
    proximity = _check_threshold_proximity(forecast_annual_profit, thresholds)
    scenarios = _search_scenarios(forecast_annual_profit, ytd_profit, monthly_avg_revenue, monthly_avg_expenses, thresholds, client)

    # ============================================================
    # Step 4: 推荐
    # ============================================================
    default_cit = _calc_cit(forecast_annual_profit, thresholds)

    best_scenario = None
    max_savings = 0
    for s in scenarios:
        if s.tax_saved_vs_default > max_savings and s.feasibility != "not_recommended":
            max_savings = s.tax_saved_vs_default
            best_scenario = s

    recommendation = ""
    if best_scenario and best_scenario.tax_saved_vs_default > 100:
        recommendation = best_scenario.description
    elif proximity.get("warning"):
        recommendation = proximity["warning"]
    else:
        recommendation = "当前利润水平远离税率跳档阈值，无需特别操作。继续保持规范的财税管理。"

    # ============================================================
    # 增值税优化
    # ============================================================
    vat_optimization = _vat_optimization(db, client_id, y, m)

    return {
        "client_id": client_id,
        "client_name": client.name,
        "period": f"{y}-{m:02d}",
        "ytd_data": {
            "revenue": round(ytd_revenue, 2),
            "expenses": round(ytd_expenses, 2),
            "profit": round(ytd_profit, 2),
            "months_elapsed": months_elapsed,
        },
        "forecast": {
            "annual_profit": round(forecast_annual_profit, 2),
            "annual_revenue": round(monthly_avg_revenue * 12, 2),
            "annual_expenses": round(monthly_avg_expenses * 12, 2),
            "confidence": "medium" if months_elapsed >= 6 else "low",
        },
        "current_cit_estimate": default_cit,
        "threshold_proximity": proximity,
        "scenarios": [
            {
                "name": s.name,
                "description": s.description,
                "revenue_adjust": s.revenue_adjust,
                "expense_adjust": s.expense_adjust,
                "annual_profit_after": round(s.annual_profit, 2),
                "estimated_cit_after": round(s.estimated_cit, 2),
                "tax_saved": round(s.tax_saved_vs_default, 2),
                "feasibility": s.feasibility,
                "legal_basis": s.legal_basis,
                "risk_level": s.risk_level,
            }
            for s in scenarios[:5]
        ],
        "recommendation": recommendation,
        "potential_savings": round(max_savings, 2),
        "vat_optimization": vat_optimization,
    }


def _cit_thresholds() -> list[dict]:
    """CIT 税率跳档阈值"""
    return [
        {
            "name": "小微企业优惠上限",
            "value": 3_000_000,
            "below_rate": 0.05,
            "above_rate": 0.25,
            "cliff_cost": 600_000,  # 刚好超过300万，多交60万
            "description": "年应纳税所得额 ≤ 300万 → 5%; > 300万 → 全额25%",
        },
        {
            "name": "小微企业标准档",
            "value": 1_000_000,
            "below_rate": 0.05,
            "above_rate": 0.05,
            "cliff_cost": 0,
            "description": "≤ 100万 和 100-300万 税率统一为5%",
        },
    ]


def _calc_cit(profit: float, thresholds: list[dict]) -> float:
    """计算企业所得税（小微企业优惠）"""
    if profit <= 0:
        return 0
    if profit <= 3_000_000:
        return round(profit * 0.05, 2)
    else:
        return round(profit * 0.25, 2)


def _check_threshold_proximity(profit: float, thresholds: list[dict]) -> dict:
    """检测利润离各跳档阈值有多近"""
    result = {"distance_to_thresholds": [], "warning": ""}

    for t in thresholds:
        distance = t["value"] - profit
        result["distance_to_thresholds"].append({
            "threshold": t["name"],
            "value": t["value"],
            "distance": round(distance, 2),
            "direction": "below" if distance > 0 else "above",
            "cliff_cost": t["cliff_cost"] if distance < 0 and abs(distance) < 50000 else 0,
        })

    # 检查是否在悬崖区
    cliff_threshold = next((t for t in thresholds if t["cliff_cost"] > 0), None)
    if cliff_threshold:
        distance = profit - cliff_threshold["value"]
        if 0 < distance < 200000:
            result["warning"] = (
                f"⚠ 利润 ¥{profit:,.0f} 超过小微企业优惠上限(¥{cliff_threshold['value']:,.0f}) "
                f"{distance:,.0f} 元，导致全额按25%征税。"
                f"建议通过合法方式将利润降至 ¥{cliff_threshold['value']:,.0f} 以下，可节省 ~¥{cliff_threshold['cliff_cost']:,.0f} 税费。"
            )
            result["cliff_zone"] = True
        elif -100000 < distance <= 0:
            result["warning"] = (
                f"利润 ¥{profit:,.0f} 接近优惠上限(¥{cliff_threshold['value']:,.0f})，"
                f"差 {abs(distance):,.0f} 元。注意控制剩余月份的利润，避免超线。"
            )
            result["cliff_zone"] = True
        else:
            result["cliff_zone"] = False

    return result


def _search_scenarios(
    forecast_profit: float,
    ytd_profit: float,
    monthly_revenue: float,
    monthly_expenses: float,
    thresholds: list[dict],
    client,
) -> list[TaxScenario]:
    """场景树搜索 — 枚举可行的利润调整方案"""

    scenarios = []
    cliff = thresholds[0]  # 300万阈值

    # 场景 1: 默认（不做调整）
    default_cit = _calc_cit(forecast_profit, thresholds)
    scenarios.append(TaxScenario(
        name="默认路径",
        description="维持当前经营节奏，不进行特别调整",
        annual_profit=forecast_profit,
        estimated_cit=default_cit,
        tax_saved_vs_default=0,
        feasibility="feasible",
        legal_basis="无需额外操作",
    ))

    # 场景 2: 加速费用扣除（年末采购/预付）
    # 将下年度部分合理费用提前到本年扣除
    adv_expense = min(monthly_expenses * 0.5, max(0, forecast_profit - cliff["value"] + 50000))
    if adv_expense > 1000:
        adjusted_profit = forecast_profit - adv_expense
        adj_cit = _calc_cit(adjusted_profit, thresholds)
        savings = default_cit - adj_cit
        scenarios.append(TaxScenario(
            name="加速费用扣除",
            description=f"通过年末合理采购/预付款项，增加本年费用约 ¥{adv_expense:,.0f}，将利润从 ¥{forecast_profit:,.0f} 降至 ¥{adjusted_profit:,.0f}",
            expense_adjust=adv_expense,
            annual_profit=adjusted_profit,
            estimated_cit=adj_cit,
            tax_saved_vs_default=savings,
            feasibility="feasible" if adv_expense < monthly_expenses * 2 else "conditional",
            legal_basis="《企业所得税法》第八条: 企业实际发生的与取得收入有关的合理支出准予扣除",
            risk_level="low",
        ))

    # 场景 3: 递延收入确认
    # 部分收入推迟到下年度确认
    defer_revenue = min(monthly_revenue * 0.3, max(0, forecast_profit - cliff["value"] + 30000))
    if defer_revenue > 1000:
        adjusted_profit = forecast_profit - defer_revenue
        adj_cit = _calc_cit(adjusted_profit, thresholds)
        savings = default_cit - adj_cit
        scenarios.append(TaxScenario(
            name="收入递延确认",
            description=f"将约 ¥{defer_revenue:,.0f} 收入推迟至下年度确认（如年末发货但协商次年开票），利润从 ¥{forecast_profit:,.0f} 降至 ¥{adjusted_profit:,.0f}",
            revenue_adjust=-defer_revenue,
            annual_profit=adjusted_profit,
            estimated_cit=adj_cit,
            tax_saved_vs_default=savings,
            feasibility="conditional",
            legal_basis="《企业会计准则第14号——收入》: 收入确认需满足控制权转移条件。可合理调整合同条款中的验收/交付时点。",
            risk_level="medium",
        ))

    # 场景 4: 组合策略（加速费用 + 递延收入）
    combined_rev = min(monthly_revenue * 0.2, max(0, forecast_profit - cliff["value"] + 40000))
    combined_exp = min(monthly_expenses * 0.4, max(0, forecast_profit - cliff["value"] - combined_rev + 30000))
    if combined_rev + combined_exp > 2000:
        adj = forecast_profit - combined_rev - combined_exp
        adj_cit = _calc_cit(adj, thresholds)
        savings = default_cit - adj_cit
        scenarios.append(TaxScenario(
            name="组合优化策略",
            description=f"递延收入 ¥{combined_rev:,.0f} + 加速费用 ¥{combined_exp:,.0f}，利润从 ¥{forecast_profit:,.0f} 降至 ¥{adj:,.0f}",
            revenue_adjust=-combined_rev,
            expense_adjust=combined_exp,
            annual_profit=adj,
            estimated_cit=adj_cit,
            tax_saved_vs_default=savings,
            feasibility="conditional",
            legal_basis="结合上述两条法规，在准则允许范围内综合调整。建议与会计师确认具体执行方案。",
            risk_level="medium",
        ))

    # 场景 5: 固定资产加速折旧
    cap = monthly_revenue * 1.5
    if cap > 5000:
        dep_adj = min(cap, max(0, forecast_profit - cliff["value"] + 60000))
        if dep_adj > 2000:
            adj = forecast_profit - dep_adj
            adj_cit = _calc_cit(adj, thresholds)
            savings = default_cit - adj_cit
            scenarios.append(TaxScenario(
                name="固定资产加速折旧",
                description=f"对符合条件的设备/器具采用一次性税前扣除，增加折旧费用 ¥{dep_adj:,.0f}",
                expense_adjust=dep_adj,
                annual_profit=adj,
                estimated_cit=adj_cit,
                tax_saved_vs_default=savings,
                feasibility="conditional",
                legal_basis="《关于设备、器具扣除有关企业所得税政策的公告》(2023年第37号): 新购≤500万的设备器具可一次性扣除",
                risk_level="low",
            ))

    # 按节税金额从大到小排序
    scenarios.sort(key=lambda s: s.tax_saved_vs_default, reverse=True)
    return scenarios


def _compute_seasonal_factor(db: Session, client_id: str, year: int, current_month: int) -> dict:
    """计算季节性因子 — 基于历史数据"""
    from app.services.report_service import get_confirmed_entries, _sum_by_account, _month_range
    factors = {"revenue": 1.0, "expense": 1.0}

    # 检查过去两年同期的数据
    for check_year in [year - 1, year - 2]:
        year_total_revenue = 0
        remainder_revenue = 0
        year_total_expenses = 0
        remainder_expenses = 0

        for mth in range(1, 13):
            ms, me = _month_range(check_year, mth)
            month_entries = get_confirmed_entries(db, str(ms), str(me))
            month_entries = [e for e in month_entries if e.get("client_id") == client_id]
            m_rev = _sum_by_account(month_entries, ["6001", "6051"], "credit")
            m_exp = _sum_by_account(month_entries, ["6401", "6402", "6403", "6601", "6602", "6603"], "debit")

            if mth > current_month:
                remainder_revenue += m_rev
                remainder_expenses += m_exp
            year_total_revenue += m_rev
            year_total_expenses += m_exp

        if year_total_revenue > 0:
            months_left = 12 - current_month
            if months_left > 0:
                expected_ratio = months_left / 12
                actual_ratio = remainder_revenue / year_total_revenue
                factors["revenue"] = max(0.5, min(2.0, actual_ratio / max(expected_ratio, 0.01)))
            if year_total_expenses > 0:
                actual_exp_ratio = remainder_expenses / year_total_expenses
                factors["expense"] = max(0.5, min(2.0, actual_exp_ratio / max(expected_ratio, 0.01)))
        if factors["revenue"] != 1.0:
            break

    return factors


def _vat_optimization(db: Session, client_id: str, year: int, month: int) -> dict:
    """增值税优化分析"""
    from app.services.report_service import get_confirmed_entries, _sum_by_account, _month_range
    from app.models.document import OriginalDocument

    ms, me = _month_range(year, month)
    entries = get_confirmed_entries(db, str(ms), str(me))
    entries = [e for e in entries if e.get("client_id") == client_id]

    input_vat = _sum_by_account(entries, ["2221002"], "debit")
    output_vat = _sum_by_account(entries, ["2221001"], "credit")
    net_vat = round(max(output_vat - input_vat, 0), 2)

    # 检查是否有未认证的进项票
    unprocessed_docs = db.query(OriginalDocument).filter(
        OriginalDocument.client_id == client_id,
        OriginalDocument.ocr_status == "done",
        OriginalDocument.doc_type == "invoice",
    ).count()

    recommendations = []
    if input_vat < output_vat * 0.5:
        recommendations.append("进项税额偏低，检查是否有未取得增值税专用发票的采购，建议优先向一般纳税人供应商采购")
    if input_vat > output_vat * 3:
        recommendations.append("进项税额远大于销项，如为留抵税额，可申请留抵退税(符合条件的企业)")

    return {
        "output_vat": round(output_vat, 2),
        "input_vat": round(input_vat, 2),
        "net_vat_payable": net_vat,
        "input_ratio": round(input_vat / max(output_vat, 1) * 100, 1),
        "unprocessed_invoices": unprocessed_docs,
        "recommendations": recommendations,
    }
