"""财务报表服务：科目余额表、总账、利润表、资产负债表"""
import json
from collections import defaultdict
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.voucher import AccountingVoucher
from app.models.account import ChartOfAccount


def get_account_map(db: Session) -> dict[str, dict]:
    """获取所有科目映射"""
    accounts = db.query(ChartOfAccount).filter(ChartOfAccount.is_active == True).all()
    return {
        a.code: {"name": a.name, "category": a.category, "direction": a.direction, "parent_code": a.parent_code}
        for a in accounts
    }


def get_confirmed_entries(db: Session, start_date: str, end_date: str) -> list[dict]:
    """获取已确认凭证的所有分录（指定日期范围）"""
    vouchers = (
        db.query(AccountingVoucher)
        .filter(
            AccountingVoucher.status == "confirmed",
            AccountingVoucher.voucher_date >= start_date,
            AccountingVoucher.voucher_date <= end_date,
        )
        .all()
    )

    entries = []
    for v in vouchers:
        v_entries = json.loads(v.entries) if v.entries else []
        for e in v_entries:
            entries.append({
                "voucher_no": v.voucher_no,
                "voucher_date": v.voucher_date.isoformat(),
                "account_code": e.get("account_code", ""),
                "account_name": e.get("account_name", ""),
                "debit": e.get("debit", 0) or 0,
                "credit": e.get("credit", 0) or 0,
                "summary": e.get("summary", v.summary),
                "client_id": v.client_id or "",
            })
    return entries


def trial_balance(db: Session, period: str) -> list[dict]:
    """科目余额表"""
    year = int(period[:4])
    month = int(period[5:7])
    start_date = f"{year}-{month:02d}-01"
    # 简易处理：取当月
    if month == 12:
        end_date = f"{year}-12-31"
    else:
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        end_date = f"{year}-{month:02d}-{last_day}"

    account_map = get_account_map(db)
    entries = get_confirmed_entries(db, start_date, end_date)

    # 按科目汇总
    summary = defaultdict(lambda: {"debit": 0.0, "credit": 0.0})
    for e in entries:
        code = e["account_code"]
        summary[code]["debit"] += e["debit"]
        summary[code]["credit"] += e["credit"]

    result = []
    for code, data in sorted(summary.items()):
        acct = account_map.get(code, {})
        total_debit = round(data["debit"], 2)
        total_credit = round(data["credit"], 2)

        # 根据科目方向计算余额
        if acct.get("direction") == "debit":
            balance = round(total_debit - total_credit, 2)
            closing_debit = max(balance, 0)
            closing_credit = max(-balance, 0)
        else:  # credit 方向
            balance = round(total_credit - total_debit, 2)
            closing_debit = max(-balance, 0)
            closing_credit = max(balance, 0)

        result.append({
            "account_code": code,
            "account_name": acct.get("name", ""),
            "category": acct.get("category", ""),
            "period_debit": total_debit,
            "period_credit": total_credit,
            "closing_debit": closing_debit,
            "closing_credit": closing_credit,
        })

    return result


