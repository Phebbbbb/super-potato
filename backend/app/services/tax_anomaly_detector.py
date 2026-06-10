"""
税务异常检测引擎 — Benford's Law + Z-Score + 财务指标异常检测

借鉴:
- findata-guard: Benford定律检测造假数据
- Finomaly: Isolation Forest 无监督异常检测
- 自研: 税务特定风险规则引擎
"""
import json
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AnomalyResult:
    """异常检测结果"""
    has_anomaly: bool = False
    risk_level: str = "low"  # low / medium / high / critical
    risk_score: float = 0.0  # 0-100
    findings: list[dict] = field(default_factory=list)
    recommendation: str = ""


# ===== Benford's Law =====
BENFORD_DIST = {
    1: 0.301, 2: 0.176, 3: 0.125, 4: 0.097,
    5: 0.079, 6: 0.067, 7: 0.058, 8: 0.051, 9: 0.046,
}
BENFORD_CHI2_CRITICAL = {0.01: 20.09, 0.05: 15.51, 0.10: 13.36}


def _first_digit(n: float) -> int:
    if n == 0:
        return 0
    n = abs(n)
    while n >= 10:
        n /= 10
    while n < 1:
        n *= 10
    return int(n)


def check_benford(amounts: list[float], min_samples: int = 30) -> dict:
    if len(amounts) < min_samples:
        return {"is_suspicious": False, "reason": "样本量不足", "min_required": min_samples}

    digits = [_first_digit(a) for a in amounts if a != 0]
    if len(digits) < min_samples:
        return {"is_suspicious": False, "reason": "有效数据不足"}

    total = len(digits)
    observed = Counter(digits)
    observed_dist = {d: observed.get(d, 0) / total for d in range(1, 10)}

    chi2 = 0.0
    deviations = {}
    for d in range(1, 10):
        expected = BENFORD_DIST[d] * total
        actual = observed.get(d, 0)
        diff = actual - expected
        if expected > 0:
            chi2 += (diff ** 2) / expected
        deviations[d] = {
            "expected_pct": round(BENFORD_DIST[d] * 100, 1),
            "actual_pct": round(observed_dist.get(d, 0) * 100, 1),
            "deviation": round(diff / max(expected, 1) * 100, 1),
        }

    is_suspicious = chi2 > BENFORD_CHI2_CRITICAL[0.05]

    return {
        "is_suspicious": is_suspicious,
        "chi2_statistic": round(chi2, 2),
        "significance": "p<0.05" if is_suspicious else "not significant",
        "observed_dist": observed_dist,
        "deviations": deviations,
        "sample_size": total,
    }


def check_zscore_outliers(amounts: list[float], threshold: float = 2.5) -> list[dict]:
    if len(amounts) < 4:
        return []

    n = len(amounts)
    mean = sum(amounts) / n
    variance = sum((x - mean) ** 2 for x in amounts) / n
    std = math.sqrt(variance) if variance > 0 else 1

    outliers = []
    for i, val in enumerate(amounts):
        if val == 0:
            continue
        z = abs(val - mean) / std if std > 0 else 0
        if z > threshold:
            outliers.append({
                "index": i,
                "value": round(val, 2),
                "z_score": round(z, 2),
                "mean": round(mean, 2),
                "severity": "high" if z > 3.5 else ("medium" if z > 3.0 else "low"),
            })
    return outliers


