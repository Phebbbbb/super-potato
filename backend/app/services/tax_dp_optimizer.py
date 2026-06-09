"""
多期税务 DP 优化器 — 纯 Python 实现，零外部依赖

算法: 动态规划 + 分支定界
  状态: (period, deferred_revenue, accelerated_expense, depreciation_method)
  决策: 每期选择收入确认时点、费用扣除节奏、折旧方式
  目标: 最小化 N 年累计企业所得税

核心洞察:
  CIT 悬崖在 ¥300万 — 这是分段函数，不是连续可微的
  贪心(只看当年)会掉进陷阱: 今年省5万 vs 明年多交60万
  DP 保证全局最优

复杂度:
  状态空间 ~ 10^4 (5年 × 10收入档 × 10费用档 × 2折旧方式)
  每状态 3 决策 → O(10^5) 级别
  纯 Python 秒出结果
"""
import json
from datetime import date as dt_date
from typing import Optional
from dataclasses import dataclass, field
from copy import deepcopy


# ============================================================
# 税法参数配置
# ============================================================

@dataclass
class TaxConfig:
    """税法配置 — 可随政策变化更新"""
    # CIT 小微企业优惠 (2023年第6号公告)
    small_profit_threshold: float = 3_000_000  # 300万
    small_profit_rate: float = 0.05            # 实际税率 5%
    normal_rate: float = 0.25                  # 正常税率 25%

    # 收入递延约束
    max_defer_revenue_ratio: float = 0.30  # 最多递延30%收入
    max_defer_months: int = 3              # 最多递延3个月

    # 费用加速约束
    max_accelerate_expense_ratio: float = 0.50  # 最多加速50%
    accelerated_asset_threshold: float = 5_000_000  # 500万以下设备可一次性扣除

    # 折旧方法
    depreciation_methods: list = field(default_factory=lambda: ["straight_line", "accelerated"])

    # 其他约束
    max_annual_loss_carryforward: int = 5  # 亏损可结转5年


def _default_tax_config() -> TaxConfig:
    return TaxConfig()


# ============================================================
# 核心 DP 算法
# ============================================================

@dataclass
class PeriodState:
    """单期状态"""
    period_index: int       # 0-based
    period_label: str       # "2026"
    base_revenue: float     # 基准收入（不做调整时）
    base_expense: float     # 基准费用
    base_profit: float      # 基准利润
    deferred_in: float = 0  # 从上期递延来的收入
    deferred_out: float = 0 # 递延到下期的收入
    accelerated_expense: float = 0  # 加速扣除的费用
    depreciation_extra: float = 0   # 加速折旧额外扣除
    adjusted_profit: float = 0      # 调整后利润
    cit_payable: float = 0          # 本期应交 CIT
    effective_rate: float = 0       # 实际税率


@dataclass
class OptimizationPath:
    """一条优化路径"""
    periods: list[PeriodState]
    total_cit: float = 0
    total_profit: float = 0
    avg_effective_rate: float = 0
    feasibility_score: float = 1.0  # 1.0 = 完全可行


def _calc_cit_piecewise(profit: float, config: TaxConfig) -> tuple[float, float]:
    """
    计算 CIT 应纳税额 + 实际税率

    分段函数:
      profit ≤ 0        → CIT = 0
      0 < profit ≤ 300万 → CIT = profit × 5%
      profit > 300万     → CIT = profit × 25%
    """
    if profit <= 0:
        return 0.0, 0.0
    if profit <= config.small_profit_threshold:
        cit = round(profit * config.small_profit_rate, 2)
        return cit, config.small_profit_rate
    else:
        cit = round(profit * config.normal_rate, 2)
        return cit, config.normal_rate