def income_statement(db: Session, period: str) -> list[dict]:
    """利润表（简易版）"""
    year = int(period[:4])
    month = int(period[5:7])
    start_date = f"{year}-01-01"
    import calendar
    last_day = calendar.monthrange(year, month)[1]
    end_date = f"{year}-{month:02d}-{last_day}"

    account_map = get_account_map(db)
    entries = get_confirmed_entries(db, start_date, end_date)

    # 按科目汇总的同时也支持前缀匹配
    summary = defaultdict(lambda: {"debit": 0.0, "credit": 0.0})
    for e in entries:
        code = e["account_code"]
        summary[code]["debit"] += e["debit"]
        summary[code]["credit"] += e["credit"]

    def sum_by_prefix(code_prefix: str) -> dict[str, float]:
        """汇总所有以 code_prefix 开头的科目"""
        debit = 0.0
        credit = 0.0
        for code, data in summary.items():
            if code.startswith(code_prefix):
                debit += data["debit"]
                credit += data["credit"]
        return {"debit": debit, "credit": credit}

    def net(code_prefix: str) -> float:
        """收入类科目：贷方净额"""
        s = sum_by_prefix(code_prefix)
        return round(s["credit"] - s["debit"], 2)

    def expense(code_prefix: str) -> float:
        """费用类科目：借方净额"""
        s = sum_by_prefix(code_prefix)
        return round(s["debit"] - s["credit"], 2)

    # 收入
    main_income = net("6001")
    total_income = round(main_income + net("6051"), 2)

    # 成本费用
    main_cost = expense("6401")
    tax_surcharge = expense("6403") + expense("6405")
    selling_exp = expense("6601")
    admin_exp = expense("6602")
    finance_exp = expense("6603")

    # 营业利润 = 营业收入 - 营业成本 - 税金及附加 - 三费
    gross_profit = round(total_income - main_cost, 2)
    operating_profit = round(gross_profit - tax_surcharge - selling_exp - admin_exp - finance_exp, 2)

    # 利润总额 = 营业利润 + 营业外收入 - 营业外支出
    other_income_net = net("6051")  # 营业外收入净额
    total_profit = round(operating_profit + other_income_net - expense("6711"), 2)

    # 净利润 = 利润总额 - 所得税
    tax_expense = expense("6801")
    net_profit = round(total_profit - tax_expense, 2)

    return [
        {"item": "一、营业收入", "line_no": 1, "amount": total_income},
        {"item": "减：营业成本", "line_no": 2, "amount": main_cost},
        {"item": "    税金及附加", "line_no": 3, "amount": tax_surcharge},
        {"item": "    销售费用", "line_no": 4, "amount": selling_exp},
        {"item": "    管理费用", "line_no": 5, "amount": admin_exp},
        {"item": "    财务费用", "line_no": 6, "amount": finance_exp},
        {"item": "二、营业利润", "line_no": 7, "amount": operating_profit},
        {"item": "加：营业外收入", "line_no": 8, "amount": other_income_net},
        {"item": "三、利润总额", "line_no": 9, "amount": total_profit},
        {"item": "减：所得税费用", "line_no": 10, "amount": tax_expense},
        {"item": "四、净利润", "line_no": 11, "amount": net_profit},
    ]


def balance_sheet(db: Session, period: str) -> dict:
    """资产负债表（简易版）"""
    year = int(period[:4])
    month = int(period[5:7])
    import calendar
    last_day = calendar.monthrange(year, month)[1]
    end_date = f"{year}-{month:02d}-{last_day}"

    account_map = get_account_map(db)
    entries = get_confirmed_entries(db, f"{year}-01-01", end_date)

    summary = defaultdict(lambda: {"debit": 0.0, "credit": 0.0})
    for e in entries:
        code = e["account_code"]
        summary[code]["debit"] += e["debit"]
        summary[code]["credit"] += e["credit"]

    def asset_balance(code_prefix: str) -> float:
        """资产类科目：借方余额，按前缀匹配"""
        debit = sum(data["debit"] for c, data in summary.items() if c.startswith(code_prefix))
        credit = sum(data["credit"] for c, data in summary.items() if c.startswith(code_prefix))
        return round(debit - credit, 2)

    def liability_balance(code_prefix: str) -> float:
        """负债/权益类科目：贷方余额，按前缀匹配"""
        debit = sum(data["debit"] for c, data in summary.items() if c.startswith(code_prefix))
        credit = sum(data["credit"] for c, data in summary.items() if c.startswith(code_prefix))
        return round(credit - debit, 2)

    # 流动资产
    cash = asset_balance("1001") + asset_balance("1002")
    ar = asset_balance("1122")
    prepay = asset_balance("1123")
    inventory = asset_balance("1405")
    current_assets = round(cash + ar + prepay + inventory, 2)

    # 非流动资产
    fixed_assets = asset_balance("1601") + asset_balance("1602")
    total_assets = round(current_assets + fixed_assets, 2)

    # 负债
    ap = liability_balance("2202")
    tax_payable = liability_balance("2221")
    total_liabilities = round(ap + tax_payable, 2)

    # 本期损益（从分录汇总计算，确保资产负债表平衡）
    revenue = sum(data["credit"] - data["debit"] for c, data in summary.items() if c.startswith("60") or c.startswith("61") or c.startswith("6051"))  # 收入类贷方净额
    cost_expense = sum(data["debit"] - data["credit"] for c, data in summary.items() if c.startswith("64") or c.startswith("6601") or c.startswith("6602") or c.startswith("6603"))  # 成本费用借方净额
    period_profit = round(revenue - cost_expense, 2)

    # 权益 = 实收资本 + 未分配利润（含本期损益）
    capital = liability_balance("4001")
    retained = liability_balance("4104") + period_profit  # 未分配利润 = 期初 + 本期
    total_equity = round(capital + retained, 2)

    return {
        "assets": [
            {"item": "货币资金", "amount": cash},
            {"item": "应收账款", "amount": ar},
            {"item": "预付账款", "amount": prepay},
            {"item": "存货", "amount": inventory},
            {"item": "流动资产合计", "amount": current_assets, "bold": True},
            {"item": "固定资产净值", "amount": fixed_assets},
            {"item": "资产总计", "amount": total_assets, "bold": True},
        ],
        "liabilities": [
            {"item": "应付账款", "amount": ap},
            {"item": "应交税费", "amount": tax_payable},
            {"item": "负债合计", "amount": total_liabilities, "bold": True},
        ],
        "equity": [
            {"item": "实收资本", "amount": capital},
            {"item": "未分配利润", "amount": retained},
            {"item": "所有者权益合计", "amount": total_equity, "bold": True},
        ],
        "total_liabilities_and_equity": round(total_liabilities + total_equity, 2),
    }


