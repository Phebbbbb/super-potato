"""
批量智能审账引擎 — 自定义审核规则 + 全客户批量扫描

代账场景核心：主管可一次性对所有客户账套执行多维度审计，
自动标记异常，生成审核报告。从"逐户逐张人工复核"变为"只看异常"。
"""
import json
from datetime import date as dt_date, timedelta
from sqlalchemy.orm import Session
from collections import defaultdict


# ================================================================
# 审计规则定义
# ================================================================

AUDIT_RULES = {
    "balance": {
        "name": "借贷平衡",
        "category": "凭证完整性",
        "severity": "blocker",
        "description": "检测本月已确认凭证是否存在借贷不平衡",
        "weight": 25,
    },
    "gap_number": {
        "name": "凭证断号",
        "category": "凭证完整性",
        "severity": "warning",
        "description": "检测本月凭证编号是否存在跳号/断号",
        "weight": 5,
    },
    "large_amount": {
        "name": "大额凭证",
        "category": "异常检测",
        "severity": "warning",
        "description": "单张凭证金额超过阈值（默认10万）",
        "weight": 10,
        "config": {"threshold": 100_000},
    },
    "duplicate": {
        "name": "重复凭证",
        "category": "异常检测",
        "severity": "warning",
        "description": "相同日期+相同金额+相同摘要的凭证",
        "weight": 15,
    },
    "unconfirmed": {
        "name": "未确认凭证",
        "category": "流程合规",
        "severity": "warning",
        "description": "本月存在未确认状态的凭证",
        "weight": 10,
    },
    "suspense_account": {
        "name": "挂账科目检查",
        "category": "科目异常",
        "severity": "warning",
        "description": "过渡性科目（其他应收/应付/待处理）期末余额异常",
        "weight": 10,
    },
    "negative_amount": {
        "name": "负数凭证",
        "category": "异常检测",
        "severity": "warning",
        "description": "检测到负数金额的凭证明细",
        "weight": 8,
    },
    "missing_summary": {
        "name": "摘要缺失",
        "category": "凭证完整性",
        "severity": "info",
        "description": "凭证或分录缺少摘要说明",
        "weight": 3,
    },
    "cross_period": {
        "name": "跨期凭证",
        "category": "期间准确",
        "severity": "warning",
        "description": "凭证日期不在所属期内",
        "weight": 5,
    },
    "unmatched_bank": {
        "name": "银行未匹配",
        "category": "银企对账",
        "severity": "warning",
        "description": "银行流水存在未匹配行",
        "weight": 10,
    },
    "revenue_expense_mismatch": {
        "name": "收入成本配比",
        "category": "合理性检查",
        "severity": "warning",
        "description": "有收入无对应成本，或毛利率异常",
        "weight": 8,
    },
    "tax_account_balance": {
        "name": "应交税费异常",
        "category": "科目异常",
        "severity": "warning",
        "description": "应交税费科目余额与实际申报差异过大",
        "weight": 10,
    },
}