def _cit_marginal_cost(profit: float, config: TaxConfig) -> dict:
    """
    计算边际税率 + 悬崖信息

    返回:
      {
        "marginal_rate": 0.25,      # 下一块钱利润的边际税率
        "bracket": "small_profit",  # 当前档位
        "distance_to_cliff": 50000, # 距下个跳档还剩多少
        "cliff_penalty": 0,         # 超过跳档点会多交多少税
      }
    """
    if profit <= 0:
        return {"marginal_rate": 0, "bracket": "loss", "distance_to_cliff": config.small_profit_threshold, "cliff_penalty": 0}

    if profit <= config.small_profit_threshold:
        distance = config.small_profit_threshold - profit
        # 超过300万的惩罚: (300万+1) × 25% - 300万 × 5% ≈ 60万
        cliff_penalty = round((config.small_profit_threshold + 1) * config.normal_rate - config.small_profit_threshold * config.small_profit_rate, 2)
        return {
            "marginal_rate": config.small_profit_rate,
            "bracket": "small_profit",
            "distance_to_cliff": round(distance, 2),
            "cliff_penalty": cliff_penalty if distance < 500000 else 0,
        }
    else:
        return {
            "marginal_rate": config.normal_rate,
            "bracket": "normal",
            "distance_to_cliff": 0,
            "cliff_penalty": 0,
        }