def cash_flow_statement(db: Session, period: str) -> list[dict]:
    """现金流量表（简易版 — 基于凭证分录直接法）"""
    year = int(period[:4])
    month = int(period[5:7])
    import calendar
    last_day = calendar.monthrange(year, month)[1]
    start_date = f"{year}-{month:02d}-01"
    end_date = f"{year}-{month:02d}-{last_day}"

    entries = get_confirmed_entries(db, start_date, end_date)

    # 经营活动
    # 销售商品/提供劳务收到的现金 = 收入类科目贷方 + 销项税额（222101贷方）
    sales_cash = sum(e["credit"] for e in entries if e["account_code"].startswith("6001") or e["account_code"].startswith("6051"))
    output_tax_cash = sum(e["credit"] for e in entries if e["account_code"] == "222101")  # 销项税
    cash_from_sales = round(sales_cash + output_tax_cash, 2)

    # 收到的税费返还
    tax_refund = sum(e["debit"] for e in entries if e["account_code"].startswith("2221") and e["account_name"] and "返还" in str(e.get("summary", "")))

    # 购买商品/接受劳务支付的现金 = 成本+进项税（借方）+ 存货增加
    cost_paid = sum(e["debit"] for e in entries if e["account_code"].startswith("6401"))
    input_tax_paid = sum(e["debit"] for e in entries if e["account_code"] == "222101")  # 进项税
    inventory_paid = sum(e["debit"] for e in entries if e["account_code"].startswith("140"))
    cash_for_purchase = round(cost_paid + input_tax_paid + inventory_paid, 2)

    # 支付给职工的现金 = 应付职工薪酬借方发生额
    payroll_paid = sum(e["debit"] for e in entries if e["account_code"].startswith("2211"))

    # 支付的各项税费
    tax_paid = sum(e["debit"] for e in entries if any(e["account_code"].startswith(p) for p in ("2221", "6801")))

    # 支付其他与经营活动有关的现金（三费）
    selling_paid = sum(e["debit"] for e in entries if e["account_code"].startswith("6601"))
    admin_paid = sum(e["debit"] for e in entries if e["account_code"].startswith("6602"))
    finance_paid = sum(e["debit"] for e in entries if e["account_code"].startswith("6603"))

    operating_inflow = cash_from_sales + tax_refund
    operating_outflow = round(cash_for_purchase + payroll_paid + tax_paid + selling_paid + admin_paid + finance_paid, 2)
    operating_net = round(operating_inflow - operating_outflow, 2)

    # 投资活动
    # 收回投资/取得投资收益收到的现金
    invest_inflow = sum(e["credit"] for e in entries if e["account_code"].startswith("61"))
    # 购建固定资产/无形资产支付的现金
    fixed_asset_paid = sum(e["debit"] for e in entries if e["account_code"].startswith(("1601", "1701")))
    invest_outflow = round(fixed_asset_paid, 2)
    investing_net = round(invest_inflow - invest_outflow, 2)

    # 筹资活动
    # 吸收投资收到的现金
    capital_inflow = sum(e["credit"] for e in entries if e["account_code"].startswith("4001"))
    # 偿还债务/分配股利支付的现金
    debt_paid = sum(e["debit"] for e in entries if e["account_code"].startswith(("2501", "4002")))
    financing_net = round(capital_inflow - debt_paid, 2)

    # 现金及现金等价物净增加额
    net_cash_increase = round(operating_net + investing_net + financing_net, 2)

    # 期初现金（从银行存款 + 库存现金余额）
    # 简化：取本期贷方合计近似
    opening_cash = round(sum(e["credit"] for e in entries if e["account_code"] in ("1001", "1002")), 2)
    ending_cash = round(opening_cash + net_cash_increase, 2)

    return [
        {"section": "一、经营活动产生的现金流量", "items": [
            {"item": "销售商品、提供劳务收到的现金", "amount": cash_from_sales},
            {"item": "收到的税费返还", "amount": tax_refund},
            {"item": "经营活动现金流入小计", "amount": operating_inflow, "bold": True},
            {"item": "购买商品、接受劳务支付的现金", "amount": -cash_for_purchase},
            {"item": "支付给职工以及为职工支付的现金", "amount": -payroll_paid},
            {"item": "支付的各项税费", "amount": -tax_paid},
            {"item": "支付其他与经营活动有关的现金", "amount": -(selling_paid + admin_paid + finance_paid)},
            {"item": "经营活动现金流出小计", "amount": -operating_outflow, "bold": True},
            {"item": "经营活动产生的现金流量净额", "amount": operating_net, "bold": True, "highlight": True},
        ]},
        {"section": "二、投资活动产生的现金流量", "items": [
            {"item": "收回投资收到的现金", "amount": invest_inflow},
            {"item": "投资活动现金流入小计", "amount": invest_inflow, "bold": True},
            {"item": "购建固定资产、无形资产支付的现金", "amount": -invest_outflow},
            {"item": "投资活动现金流出小计", "amount": -invest_outflow, "bold": True},
            {"item": "投资活动产生的现金流量净额", "amount": investing_net, "bold": True, "highlight": True},
        ]},
        {"section": "三、筹资活动产生的现金流量", "items": [
            {"item": "吸收投资收到的现金", "amount": capital_inflow},
            {"item": "筹资活动现金流入小计", "amount": capital_inflow, "bold": True},
            {"item": "偿还债务支付的现金", "amount": -debt_paid},
            {"item": "筹资活动现金流出小计", "amount": -debt_paid, "bold": True},
            {"item": "筹资活动产生的现金流量净额", "amount": financing_net, "bold": True, "highlight": True},
        ]},
        {"section": "汇总", "items": [
            {"item": "现金及现金等价物净增加额", "amount": net_cash_increase, "bold": True, "highlight": True},
            {"item": "期初现金及现金等价物余额", "amount": opening_cash},
            {"item": "期末现金及现金等价物余额", "amount": ending_cash, "bold": True},
        ]},
    ]


