"""
多期税务 DP 优化器 — 纯 Python 实现，零外部依赖

算法矩阵:
  1. 束搜索 DP      — 快速近似解，适合交互式使用
  2. 分支定界 B&B    — 带 LP 松弛下界的精确搜索
  3. LP 松弛界       — CIT 分段凸函数的凸包给出最优下界

核心洞察:
  CIT 悬崖在 ¥300万 — 分段函数非连续可微
  贪心(只看当年)会掉进陷阱: 今年省5万 vs 明年多交60万
  B&B 保证全局最优（在离散化精度内）

LP 松弛原理:
  CIT(p) = 0 (p≤0) | 0.05p (0<p≤300万) | 0.25p (p>300万)
  凸包 = 0 (p≤0) | 0.05p (0<p≤300万) | 0.25p-60万 (p>300万)
  凸包 ≤ 原函数 → 给出有效下界 → 剪枝

复杂度:
  束搜索: O(P × B²) 其中 B=beam_width, P=期数
  B&B:    最坏 O(4^P × 3^P) 但剪枝后 ~10³~10⁴ 节点
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
        # 最后一期不允许递延（无下期可承接）
        defer_ratios = [0] if i == n - 1 else [0, 0.1, 0.2, 0.3]
        for defer_ratio in defer_ratios:
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
            key = round(lv["adjusted_profit"], -1)  # 聚合到十元（避免50元差异被误去重）
            if key not in seen:
                seen.add(key)
                unique.append(lv)
        feasible_levels.append(unique[:beam_width])  # 束剪枝

    # === DP 前向搜索 ===
    # dp[i][j] = {level, path, total_cit, cum_dep}
    # 转移规则:
    #   deferred_revenue: 上期递延 → 本期加回 (timing, 净额为零)
    #   accelerated_expense: 上期加速 → 本期加回 (timing, 净额为零)
    #   depreciation_extra: 累计不超过 config 上限 (终身一次性)
    max_cum_dep = min(
        config.accelerated_asset_threshold,
        sum(annual_revenues) * 0.15,  # 总收入的15%上限
    )

    dp = []

    for i in range(n):
        row = []
        for j, level in enumerate(feasible_levels[i]):
            best_prev_cit = float("inf")
            best_prev_path = None
            best_deferred_in = 0
            best_accel_recapture = 0
            best_cum_dep = level["depreciation_extra"]

            if i > 0:
                for k, prev_state in enumerate(dp[i - 1]):
                    prev_level = prev_state["level"]
                    prev_path = prev_state["path"]
                    prev_cit = prev_state["total_cit"]
                    prev_cum_dep = prev_state.get("cum_dep", 0)

                    # 累计折旧超限 → 剪枝
                    cum_dep = prev_cum_dep + level["depreciation_extra"]
                    if cum_dep > max_cum_dep + 0.01:
                        continue

                    # 上期递延收入 + 上期加速费用 → 本期加回
                    deferred_in = prev_level.get("deferred_revenue_out", 0)
                    accel_recapture = prev_level.get("accelerated_expense", 0)
                    full_profit = level["adjusted_profit"] + deferred_in + accel_recapture
                    full_cit, _ = _calc_cit_piecewise(full_profit, config)
                    total_cit = prev_cit + full_cit

                    if total_cit < best_prev_cit:
                        best_prev_cit = total_cit
                        best_prev_path = prev_path
                        best_deferred_in = deferred_in
                        best_accel_recapture = accel_recapture
                        best_cum_dep = cum_dep
            else:
                # 第一期: 无上期 reversal
                if level["depreciation_extra"] <= max_cum_dep + 0.01:
                    best_prev_cit = level["cit"]
                    best_prev_path = []

            if best_prev_cit == float("inf"):
                continue  # 所有转移被剪枝

            full_adjusted = level["adjusted_profit"] + best_deferred_in + best_accel_recapture
            full_cit, full_rate = _calc_cit_piecewise(full_adjusted, config)

            state = PeriodState(
                period_index=i,
                period_label=period_labels[i],
                base_revenue=annual_revenues[i],
                base_expense=annual_expenses[i],
                base_profit=level["base_profit"],
                deferred_in=best_deferred_in,
                deferred_out=level["deferred_revenue_out"],
                accelerated_expense=level["accelerated_expense"],
                depreciation_extra=level["depreciation_extra"],
                adjusted_profit=round(full_adjusted, 2),
                cit_payable=round(full_cit, 2),
                effective_rate=full_rate,
            )

            path = (best_prev_path or []) + [state]
            row.append({
                "level": level,
                "path": path,
                "total_cit": round(best_prev_cit, 2),
                "cum_dep": best_cum_dep,
            })

        # 束剪枝: 保留 cumulative_cit 最小的 beam_width 条路径
        row.sort(key=lambda x: x["total_cit"])
        dp.append(row[:beam_width])

    # === 提取最优路径 ===
    if not dp or not dp[-1]:
        return {"error": "无可行的优化路径"}

    best = dp[-1][0]
    optimal_periods = best["path"]

    # 终端加回: 最后一期 accelerated_expense 在虚拟 n+1 年确认
    last_p = optimal_periods[-1] if optimal_periods else None
    tail_deferred = float(getattr(last_p, 'deferred_out', 0) or 0)
    tail_accel = float(getattr(last_p, 'accelerated_expense', 0) or 0)
    tail_profit = tail_deferred + tail_accel
    tail_cit, _ = _calc_cit_piecewise(tail_profit, config)

    total_profit = sum(p.adjusted_profit for p in optimal_periods) + tail_profit
    total_cit = best["total_cit"] + tail_cit
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
        last_ap = periods[-1] if periods else None
        tail_d = float(getattr(last_ap, 'deferred_out', 0) or 0)
        tail_a = float(getattr(last_ap, 'accelerated_expense', 0) or 0)
        tail_p = tail_d + tail_a
        tail_c, _ = _calc_cit_piecewise(tail_p, config)
        alt_periods_profit = sum(p.adjusted_profit for p in periods) + tail_p
        alt_cit = candidate["total_cit"] + tail_c
        alt_scenarios.append({
            "rank": rank + 1,
            "total_cit": alt_cit,
            "avg_rate": round(alt_cit / max(alt_periods_profit, 1), 4),
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


# ═══════════════════════════════════════════════════════════════
# Branch-and-Bound with LP Relaxation (精确优化)
# ═══════════════════════════════════════════════════════════════

def _convex_envelope_cit(profit: float, config: TaxConfig) -> float:
    """CIT 分段函数的凸包（凸函数等于自身，用于 LP 松弛下界）"""
    if profit <= 0:
        return 0.0
    if profit <= config.small_profit_threshold:
        return profit * config.small_profit_rate
    cit_at_threshold = config.small_profit_threshold * config.small_profit_rate
    return cit_at_threshold + (profit - config.small_profit_threshold) * config.normal_rate


def _lp_lower_bound(
    total_profit: float, n_periods: int,
    max_defer_ratio: float, config: TaxConfig,
    dep_deduction: float = 0.0,
) -> float:
    """
    LP 松弛下界 — 利润可连续分配到各期时的最小 CIT

    核心松弛: 利润可连续分配（不限离散档位）、递延可跨任意期
    最优策略（CIT 凸 → Jensen）: 均分总利润到 n 期
    若平均 > 300万: 枚举 K 期填满 300万(税率5%), 其余均分(税率25%)

    dep_deduction: 可永久扣除的折旧（不计入应税利润）
    """
    taxable = max(total_profit - dep_deduction, 0)
    if n_periods <= 0 or taxable <= 0:
        return 0.0
    avg_profit = taxable / n_periods
    if avg_profit <= 0:
        return 0.0

    threshold = config.small_profit_threshold
    if avg_profit <= threshold:
        per_cit, _ = _calc_cit_piecewise(avg_profit, config)
        return round(n_periods * per_cit, 2)

    max_k = min(n_periods, int(taxable / threshold)) if threshold > 0 else 0
    best = float("inf")
    for k in range(max_k + 1):
        remaining = taxable - k * threshold
        rem_periods = n_periods - k
        if rem_periods <= 0:
            if remaining <= 0.01:
                cit = k * threshold * config.small_profit_rate
                if cit < best:
                    best = cit
            continue
        rp = remaining / rem_periods
        if rp < 0:
            continue
        cit = k * threshold * config.small_profit_rate
        cit += rem_periods * _convex_envelope_cit(rp, config)
        if cit < best:
            best = cit
    return round(best, 2)


def optimize_branch_and_bound(
    annual_revenues: list[float],
    annual_expenses: list[float],
    period_labels: list[str] = None,
    config: TaxConfig = None,
    time_limit_ms: int = 5000,
) -> dict:
    """
    分支定界精确优化 — LP 松弛剪枝，保证全局最优（离散化精度内）

    B&B 树: 每层=一个纳税年度, 分支=可行利润档位
    下界 = LP 松弛, 上界 = 束搜索解, 剪枝 = 下界 ≥ 上界
    最优性保证: optimality_gap = (UB - LB) / UB × 100%
    """
    import time

    if config is None:
        config = _default_tax_config()

    n = len(annual_revenues)
    if period_labels is None:
        period_labels = [f"Year {i+1}" for i in range(n)]

    start_time = time.time()

    # ── 初始上界: 束搜索 ──
    beam_result = optimize_multi_period(
        annual_revenues, annual_expenses, period_labels, config,
        beam_width=min(30, 20 + n * 5),
    )
    if beam_result.get("error"):
        return beam_result
    best_upper_bound = beam_result["total_cit"]
    best_solution = beam_result["optimal_path"]
    total_profit_all = sum(r - e for r, e in zip(annual_revenues, annual_expenses))

    # ── B&B 折旧上限 ──
    max_cum_dep_bb = min(
        config.accelerated_asset_threshold,
        sum(annual_revenues) * 0.15,
    )

    # ── 构建每期可行档位 ──
    all_levels = []
    for i in range(n):
        rev = annual_revenues[i]
        exp = annual_expenses[i]
        base_profit = rev - exp
        levels = []
        # 最后一期不允许递延（无下期可承接）
        defer_ratios_bb = [0] if i == n - 1 else [0, 0.1, 0.2, 0.3]
        for defer_ratio in defer_ratios_bb:
            if defer_ratio > config.max_defer_revenue_ratio:
                continue
            deferred_rev = rev * defer_ratio
            for accel_ratio in [0, 0.15, 0.3, 0.5]:
                if accel_ratio > config.max_accelerate_expense_ratio:
                    continue
                accel_exp = exp * accel_ratio
                for dep_extra in [0, rev * 0.05, rev * 0.10]:
                    if dep_extra > config.accelerated_asset_threshold:
                        continue
                    adjusted = base_profit - deferred_rev - accel_exp - dep_extra
                    cit, rate = _calc_cit_piecewise(adjusted, config)
                    levels.append({
                        "adjusted_profit": round(adjusted, 2),
                        "deferred_revenue_out": deferred_rev,
                        "accelerated_expense": accel_exp,
                        "depreciation_extra": dep_extra,
                        "cit": cit,
                        "effective_rate": rate,
                    })
        seen = set()
        unique = []
        for lv in sorted(levels, key=lambda x: x["adjusted_profit"]):
            key = round(lv["adjusted_profit"], -1)
            if key not in seen:
                seen.add(key)
                unique.append(lv)
        all_levels.append(unique)

    # ── DFS B&B ──
    # 转移规则与 beam search 一致: deferred + accel_exp 在下期加回, dep 累计有上限
    nodes_explored = 0
    nodes_pruned = 0

    def bb_search(period_idx: int, cumulative_cit: float,
                  prev_deferred_out: float, prev_accel_exp: float,
                  cum_dep: float, path: list):
        nonlocal nodes_explored, nodes_pruned, best_upper_bound, best_solution

        nodes_explored += 1
        if time.time() - start_time > time_limit_ms / 1000:
            return

        if period_idx >= n:
            # 最后一期的 deferred + accel 在下年加回（但无下年 → 全部确认）
            final_profit = prev_deferred_out + prev_accel_exp
            final_cit = cumulative_cit + _calc_cit_piecewise(final_profit, config)[0]
            if final_cit < best_upper_bound - 0.01:
                best_upper_bound = final_cit
                best_solution = list(path)
            return

        # LP 下界计算: 剩余总利润的凸包下界
        # 折旧是永久扣除，从应税利润中减去剩余折旧额度
        remaining_base = sum(r - e for r, e in zip(annual_revenues[period_idx:], annual_expenses[period_idx:]))
        remaining_profit = remaining_base + prev_deferred_out + prev_accel_exp
        remaining_dep_cap = max(0, max_cum_dep_bb - cum_dep)
        remaining_periods = n - period_idx
        if remaining_periods > 0:
            lb_remaining = _lp_lower_bound(
                max(remaining_profit, 0), remaining_periods,
                config.max_defer_revenue_ratio, config,
                dep_deduction=remaining_dep_cap,
            )
        else:
            lb_remaining = 0

        lower_bound = cumulative_cit + lb_remaining
        if lower_bound >= best_upper_bound - 0.01:
            nodes_pruned += 1
            return

        for level in sorted(all_levels[period_idx], key=lambda l: l["cit"]):
            # 折旧累计上限检查
            new_cum_dep = cum_dep + level["depreciation_extra"]
            if new_cum_dep > max_cum_dep_bb + 0.01:
                continue

            # 本期加回: 上期递延收入 + 上期加速费用
            deferred_in = prev_deferred_out
            accel_recapture = prev_accel_exp
            full_profit = level["adjusted_profit"] + deferred_in + accel_recapture
            full_cit, full_rate = _calc_cit_piecewise(full_profit, config)

            path_entry = {
                "period": period_labels[period_idx],
                "adjusted_profit": round(full_profit, 2),
                "deferred_out": round(level["deferred_revenue_out"], 2),
                "accelerated_expense": round(level["accelerated_expense"], 2),
                "depreciation_extra": round(level["depreciation_extra"], 2),
                "cit_payable": round(full_cit, 2),
                "effective_rate": full_rate,
            }

            bb_search(
                period_idx + 1,
                cumulative_cit + full_cit,
                level["deferred_revenue_out"],
                level["accelerated_expense"],
                new_cum_dep,
                path + [path_entry],
            )

    bb_search(0, 0.0, 0.0, 0.0, 0.0, [])

    elapsed_ms = int((time.time() - start_time) * 1000)

    if not best_solution:
        return beam_result

    # 终端加回: 最后一期递延收入和加速费用在下年确认
    last = best_solution[-1] if best_solution else {}
    tail_deferred = float(last.get("deferred_out", 0) or 0)
    tail_accel = float(last.get("accelerated_expense", 0) or 0)
    tail_profit = tail_deferred + tail_accel
    tail_cit, _ = _calc_cit_piecewise(tail_profit, config)

    total_cit_bb = round(sum(p.get("cit_payable", 0) for p in best_solution) + tail_cit, 2)
    total_profit_bb = sum(p.get("adjusted_profit", 0) for p in best_solution) + tail_profit
    baseline_cit = sum(_calc_cit_piecewise(r - e, config)[0] for r, e in zip(annual_revenues, annual_expenses))
    savings = round(baseline_cit - total_cit_bb, 2)

    lp_bound = _lp_lower_bound(total_profit_all, n, config.max_defer_revenue_ratio, config,
                               dep_deduction=max_cum_dep_bb)
    optimality_gap = round((total_cit_bb - lp_bound) / total_cit_bb * 100, 2) if total_cit_bb > 0 else 0.0

    return {
        "algorithm": "branch_and_bound",
        "optimal_path": best_solution,
        "total_profit": round(total_profit_bb, 2),
        "total_cit": round(total_cit_bb, 2),
        "baseline_cit": baseline_cit,
        "total_savings": savings,
        "savings_pct": round(savings / max(baseline_cit, 1) * 100, 1),
        "optimality_gap_pct": optimality_gap,
        "optimality_guarantee": "provably_optimal" if optimality_gap < 0.1 else f"gap={optimality_gap}%",
        "lp_lower_bound": round(lp_bound, 2),
        "nodes_explored": nodes_explored,
        "nodes_pruned": nodes_pruned,
        "elapsed_ms": elapsed_ms,
        "beam_comparison": {
            "beam_total_cit": beam_result.get("total_cit", 0),
            "bb_vs_beam_savings": round(beam_result.get("total_cit", 0) - total_cit_bb, 2),
        },
    }