def run_batch_audit(
    db: Session,
    client_ids: list[str] | None = None,
    period: str | None = None,
    rules: list[str] | None = None,
    threshold_overrides: dict[str, float] | None = None,
) -> dict:
    """
    对指定客户（或全部）执行批量智能审账

    Args:
        client_ids: 客户ID列表，None=全部
        period: 期间 YYYY-MM，None=当前月
        rules: 要执行的规则 key 列表，None=全部
        threshold_overrides: 覆盖默认阈值 {"large_amount": 50000}

    Returns:
        {
            "summary": {total_clients, total_issues, passed_clients, failed_clients, ...},
            "clients": [{client_id, client_name, score, passed, issues: [...]}],
            "rule_stats": {rule_key: {total, passed, failed}},
        }
    """
    from app.models.client import Client
    from app.models.voucher import AccountingVoucher
    from app.models.bank import BankStatementLine, BankAccount

    today = dt_date.today()
    if period:
        y, m = map(int, period.split("-"))
    else:
        y, m = today.year, today.month

    period_str = f"{y}-{m:02d}"
    ms = dt_date(y, m, 1)
    if m == 12:
        me = dt_date(y + 1, 1, 1) - timedelta(days=1)
    else:
        me = dt_date(y, m + 1, 1) - timedelta(days=1)

    # 确定要执行的规则
    active_rules = rules or list(AUDIT_RULES.keys())
    rule_configs = {k: AUDIT_RULES[k] for k in active_rules if k in AUDIT_RULES}

    # 阈值覆盖
    if threshold_overrides:
        for k, v in threshold_overrides.items():
            if k in rule_configs and "config" in rule_configs[k]:
                rule_configs[k]["config"]["threshold"] = v

    # 获取客户
    q = db.query(Client)
    if client_ids:
        q = q.filter(Client.id.in_(client_ids))
    clients = q.all()

    client_results = []
    rule_stats = defaultdict(lambda: {"total": 0, "passed": 0, "failed": 0})

    for client in clients:
        issues = []
        max_score = sum(r["weight"] for r in rule_configs.values())
        score = max_score

        # 加载本月凭证
        vouchers = db.query(AccountingVoucher).filter(
            AccountingVoucher.client_id == client.id,
            AccountingVoucher.voucher_date >= ms,
            AccountingVoucher.voucher_date <= me,
        ).all()

        # 加载银行账户
        bank_accounts = db.query(BankAccount).filter(
            BankAccount.client_id == client.id,
        ).all()
        bank_account_ids = [a.id for a in bank_accounts]

        # === 规则: 借贷平衡 ===
        if "balance" in rule_configs:
            rule = rule_configs["balance"]
            unbalanced = []
            for v in vouchers:
                if v.total_debit is not None and v.total_credit is not None:
                    if abs(v.total_debit - v.total_credit) > 0.01:
                        unbalanced.append({
                            "voucher_no": v.voucher_no,
                            "debit": v.total_debit,
                            "credit": v.total_credit,
                            "diff": round(v.total_debit - v.total_credit, 2),
                        })
            if unbalanced:
                score -= rule["weight"]
                issues.append({
                    "rule_key": "balance", "rule_name": rule["name"],
                    "severity": rule["severity"], "category": rule["category"],
                    "passed": False, "detail": f"{len(unbalanced)} 张凭证借贷不平衡",
                    "samples": unbalanced[:5],
                })
                rule_stats["balance"]["failed"] += 1
            else:
                rule_stats["balance"]["passed"] += 1
            rule_stats["balance"]["total"] += 1

        # === 规则: 凭证断号 ===
        if "gap_number" in rule_configs and vouchers:
            rule = rule_configs["gap_number"]
            nums = []
            for v in vouchers:
                try:
                    n = int(v.voucher_no.replace("记", "").replace("字", "").replace("第", "").replace("号", "").split("-")[-1])
                    nums.append(n)
                except (ValueError, AttributeError):
                    pass
            nums.sort()
            gaps = []
            for i in range(1, len(nums)):
                if nums[i] - nums[i-1] > 1:
                    gaps.extend(range(nums[i-1] + 1, nums[i]))
            if gaps:
                score -= rule["weight"]
                issues.append({
                    "rule_key": "gap_number", "rule_name": rule["name"],
                    "severity": rule["severity"], "category": rule["category"],
                    "passed": False,
                    "detail": f"发现 {len(gaps)} 个断号: {gaps[:10]}",
                })
                rule_stats["gap_number"]["failed"] += 1
            else:
                rule_stats["gap_number"]["passed"] += 1
            rule_stats["gap_number"]["total"] += 1

        # === 规则: 大额凭证 ===
        if "large_amount" in rule_configs and vouchers:
            rule = rule_configs["large_amount"]
            threshold = rule.get("config", {}).get("threshold", 100_000)
            large = []
            for v in vouchers:
                amt = max(float(v.total_debit or 0), float(v.total_credit or 0))
                if amt > threshold:
                    large.append({
                        "voucher_no": v.voucher_no,
                        "amount": round(amt, 2),
                        "summary": v.summary or "",
                    })
            if large:
                score -= rule["weight"]
                issues.append({
                    "rule_key": "large_amount", "rule_name": rule["name"],
                    "severity": rule["severity"], "category": rule["category"],
                    "passed": False,
                    "detail": f"{len(large)} 张凭证金额超过 ¥{threshold:,.0f}",
                    "samples": large[:5],
                })
                rule_stats["large_amount"]["failed"] += 1
            else:
                rule_stats["large_amount"]["passed"] += 1
            rule_stats["large_amount"]["total"] += 1

        # === 规则: 重复凭证 ===
        if "duplicate" in rule_configs and vouchers:
            rule = rule_configs["duplicate"]
            seen = {}
            dups = []
            for v in vouchers:
                key = (str(v.voucher_date), round(float(v.total_debit or 0), 2),
                       round(float(v.total_credit or 0), 2), v.summary or "")
                if key in seen:
                    dups.append({
                        "voucher_no_1": seen[key],
                        "voucher_no_2": v.voucher_no,
                        "amount": round(float(v.total_debit or 0), 2),
                    })
                else:
                    seen[key] = v.voucher_no
            if dups:
                score -= rule["weight"]
                issues.append({
                    "rule_key": "duplicate", "rule_name": rule["name"],
                    "severity": rule["severity"], "category": rule["category"],
                    "passed": False,
                    "detail": f"发现 {len(dups)} 组可能的重复凭证",
                    "samples": dups[:5],
                })
                rule_stats["duplicate"]["failed"] += 1
            else:
                rule_stats["duplicate"]["passed"] += 1
            rule_stats["duplicate"]["total"] += 1

        # === 规则: 未确认凭证 ===
        if "unconfirmed" in rule_configs:
            rule = rule_configs["unconfirmed"]
            unconfirmed = [v for v in vouchers if v.status != "confirmed"]
            if unconfirmed:
                score -= rule["weight"]
                issues.append({
                    "rule_key": "unconfirmed", "rule_name": rule["name"],
                    "severity": rule["severity"], "category": rule["category"],
                    "passed": False,
                    "detail": f"{len(unconfirmed)} 张凭证未确认",
                    "samples": [{"voucher_no": v.voucher_no, "status": v.status} for v in unconfirmed[:5]],
                })
                rule_stats["unconfirmed"]["failed"] += 1
            else:
                rule_stats["unconfirmed"]["passed"] += 1
            rule_stats["unconfirmed"]["total"] += 1

        # === 规则: 挂账科目检查 ===
        if "suspense_account" in rule_configs and vouchers:
            rule = rule_configs["suspense_account"]
            suspense_codes = ["1221", "2241", "2242", "1901", "6301"]  # 其他应收/应付/待摊/待处理
            suspicious = []
            for v in vouchers:
                try:
                    entries = json.loads(v.entries) if isinstance(v.entries, str) else (v.entries or [])
                except (json.JSONDecodeError, TypeError):
                    entries = []
                for e in entries:
                    code = str(e.get("account_code", ""))
                    if any(code.startswith(sc) for sc in suspense_codes):
                        debit = float(e.get("debit", 0) or 0)
                        credit = float(e.get("credit", 0) or 0)
                        if abs(debit - credit) > 100:
                            suspicious.append({
                                "voucher_no": v.voucher_no,
                                "account_code": code,
                                "account_name": e.get("account_name", ""),
                                "debit": debit,
                                "credit": credit,
                            })
            if suspicious:
                score -= rule["weight"]
                issues.append({
                    "rule_key": "suspense_account", "rule_name": rule["name"],
                    "severity": rule["severity"], "category": rule["category"],
                    "passed": False,
                    "detail": f"{len(suspicious)} 笔挂账科目交易需复核",
                    "samples": suspicious[:5],
                })
                rule_stats["suspense_account"]["failed"] += 1
            else:
                rule_stats["suspense_account"]["passed"] += 1
            rule_stats["suspense_account"]["total"] += 1

        # === 规则: 负数凭证 ===
        if "negative_amount" in rule_configs and vouchers:
            rule = rule_configs["negative_amount"]
            negs = []
            for v in vouchers:
                td = float(v.total_debit or 0)
                tc = float(v.total_credit or 0)
                if td < 0 or tc < 0:
                    negs.append({"voucher_no": v.voucher_no, "debit": td, "credit": tc})
            if negs:
                score -= rule["weight"]
                issues.append({
                    "rule_key": "negative_amount", "rule_name": rule["name"],
                    "severity": rule["severity"], "category": rule["category"],
                    "passed": False,
                    "detail": f"{len(negs)} 张凭证含负数金额",
                    "samples": negs[:5],
                })
                rule_stats["negative_amount"]["failed"] += 1
            else:
                rule_stats["negative_amount"]["passed"] += 1
            rule_stats["negative_amount"]["total"] += 1

        # === 规则: 摘要缺失 ===
        if "missing_summary" in rule_configs and vouchers:
            rule = rule_configs["missing_summary"]
            no_summary = []
            for v in vouchers:
                if not v.summary or len(v.summary.strip()) < 2:
                    no_summary.append({"voucher_no": v.voucher_no})
                else:
                    try:
                        entries = json.loads(v.entries) if isinstance(v.entries, str) else (v.entries or [])
                    except (json.JSONDecodeError, TypeError):
                        entries = []
                    for e in entries:
                        if not e.get("summary") or len(str(e.get("summary", "")).strip()) < 2:
                            no_summary.append({
                                "voucher_no": v.voucher_no,
                                "entry_account": e.get("account_code", ""),
                            })
            if no_summary:
                score -= rule["weight"]
                issues.append({
                    "rule_key": "missing_summary", "rule_name": rule["name"],
                    "severity": rule["severity"], "category": rule["category"],
                    "passed": False,
                    "detail": f"{len(no_summary)} 处摘要缺失或过短",
                })
                rule_stats["missing_summary"]["failed"] += 1
            else:
                rule_stats["missing_summary"]["passed"] += 1
            rule_stats["missing_summary"]["total"] += 1

        # === 规则: 跨期凭证 ===
        if "cross_period" in rule_configs and vouchers:
            rule = rule_configs["cross_period"]
            cross = []
            for v in vouchers:
                if v.voucher_date:
                    vd = v.voucher_date if isinstance(v.voucher_date, dt_date) else dt_date.fromisoformat(str(v.voucher_date))
                    if vd < ms or vd > me:
                        cross.append({"voucher_no": v.voucher_no, "date": str(vd)})
            if cross:
                score -= rule["weight"]
                issues.append({
                    "rule_key": "cross_period", "rule_name": rule["name"],
                    "severity": rule["severity"], "category": rule["category"],
                    "passed": False,
                    "detail": f"{len(cross)} 张凭证日期不在 {period_str} 内",
                    "samples": cross[:5],
                })
                rule_stats["cross_period"]["failed"] += 1
            else:
                rule_stats["cross_period"]["passed"] += 1
            rule_stats["cross_period"]["total"] += 1

        # === 规则: 银行未匹配 ===
        if "unmatched_bank" in rule_configs and bank_account_ids:
            rule = rule_configs["unmatched_bank"]
            unmatched_count = db.query(BankStatementLine).filter(
                BankStatementLine.bank_account_id.in_(bank_account_ids),
                BankStatementLine.match_status == "unmatched",
            ).count()
            if unmatched_count > 0:
                score -= rule["weight"]
                issues.append({
                    "rule_key": "unmatched_bank", "rule_name": rule["name"],
                    "severity": rule["severity"], "category": rule["category"],
                    "passed": False,
                    "detail": f"{unmatched_count} 笔银行流水未匹配",
                })
                rule_stats["unmatched_bank"]["failed"] += 1
            else:
                rule_stats["unmatched_bank"]["passed"] += 1
            rule_stats["unmatched_bank"]["total"] += 1

        # === 规则: 收入成本配比 ===
        if "revenue_expense_mismatch" in rule_configs and vouchers:
            rule = rule_configs["revenue_expense_mismatch"]
            rev_codes = {"6001", "6051"}
            cost_codes = {"6401", "6402", "6403"}
            total_rev = 0
            total_cost = 0
            for v in vouchers:
                try:
                    entries = json.loads(v.entries) if isinstance(v.entries, str) else (v.entries or [])
                except (json.JSONDecodeError, TypeError):
                    entries = []
                for e in entries:
                    code = str(e.get("account_code", ""))
                    if code in rev_codes:
                        total_rev += float(e.get("credit", 0) or 0)
                    if code in cost_codes:
                        total_cost += float(e.get("debit", 0) or 0)
            if total_rev > 0 and total_cost == 0:
                score -= rule["weight"]
                issues.append({
                    "rule_key": "revenue_expense_mismatch", "rule_name": rule["name"],
                    "severity": rule["severity"], "category": rule["category"],
                    "passed": False,
                    "detail": f"收入 ¥{total_rev:,.2f} 但无对应成本，请确认是否需要结转成本",
                })
                rule_stats["revenue_expense_mismatch"]["failed"] += 1
            elif total_rev > 0 and total_cost / total_rev > 0.95:
                score -= rule["weight"] // 2
                issues.append({
                    "rule_key": "revenue_expense_mismatch", "rule_name": rule["name"],
                    "severity": "info", "category": rule["category"],
                    "passed": False,
                    "detail": f"毛利率 {(1 - total_cost/total_rev)*100:.1f}% 偏低，请复核",
                })
                rule_stats["revenue_expense_mismatch"]["failed"] += 1
            else:
                rule_stats["revenue_expense_mismatch"]["passed"] += 1
            rule_stats["revenue_expense_mismatch"]["total"] += 1

        # === 规则: 应交税费异常 ===
        if "tax_account_balance" in rule_configs and vouchers:
            rule = rule_configs["tax_account_balance"]
            tax_codes = {"2221", "2221001", "2221002"}
            tax_debit = 0
            tax_credit = 0
            for v in vouchers:
                try:
                    entries = json.loads(v.entries) if isinstance(v.entries, str) else (v.entries or [])
                except (json.JSONDecodeError, TypeError):
                    entries = []
                for e in entries:
                    code = str(e.get("account_code", ""))
                    if any(code.startswith(tc) for tc in tax_codes):
                        tax_debit += float(e.get("debit", 0) or 0)
                        tax_credit += float(e.get("credit", 0) or 0)
            tax_balance = tax_credit - tax_debit
            if tax_balance < -100:
                score -= rule["weight"]
                issues.append({
                    "rule_key": "tax_account_balance", "rule_name": rule["name"],
                    "severity": rule["severity"], "category": rule["category"],
                    "passed": False,
                    "detail": f"应交税费借方余额 ¥{abs(tax_balance):,.2f}（异常：通常应为贷方余额）",
                })
                rule_stats["tax_account_balance"]["failed"] += 1
            else:
                rule_stats["tax_account_balance"]["passed"] += 1
            rule_stats["tax_account_balance"]["total"] += 1

        # === 汇总 ===
        score = max(0, score)
        if score >= max_score * 0.85:
            grade = "excellent"
        elif score >= max_score * 0.7:
            grade = "good"
        elif score >= max_score * 0.5:
            grade = "warning"
        else:
            grade = "danger"

        client_results.append({
            "client_id": client.id,
            "client_name": client.name,
            "period": period_str,
            "score": score,
            "max_score": max_score,
            "grade": grade,
            "passed": len([i for i in issues if i["severity"] == "blocker"]) == 0,
            "issues": issues,
            "blocker_count": len([i for i in issues if i["severity"] == "blocker"]),
            "warning_count": len([i for i in issues if i["severity"] == "warning"]),
            "info_count": len([i for i in issues if i["severity"] == "info"]),
            "voucher_count": len(vouchers),
        })

    # 排序：问题多的排前面
    client_results.sort(key=lambda r: r["score"])

    total_issues = sum(len(c["issues"]) for c in client_results)
    passed_clients = sum(1 for c in client_results if c["passed"])
    blocker_clients = sum(1 for c in client_results if c["blocker_count"] > 0)

    return {
        "period": period_str,
        "total_clients": len(clients),
        "total_issues": total_issues,
        "passed_clients": passed_clients,
        "failed_clients": len(clients) - passed_clients,
        "blocker_clients": blocker_clients,
        "rules_executed": len(active_rules),
        "clients": client_results,
        "rule_stats": {
            k: {"name": AUDIT_RULES[k]["name"], **v}
            for k, v in rule_stats.items()
        },
        "audited_at": dt_date.today().isoformat(),
    }