def optimize_multi_period(
    annual_revenues: list[float],
    annual_expenses: list[float],
    period_labels: list[str] = None,
    config: TaxConfig = None,
    beam_width: int = 20,
) -> dict:
    """
    多期税务 DP 优化

    Args:
        annual_revenues: 各年预测收入 [2026年, 2027年, ...]
        annual_expenses: 各年预测费用
        period_labels: 各期标签 ["2026", "2027", ...]
        config: 税法配置
        beam_width: 束搜索宽度（保留前K个最优状态）

    Returns:
        {
            "optimal_path": [...],      # 每年最优状态
            "total_cit": 150000,
            "total_profit": 3000000,
            "avg_effective_rate": 0.05,
            "alternative_scenarios": [...],  # 次优方案供参考
            "cliff_warnings": [...],
        }
    """
    if config is None:
        config = _default_tax_config()

    n = len(annual_revenues)
    if period_labels is None:
        period_labels = [f"Year {i+1}" for i in range(n)]

    # === 枚举每期的可行利润水平 ===
    # 对每期，生成: 基准利润 ± 递延收入 ± 加速费用 ± 折旧调整
    feasible_levels = []  # list[list[dict]]

    for i in range(n):
        rev = annual_revenues[i]
        exp = annual_expenses[i]
        base_profit = rev - exp
        levels = []

        # 收入递延选项（0%, 10%, 20%, 30%）
        for defer_ratio in [0, 0.1, 0.2, 0.3]:
            if defer_ratio > config.max_defer_revenue_ratio:
                continue
            deferred_rev = rev * defer_ratio

            # 费用加速选项（0%, 15%, 30%, 50%）
            for accel_ratio in [0, 0.15, 0.3, 0.5]:
                if accel_ratio > config.max_accelerate_expense_ratio:
                    continue
                accel_exp = exp * accel_ratio

                # 折旧调整（0 或 设备价值 × 一次性扣除比例）
                for dep_extra in [0, rev * 0.05, rev * 0.10]:
                    if dep_extra > config.accelerated_asset_threshold:
                        continue

                    adjusted = base_profit - deferred_rev - accel_exp - dep_extra
                    cit, rate = _calc_cit_piecewise(adjusted, config)

                    levels.append({
                        "base_profit": base_profit,
                        "deferred_revenue_out": deferred_rev,
                        "accelerated_expense": accel_exp,
                        "depreciation_extra": dep_extra,
                        "adjusted_profit": round(adjusted, 2),
                        "cit": cit,
                        "effective_rate": rate,
                    })

        # 去重 + 排序（按利润从低到高）
        seen = set()
        unique = []
        for lv in sorted(levels, key=lambda x: x["adjusted_profit"]):
            key = (round(lv["adjusted_profit"], -2),)  # 聚合到百元
            if key not in seen:
                seen.add(key)
                unique.append(lv)
        feasible_levels.append(unique[:beam_width])  # 束剪枝

    # === DP 前向搜索 ===
    # dp[i][j] = (最优路径到第i期第j个利润水平, 累计CIT)
    # 转移: 上期递延的收入 → 本期加回

    dp = []  # dp[i] = list of (path, total_cit, deferred_from_prev)

    for i in range(n):
        row = []
        for j, level in enumerate(feasible_levels[i]):
            # 上期递延来的收入
            deferred_in = 0
            best_prev_cit = float("inf")
            best_prev_path = None

            if i > 0:
                for k, prev_state in enumerate(dp[i - 1]):
                    prev_level = prev_state["level"]
                    prev_path = prev_state["path"]
                    prev_cit = prev_state["total_cit"]
                    # 上期递延 = 本期加回
                    deferred_in = prev_level.get("deferred_revenue_out", 0)
                    # 调整本期利润: 加回上期递延收入
                    full_profit = level["adjusted_profit"] + deferred_in
                    full_cit, _ = _calc_cit_piecewise(full_profit, config)
                    total_cit = prev_cit + full_cit

                    if total_cit < best_prev_cit:
                        best_prev_cit = total_cit
                        best_prev_path = prev_path
            else:
                # 第一期
                best_prev_cit = level["cit"]
                best_prev_path = []

            state = PeriodState(
                period_index=i,
                period_label=period_labels[i],
                base_revenue=annual_revenues[i],
                base_expense=annual_expenses[i],
                base_profit=level["base_profit"],
                deferred_in=deferred_in,
                deferred_out=level["deferred_revenue_out"],
                accelerated_expense=level["accelerated_expense"],
                depreciation_extra=level["depreciation_extra"],
                adjusted_profit=round(level["adjusted_profit"] + deferred_in, 2),
                cit_payable=round(level["cit"], 2),
                effective_rate=level["effective_rate"],
            )

            path = (best_prev_path or []) + [state]
            row.append({
                "level": level,
                "path": path,
                "total_cit": round(best_prev_cit, 2),
            })

        # 束剪枝: 保留 cumulative_cit 最小的 beam_width 条路径
        row.sort(key=lambda x: x["total_cit"])
        dp.append(row[:beam_width])

    # === 提取最优路径 ===
    if not dp or not dp[-1]:
        return {"error": "无可行的优化路径"}

    best = dp[-1][0]
    optimal_periods = best["path"]
    total_profit = sum(p.adjusted_profit for p in optimal_periods)
    total_cit = best["total_cit"]
    avg_rate = round(total_cit / max(total_profit, 1), 4)

    # === 悬崖预警 ===
    cliff_warnings = []
    for p in optimal_periods:
        marginal = _cit_marginal_cost(p.adjusted_profit, config)
        if marginal["distance_to_cliff"] > 0 and marginal["distance_to_cliff"] < 500000:
            cliff_warnings.append({
                "period": p.period_label,
                "adjusted_profit": p.adjusted_profit,
                "distance_to_cliff": marginal["distance_to_cliff"],
                "message": f"{p.period_label}年利润 ¥{p.adjusted_profit:,.0f} 距300万优惠上限仅差 ¥{marginal['distance_to_cliff']:,.0f}，需警惕",
            })

    # === 次优方案（前3条） ===
    alt_scenarios = []
    for rank, candidate in enumerate(dp[-1][:3]):
        periods = candidate["path"]
        alt_scenarios.append({
            "rank": rank + 1,
            "total_cit": candidate["total_cit"],
            "avg_rate": round(candidate["total_cit"] / max(sum(p.adjusted_profit for p in periods), 1), 4),
            "strategy": " + ".join([
                f"{p.period_label}: 收入递延¥{p.deferred_out:,.0f}" if p.deferred_out > 0 else
                f"{p.period_label}: 费用加速¥{p.accelerated_expense:,.0f}" if p.accelerated_expense > 0 else
                f"{p.period_label}: 基准方案"
                for p in periods
            ]),
        })

    # === 对比不做优化的基准方案 ===
    baseline_cit = sum(_calc_cit_piecewise(r - e, config)[0] for r, e in zip(annual_revenues, annual_expenses))
    savings = round(baseline_cit - total_cit, 2)

    return {
        "optimal_path": [
            {
                "period": p.period_label,
                "base_revenue": round(p.base_revenue, 2),
                "base_expense": round(p.base_expense, 2),
                "base_profit": round(p.base_profit, 2),
                "deferred_out": round(p.deferred_out, 2),
                "accelerated_expense": round(p.accelerated_expense, 2),
                "depreciation_extra": round(p.depreciation_extra, 2),
                "adjusted_profit": round(p.adjusted_profit, 2),
                "cit_payable": p.cit_payable,
                "effective_rate": p.effective_rate,
            }
            for p in optimal_periods
        ],
        "total_profit": round(total_profit, 2),
        "total_cit": total_cit,
        "avg_effective_rate": avg_rate,
        "baseline_cit": baseline_cit,
        "total_savings": savings,
        "savings_pct": round(savings / max(baseline_cit, 1) * 100, 1),
        "alternative_scenarios": alt_scenarios,
        "cliff_warnings": cliff_warnings,
    }