def _month_range(year: int, month: int):
    """返回某月的起止日期字符串"""
    start = f"{year}-{month:02d}-01"
    if month == 12:
        end = f"{year}-12-31"
    else:
        from calendar import monthrange
        end = f"{year}-{month:02d}-{monthrange(year, month)[1]}"
    return start, end


def _sum_by_account(entries: list[dict], prefixes: list[str], side: str = "credit") -> float:
    """按科目前缀汇总发生额"""
    return round(sum(
        e[side] for e in entries
        if any(e["account_code"].startswith(p) for p in prefixes)
    ), 2)


def dashboard_data(db: Session, client_id: str = None) -> dict:
    """经营分析仪表盘 — 对标亿企赢 KPI 驾驶舱"""
    from datetime import date as dt_date
    from app.models.document import OriginalDocument
    from app.models.filing import TaxFiling

    today = dt_date.today()
    month_start, month_end = _month_range(today.year, today.month)

    # 限定客户范围
    voucher_filter = [AccountingVoucher.status == "confirmed"]
    doc_filter = []
    filing_filter = []
    if client_id:
        voucher_filter.append(AccountingVoucher.client_id == client_id)
        doc_filter.append(OriginalDocument.client_id == client_id)
        filing_filter.append(TaxFiling.client_id == client_id)

    # === 本月核心指标 ===
    entries = get_confirmed_entries(db, month_start, month_end)
    if client_id:
        entries = [e for e in entries if e.get("client_id") == client_id]

    revenue = _sum_by_account(entries, ["6001", "6051"], "credit")  # 主营业务收入 + 其他业务收入
    cost = _sum_by_account(entries, ["6401", "6402", "6403"], "debit")  # 主营业务成本
    selling_exp = _sum_by_account(entries, ["6601"], "debit")  # 销售费用
    admin_exp = _sum_by_account(entries, ["6602"], "debit")  # 管理费用
    finance_exp = _sum_by_account(entries, ["6603"], "debit")  # 财务费用
    total_expenses = round(cost + selling_exp + admin_exp + finance_exp, 2)
    gross_profit = round(revenue - cost, 2)
    profit_margin = round((gross_profit / revenue * 100), 1) if revenue > 0 else 0

    # 税金
    output_vat = _sum_by_account(entries, ["2221001"], "credit")  # 销项税额
    input_vat = _sum_by_account(entries, ["2221002"], "debit")  # 进项税额 (借方)

    # === 资产负债快照 ===
    cash_bank = _sum_by_account(entries, ["1001", "1002"], "debit") - _sum_by_account(entries, ["1001", "1002"], "credit")
    ar = _sum_by_account(entries, ["1122"], "debit") - _sum_by_account(entries, ["1122"], "credit")
    ap = _sum_by_account(entries, ["2202"], "credit") - _sum_by_account(entries, ["2202"], "debit")

    # === 近6个月趋势 ===
    revenue_trend = []
    tax_trend = []
    for i in range(5, -1, -1):
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        ms, me = _month_range(y, m)
        month_entries = get_confirmed_entries(db, ms, me)
        if client_id:
            month_entries = [e for e in month_entries if e.get("client_id") == client_id]
        month_revenue = _sum_by_account(month_entries, ["6001", "6051"], "credit")
        month_vat = _sum_by_account(month_entries, ["2221001"], "credit") - _sum_by_account(month_entries, ["2221002"], "debit")
        revenue_trend.append({"month": f"{y}-{m:02d}", "revenue": month_revenue, "vat": round(max(month_vat, 0), 2)})
        tax_trend.append({"month": f"{y}-{m:02d}", "tax_burden": round((month_vat / month_revenue * 100), 2) if month_revenue > 0 else 0})

    # === 运营效率指标 ===
    doc_count = db.query(func.count(OriginalDocument.id)).filter(*doc_filter).scalar() or 0
    doc_processed = db.query(func.count(OriginalDocument.id)).filter(
        OriginalDocument.ocr_status == "done", *doc_filter
    ).scalar() or 0

    voucher_total = db.query(func.count(AccountingVoucher.id)).filter(*voucher_filter).scalar() or 0
    # 本月凭证
    voucher_month = db.query(func.count(AccountingVoucher.id)).filter(
        AccountingVoucher.status == "confirmed",
        AccountingVoucher.voucher_date >= month_start,
        AccountingVoucher.voucher_date <= month_end,
        *([AccountingVoucher.client_id == client_id] if client_id else []),
    ).scalar() or 0

    pending_filings = db.query(func.count(TaxFiling.id)).filter(
        TaxFiling.status == "pending", *filing_filter
    ).scalar() or 0
    submitted_filings = db.query(func.count(TaxFiling.id)).filter(
        TaxFiling.status.in_(["submitted", "success"]), *filing_filter
    ).scalar() or 0

    return {
        "current_month": {
            "revenue": revenue,
            "cost": cost,
            "gross_profit": gross_profit,
            "profit_margin": profit_margin,
            "selling_exp": selling_exp,
            "admin_exp": admin_exp,
            "finance_exp": finance_exp,
            "total_expenses": total_expenses,
            "output_vat": output_vat,
            "input_vat": input_vat,
            "vat_payable": round(max(output_vat - input_vat, 0), 2),
            "est_cit": round(max(gross_profit * 0.025, 0), 2) if gross_profit > 0 else 0,
        },
        "balance": {
            "cash_bank": round(max(cash_bank, 0), 2),
            "accounts_receivable": round(max(ar, 0), 2),
            "accounts_payable": round(max(ap, 0), 2),
        },
        "trends": {
            "revenue": revenue_trend,
            "tax_burden": tax_trend,
        },
        "operations": {
            "total_documents": doc_count,
            "documents_processed": doc_processed,
            "total_vouchers": voucher_total,
            "vouchers_this_month": voucher_month,
            "pending_filings": pending_filings,
            "submitted_filings": submitted_filings,
        },
    }
