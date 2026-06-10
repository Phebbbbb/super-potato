"""
结账风险检测引擎 — 20项结账前风险扫描

在企业期末结账前自动执行全面风险检测，
覆盖凭证完整、科目余额、银行对账、折旧摊销、税金计提及申报状态。
"""
import json
from datetime import date as dt_date, timedelta
from sqlalchemy.orm import Session


def run_close_risk_check(db: Session, client_id: str, period: str | None = None) -> dict:
    """
    对指定客户执行20项结账前风险检测

    返回:
        {
            "client_id", "client_name", "period",
            "total_checks": 20, "passed": 15, "warnings": 3, "blockers": 2,
            "score": 75,
            "check_items": [{check, status, detail, severity}],
            "can_close": false,
            "recommendations": [...]
        }
    """
    from app.models.client import Client
    from app.models.voucher import AccountingVoucher
    from app.models.filing import TaxFiling
    from app.models.bank import BankStatementLine, BankAccount
    from app.models.document import OriginalDocument

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

    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        return {"error": "客户不存在", "can_close": False}

    checks = []
    blockers = 0
    warnings = 0
    passed = 0
    max_score = 100
    score = max_score

    # 加载数据
    vouchers = db.query(AccountingVoucher).filter(
        AccountingVoucher.client_id == client_id,
        AccountingVoucher.voucher_date >= ms,
        AccountingVoucher.voucher_date <= me,
    ).all()

    all_entries = []
    for v in vouchers:
        try:
            e = json.loads(v.entries) if isinstance(v.entries, str) else (v.entries or [])
        except (json.JSONDecodeError, TypeError):
            e = []
        all_entries.extend(e)

    bank_accounts = db.query(BankAccount).filter(BankAccount.client_id == client_id).all()
    bank_ids = [a.id for a in bank_accounts]

    # ============================================================
    # 检查项 1-20
    # ============================================================

    # 1. 本月是否有凭证
    if len(vouchers) == 0:
        blockers += 1; score -= 20
        checks.append({"check": "本月凭证", "status": "blocker", "detail": "本月无任何凭证，无法结账", "severity": "blocker"})
    else:
        passed += 1
        checks.append({"check": "本月凭证", "status": "pass", "detail": f"共 {len(vouchers)} 张"})

    # 2. 未确认凭证
    unconfirmed = [v for v in vouchers if v.status != "confirmed"]
    if unconfirmed:
        warnings += 1; score -= 10
        checks.append({"check": "未确认凭证", "status": "warning",
                       "detail": f"{len(unconfirmed)} 张凭证未确认: {[v.voucher_no for v in unconfirmed[:3]]}",
                       "severity": "warning"})
    else:
        passed += 1
        checks.append({"check": "未确认凭证", "status": "pass", "detail": "全部已确认"})

    # 3. 借贷平衡
    unbalanced = []
    for v in vouchers:
        if v.total_debit is not None and v.total_credit is not None:
            if abs(v.total_debit - v.total_credit) > 0.01:
                unbalanced.append(v.voucher_no)
    if unbalanced:
        blockers += 1; score -= 25
        checks.append({"check": "借贷平衡", "status": "blocker",
                       "detail": f"{len(unbalanced)} 张凭证借贷不平衡", "severity": "blocker"})
    else:
        passed += 1
        checks.append({"check": "借贷平衡", "status": "pass", "detail": "全部平衡"})

    # 4. 科目试算平衡
    total_debit_sum = sum(float(e.get("debit", 0) or 0) for e in all_entries)
    total_credit_sum = sum(float(e.get("credit", 0) or 0) for e in all_entries)
    if abs(total_debit_sum - total_credit_sum) > 1:
        blockers += 1; score -= 25
        checks.append({"check": "试算平衡", "status": "blocker",
                       "detail": f"借方 ¥{total_debit_sum:,.2f} ≠ 贷方 ¥{total_credit_sum:,.2f}，差异 ¥{abs(total_debit_sum - total_credit_sum):,.2f}",
                       "severity": "blocker"})
    else:
        passed += 1
        checks.append({"check": "试算平衡", "status": "pass", "detail": "借贷合计一致"})

    # 5. 银行未匹配流水
    if bank_ids:
        unmatched = db.query(BankStatementLine).filter(
            BankStatementLine.bank_account_id.in_(bank_ids),
            BankStatementLine.match_status == "unmatched",
        ).count()
        if unmatched > 0:
            warnings += 1; score -= 8
            checks.append({"check": "银行对账", "status": "warning",
                           "detail": f"{unmatched} 笔银行流水未匹配", "severity": "warning"})
        else:
            passed += 1
            checks.append({"check": "银行对账", "status": "pass", "detail": "已全部匹配"})
    else:
        passed += 1
        checks.append({"check": "银行对账", "status": "pass", "detail": "无银行账户"})

    # 6. 固定资产折旧
    from app.models.fixed_asset import FixedAsset
    assets = db.query(FixedAsset).filter(
        FixedAsset.client_id == client_id,
        FixedAsset.status == "active",
    ).all()
    if assets:
        # 检查本月是否已折旧
        depreciation_codes = {"1602", "5101", "6602"}
        has_depr = any(
            str(e.get("account_code", "")) in depreciation_codes
            for e in all_entries
        )
        if not has_depr:
            warnings += 1; score -= 5
            checks.append({"check": "折旧计提", "status": "warning",
                           "detail": f"有 {len(assets)} 项资产未计提本月折旧", "severity": "warning"})
        else:
            passed += 1
            checks.append({"check": "折旧计提", "status": "pass", "detail": "已计提"})
    else:
        passed += 1
        checks.append({"check": "折旧计提", "status": "pass", "detail": "无固定资产"})

    # 7. 待处理原始凭证
    pending_docs = db.query(OriginalDocument).filter(
        OriginalDocument.client_id == client_id,
        OriginalDocument.ocr_status == "pending",
    ).count()
    if pending_docs > 0:
        warnings += 1; score -= 5
        checks.append({"check": "待处理票据", "status": "warning",
                       "detail": f"{pending_docs} 张票据未 OCR 识别", "severity": "warning"})
    else:
        passed += 1
        checks.append({"check": "待处理票据", "status": "pass", "detail": "已全部处理"})

    # 8. 未申报税种
    required_taxes = ["vat", "surtax", "stamp_duty"]
    if m in (1, 4, 7, 10):
        required_taxes.append("corporate_income")
    if client.taxpayer_type == "small" and m not in (1, 4, 7, 10):
        required_taxes = [t for t in required_taxes if t not in ("vat", "surtax")]

    tax_names = {"vat": "增值税", "surtax": "附加税", "stamp_duty": "印花税", "corporate_income": "企业所得税"}
    missing_filings = []
    for tt in required_taxes:
        existing = db.query(TaxFiling).filter(
            TaxFiling.client_id == client_id, TaxFiling.period == period_str, TaxFiling.tax_type == tt,
        ).first()
        if not existing:
            missing_filings.append(tax_names.get(tt, tt))

    if missing_filings:
        warnings += 1; score -= 10
        checks.append({"check": "申报状态", "status": "warning",
                       "detail": f"未创建申报: {', '.join(missing_filings)}", "severity": "warning"})
    else:
        passed += 1
        checks.append({"check": "申报状态", "status": "pass", "detail": "已全部创建"})

    # 9. 损益类科目未结平
    profit_loss_codes = {"6", "5"}  # 6开头=损益-收入/费用, 5开头=成本
    pl_balances = defaultdict(float)
    for e in all_entries:
        code = str(e.get("account_code", ""))
        if code and code[0] in profit_loss_codes:
            debit = float(e.get("debit", 0) or 0)
            credit = float(e.get("credit", 0) or 0)
            pl_balances[code] += debit - credit

    pl_with_balance = {k: v for k, v in pl_balances.items() if abs(v) > 1}
    if pl_with_balance:
        warnings += 1; score -= 10
        checks.append({"check": "损益结转", "status": "warning",
                       "detail": f"损益类科目未结平，余额合计 ¥{sum(pl_with_balance.values()):,.2f}",
                       "severity": "warning"})
    else:
        passed += 1
        checks.append({"check": "损益结转", "status": "pass", "detail": "损益已全部结转入本年利润"})

    # 10. 应交税费计提
    tax_account_codes = {"2221", "2221001", "2221002", "2221003", "2221004"}
    has_tax_entries = any(str(e.get("account_code", "")) in tax_account_codes for e in all_entries)
    if not has_tax_entries and len(vouchers) > 0:
        warnings += 1; score -= 5
        checks.append({"check": "税金计提", "status": "warning",
                       "detail": "本月无应交税费凭证，请确认是否需要计提", "severity": "warning"})
    else:
        passed += 1
        checks.append({"check": "税金计提", "status": "pass", "detail": "已处理" if has_tax_entries else "无应税事项"})

    # 11. 应付职工薪酬计提
    payroll_codes = {"2211", "2241", "2242"}
    has_payroll = any(
        str(e.get("account_code", "")) in payroll_codes for e in all_entries
    )
    if not has_payroll and len(vouchers) > 0:
        checks.append({"check": "薪酬计提", "status": "pass", "detail": "本月无薪酬计提（如确认无工资请忽略）"})
        passed += 1
    else:
        passed += 1
        checks.append({"check": "薪酬计提", "status": "pass", "detail": "已处理"})

    # 12. 凭证断号
    nums = []
    for v in vouchers:
        try:
            n = int(v.voucher_no.replace("记", "").replace("字", "").replace("第", "").replace("号", "").split("-")[-1])
            nums.append(n)
        except (ValueError, AttributeError):
            pass
    nums.sort()
    gaps = []
    if nums:
        for i in range(1, len(nums)):
            if nums[i] - nums[i-1] > 1:
                gaps.extend(range(nums[i-1] + 1, nums[i]))
    if gaps:
        warnings += 1; score -= 3
        checks.append({"check": "凭证连号", "status": "warning",
                       "detail": f"发现断号: {gaps[:10]}", "severity": "warning"})
    else:
        passed += 1
        checks.append({"check": "凭证连号", "status": "pass", "detail": "编号连续"})

    # 13. 大额异常凭证
    large_threshold = 100_000
    large_vouchers = []
    for v in vouchers:
        amt = max(float(v.total_debit or 0), float(v.total_credit or 0))
        if amt > large_threshold:
            large_vouchers.append({"voucher_no": v.voucher_no, "amount": round(amt, 2)})
    if large_vouchers:
        warnings += 1; score -= 5
        checks.append({"check": "大额交易", "status": "warning",
                       "detail": f"{len(large_vouchers)} 笔超 ¥{large_threshold:,.0f}",
                       "severity": "warning"})
    else:
        passed += 1
        checks.append({"check": "大额交易", "status": "pass", "detail": "无异常大额"})

    # 14. 收入确认
    rev_codes = {"6001", "6051"}
    has_revenue = any(str(e.get("account_code", "")) in rev_codes for e in all_entries)
    has_expense = any(str(e.get("account_code", ""))[0] in ("5", "6") for e in all_entries)
    if has_revenue and not has_expense:
        warnings += 1; score -= 5
        checks.append({"check": "成本匹配", "status": "warning",
                       "detail": "有收入但未发现成本/费用凭证", "severity": "warning"})
    else:
        passed += 1
        checks.append({"check": "成本匹配", "status": "pass", "detail": "正常"})

    # 15. 负数余额检测
    neg_entries = []
    for e in all_entries:
        if float(e.get("debit", 0) or 0) < 0 or float(e.get("credit", 0) or 0) < 0:
            neg_entries.append(e.get("account_code", ""))
    if neg_entries:
        warnings += 1; score -= 3
        checks.append({"check": "红字分录", "status": "warning",
                       "detail": f"{len(neg_entries)} 笔负金额分录", "severity": "warning"})
    else:
        passed += 1
        checks.append({"check": "红字分录", "status": "pass", "detail": "无异常"})

    # 16. 科目余额合理性
    cash_codes = {"1001", "1002"}
    cash_balance = 0
    for e in all_entries:
        code = str(e.get("account_code", ""))
        if code in cash_codes:
            cash_balance += float(e.get("debit", 0) or 0) - float(e.get("credit", 0) or 0)
    if cash_balance < 0:
        blockers += 1; score -= 20
        checks.append({"check": "现金余额", "status": "blocker",
                       "detail": f"货币资金余额为负 ¥{cash_balance:,.2f}，严重异常", "severity": "blocker"})
    else:
        passed += 1
        checks.append({"check": "现金余额", "status": "pass",
                       "detail": f"¥{cash_balance:,.2f}" if cash_balance != 0 else "余额为零"})

    # 17. 凭证日期连续性
    dates = sorted(set(str(v.voucher_date) for v in vouchers if v.voucher_date))
    if len(dates) < 3 and len(vouchers) > 5:
        warnings += 1; score -= 3
        checks.append({"check": "日期分布", "status": "warning",
                       "detail": "凭证日期集中在少数几天，建议按业务发生日记录", "severity": "warning"})
    else:
        passed += 1
        checks.append({"check": "日期分布", "status": "pass", "detail": "合理"})

    # 18. 客户基础信息
    missing_info = []
    if not client.tax_no:
        missing_info.append("税号")
    if not client.taxpayer_type:
        missing_info.append("纳税人类型")
    if missing_info:
        warnings += 1; score -= 5
        checks.append({"check": "客户档案", "status": "warning",
                       "detail": f"缺失: {', '.join(missing_info)}", "severity": "warning"})
    else:
        passed += 1
        checks.append({"check": "客户档案", "status": "pass", "detail": "完整"})

    # 19. 申报截止日
    deadline_day = 15
    days_left = (dt_date(y, m, deadline_day) - today).days
    if today > dt_date(y, m, deadline_day) and today.month == m + 1:
        warnings += 1; score -= 15
        checks.append({"check": "申报截止", "status": "warning",
                       "detail": f"已逾期 {abs(days_left)} 天！", "severity": "warning"})
    elif days_left <= 3:
        warnings += 1; score -= 5
        checks.append({"check": "申报截止", "status": "warning",
                       "detail": f"仅剩 {days_left} 天", "severity": "warning"})
    else:
        passed += 1
        checks.append({"check": "申报截止", "status": "pass", "detail": f"距截止 {days_left} 天"})

    # 20. 上月是否已关账
    if m == 1:
        prev_period = f"{y-1}-12"
    else:
        prev_period = f"{y}-{m-1:02d}"
    prev_vouchers = db.query(AccountingVoucher).filter(
        AccountingVoucher.client_id == client_id,
        AccountingVoucher.period == prev_period,
        AccountingVoucher.status == "confirmed",
    ).count()
    if prev_vouchers > 0:
        passed += 1
        checks.append({"check": "期初衔接", "status": "pass", "detail": f"上期 {prev_vouchers} 张已确认"})
    else:
        passed += 1
        checks.append({"check": "期初衔接", "status": "pass", "detail": "首期或上期无凭证"})

    # === 汇总 ===
    score = max(0, score)
    can_close = blockers == 0

    if score >= 85:
        overall = "excellent"
    elif score >= 70:
        overall = "good"
    elif score >= 50:
        overall = "warning"
    else:
        overall = "danger"

    recommendations = []
    if blockers > 0:
        recommendations.append(f"发现 {blockers} 项阻断问题，解决后才能安全关账")
    if warnings > 0:
        recommendations.append(f"发现 {warnings} 项预警，建议关账前复核")
    if can_close:
        recommendations.append("可执行期末结转")

    return {
        "client_id": client_id,
        "client_name": client.name,
        "period": period_str,
        "total_checks": 20,
        "passed_count": passed,
        "warning_count": warnings,
        "blocker_count": blockers,
        "score": score,
        "max_score": max_score,
        "grade": overall,
        "can_close": can_close,
        "check_items": checks,
        "recommendations": recommendations,
        "checked_at": today.isoformat(),
    }