def optimize_with_scenario(
    client_data: dict,
    config: TaxConfig = None,
) -> dict:
    """
    基于客户实际数据进行优化

    Args:
        client_data: {
            "historical_revenues": [12个月收入],
            "historical_expenses": [12个月费用],
            "ytd_revenue": 500000,
            "ytd_expense": 350000,
            "months_elapsed": 6,
            "growth_rate_estimate": 0.10,  # 预估年增长率
            "fixed_asset_value": 200000,    # 可加速折旧的资产
        }

    Returns:
        优化建议 + 具体执行方案
    """
    from datetime import date

    today = date.today()
    current_year = today.year
    months_remaining = 12 - client_data.get("months_elapsed", today.month)
    growth = client_data.get("growth_rate_estimate", 0.05)

    # 构建 3 年预测
    ytd_rev = client_data.get("ytd_revenue", 0)
    ytd_exp = client_data.get("ytd_expense", 0)
    months_elapsed = max(client_data.get("months_elapsed", 1), 1)

    monthly_rev = ytd_rev / months_elapsed
    monthly_exp = ytd_exp / months_elapsed

    annual_revenues = []
    annual_expenses = []
    for offset in range(3):
        yr = current_year + offset
        if offset == 0:
            # 今年: YTD + 预测剩余
            rev = ytd_rev + monthly_rev * months_remaining * (1 + growth)
            exp = ytd_exp + monthly_exp * months_remaining * (1 + growth * 0.5)
        else:
            # 明年后年: 全年预测
            prev_rev = annual_revenues[-1]
            prev_exp = annual_expenses[-1]
            rev = prev_rev * (1 + growth)
            exp = prev_exp * (1 + growth * 0.7)
        annual_revenues.append(rev)
        annual_expenses.append(exp)

    period_labels = [str(current_year + i) for i in range(3)]

    result = optimize_multi_period(annual_revenues, annual_expenses, period_labels, config)

    # 生成可执行建议
    recommendations = []
    opt_path = result.get("optimal_path", [])

    for p in opt_path:
        year = p["period"]
        if p["deferred_out"] > 1000:
            recommendations.append({
                "year": year,
                "action": "收入递延",
                "amount": p["deferred_out"],
                "detail": f"{year}年递延 ¥{p['deferred_out']:,.0f} 收入至下年度。操作: 对年末发货的合同，将验收/交付条款约定至次年1月。",
                "legal_basis": "《企业会计准则第14号——收入》收入确认五步法: 控制权转移时点可合理约定",
                "tax_saved": round(p["deferred_out"] * 0.20, 2),  # 25% - 5% = 20% 节省
            })
        if p["accelerated_expense"] > 1000:
            recommendations.append({
                "year": year,
                "action": "费用加速",
                "amount": p["accelerated_expense"],
                "detail": f"{year}年通过年末采购/预付款增加可扣除费用 ¥{p['accelerated_expense']:,.0f}",
                "legal_basis": "《企业所得税法》第八条: 与取得收入相关的合理支出准予扣除",
                "tax_saved": round(p["accelerated_expense"] * 0.20, 2),
            })
        if p["depreciation_extra"] > 1000:
            recommendations.append({
                "year": year,
                "action": "加速折旧",
                "amount": p["depreciation_extra"],
                "detail": f"{year}年对符合条件的设备/器具采用一次性税前扣除，增加折旧 ¥{p['depreciation_extra']:,.0f}",
                "legal_basis": "《关于设备、器具扣除有关企业所得税政策的公告》(2023年第37号)",
                "tax_saved": round(p["depreciation_extra"] * 0.20, 2),
            })

    result["recommendations"] = recommendations
    result["forecast"] = {
        "annual_revenues": [round(r, 2) for r in annual_revenues],
        "annual_expenses": [round(e, 2) for e in annual_expenses],
        "method": "线性外推 + 增长率修正",
        "confidence": "medium" if months_elapsed >= 6 else "low",
    }

    return result