def check_tax_risk_rules(vouchers: list[dict]) -> list[dict]:
    findings = []
    if not vouchers:
        return findings

    amounts = [v.get("total_debit", v.get("amount", 0)) for v in vouchers]

    # 规则1: 整数金额
    round_count = sum(1 for a in amounts if a > 1000 and a % 10000 == 0)
    round_pct = round_count / max(len(amounts), 1) * 100
    if round_pct > 40:
        examples = [str(a) for a in amounts if a > 1000 and a % 10000 == 0][:5]
        findings.append({
            "rule": "round_number",
            "description": f"大额整数凭证占比 {round_pct:.0f}%（>{','.join(examples)}...），可能存在人为编造",
            "risk": "medium",
        })

    # 规则2: 重复金额
    amount_counter = Counter([round(a, 2) for a in amounts if a > 0])
    duplicates = {k: v for k, v in amount_counter.items() if v >= 3}
    if duplicates:
        dup_list = sorted(duplicates.items(), key=lambda x: x[1], reverse=True)[:5]
        dup_str = ", ".join([f"¥{k:,.2f}×{v}次" for k, v in dup_list])
        findings.append({
            "rule": "duplicate_amount",
            "description": f"重复金额: {dup_str}，可能为拆分入账或重复记账",
            "risk": "medium" if max(duplicates.values()) >= 5 else "low",
        })

    # 规则3: 月末集中入账
    if vouchers and "voucher_date" in vouchers[0]:
        from datetime import date
        month_end_count = 0
        quarter_end_count = 0
        for v in vouchers:
            d = v.get("voucher_date", "")
            if d:
                try:
                    dt = date.fromisoformat(d) if isinstance(d, str) else d
                    if dt.day >= 25:
                        month_end_count += 1
                    if dt.month in (3, 6, 9, 12) and dt.day >= 25:
                        quarter_end_count += 1
                except (ValueError, TypeError):
                    pass
        me_pct = month_end_count / max(len(vouchers), 1) * 100
        qe_pct = quarter_end_count / max(len(vouchers), 1) * 100
        if me_pct > 50:
            findings.append({
                "rule": "month_end_clustering",
                "description": f"月末集中入账占比 {me_pct:.0f}%，可能存在突击做账",
                "risk": "medium" if me_pct > 70 else "low",
            })
        if qe_pct > 25:
            findings.append({
                "rule": "quarter_end_clustering",
                "description": f"季末集中入账占比 {qe_pct:.0f}%，可能存在调节利润",
                "risk": "high" if qe_pct > 40 else "medium",
            })

    # 规则4: 借贷不平衡
    for v in vouchers:
        debit = v.get("total_debit", 0) or 0
        credit = v.get("total_credit", 0) or 0
        if debit > 0 and credit > 0 and abs(debit - credit) > 0.01:
            findings.append({
                "rule": "unbalanced_voucher",
                "description": f"凭证 {v.get('voucher_no', '未知')} 借贷不平衡 (借:{debit} 贷:{credit})",
                "risk": "critical",
            })

    return findings


def analyze_tax_risk(vouchers: list[dict], amounts: list[float] = None) -> AnomalyResult:
    if amounts is None:
        amounts = [v.get("total_debit", v.get("amount", 0)) for v in vouchers]

    result = AnomalyResult()
    risk_score = 0.0

    # 1. Benford
    benford = check_benford(amounts)
    if benford.get("is_suspicious"):
        result.findings.append({"type": "benford", "name": "Benford定律异常（数据可能非自然产生）", "detail": benford})
        risk_score += 25

    # 2. Z-Score
    outliers = check_zscore_outliers(amounts)
    if outliers:
        high_severity = [o for o in outliers if o["severity"] == "high"]
        result.findings.append({
            "type": "zscore_outliers",
            "name": f"Z-Score离群值检测到 {len(outliers)} 个异常金额",
            "detail": {"outliers": outliers[:10], "total": len(outliers)},
        })
        risk_score += len(high_severity) * 10 + (len(outliers) - len(high_severity)) * 3

    # 3. 税务规则
    rules = check_tax_risk_rules(vouchers)
    for rule in rules:
        result.findings.append({"type": "tax_rule", "name": rule["description"], "detail": rule})
        risk_map = {"low": 5, "medium": 15, "high": 25, "critical": 40}
        risk_score += risk_map.get(rule["risk"], 5)

    result.has_anomaly = len(result.findings) > 0
    result.risk_score = min(risk_score, 100)

    if result.risk_score >= 70:
        result.risk_level = "critical"
        result.recommendation = "存在严重税务风险，建议立即排查并咨询税务师"
    elif result.risk_score >= 40:
        result.risk_level = "high"
        result.recommendation = "存在多个税务风险点，建议复核相关凭证并与客户沟通"
    elif result.risk_score >= 15:
        result.risk_level = "medium"
        result.recommendation = "存在一些异常指标，建议关注并在后续记账中核实"
    else:
        result.risk_level = "low"
        result.recommendation = "数据整体正常，未发现明显异常"

    return result