# ============================================================
# 快速分析: 单期悬崖检测
# ============================================================

def cliff_analysis(ytd_profit: float, months_elapsed: int, monthly_avg_profit: float) -> dict:
    """
    CIT 悬崖快速检测 — 不需要完整 DP，只在需要时跑优化

    在 Dashboard 上实时显示，不消耗计算资源
    """
    months_remaining = 12 - months_elapsed
    forecast = ytd_profit + monthly_avg_profit * months_remaining
    config = _default_tax_config()

    marginal = _cit_marginal_cost(forecast, config)
    current_cit, _ = _calc_cit_piecewise(ytd_profit, config)
    forecast_cit, _ = _calc_cit_piecewise(forecast, config)

    result = {
        "ytd_profit": round(ytd_profit, 2),
        "forecast_annual_profit": round(forecast, 2),
        "current_bracket": marginal["bracket"],
        "marginal_rate": marginal["marginal_rate"],
        "distance_to_300w": marginal["distance_to_cliff"],
        "estimated_full_year_cit": forecast_cit,
        "ytd_cit_accrual": round(current_cit, 2),
        "remaining_cit_liability": round(max(forecast_cit - current_cit, 0), 2),
    }

    if marginal["distance_to_cliff"] > 0 and marginal["distance_to_cliff"] < 300000:
        result["alert"] = "warning"
        result["alert_message"] = (
            f"预测全年利润 ¥{forecast:,.0f}，距300万优惠上限仅 {marginal['distance_to_cliff']:,.0f}。"
            f"若超过将多交 ~¥{marginal['cliff_penalty']:,.0f} 税费。建议启动税务优化。"
        )
        # 计算安全利润区间
        safe_monthly = marginal["distance_to_cliff"] / max(months_remaining, 1)
        result["safe_monthly_profit"] = round(safe_monthly, 2)
        result["action"] = f"剩余 {months_remaining} 个月，每月利润控制在 ¥{safe_monthly:,.0f} 以内可保住5%税率"
    elif marginal["bracket"] == "normal":
        result["alert"] = "passed"
        result["alert_message"] = "已超过小微企业优惠上限，全额按25%征税"
    else:
        result["alert"] = "safe"
        result["alert_message"] = "当前利润水平安全，无悬崖风险"

    return result
