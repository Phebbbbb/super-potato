"""
财务报表PDF生成引擎 — 借鉴 ReportLab/PedroReports

生成: 资产负债表 / 利润表 / 纳税申报表 / 凭证打印 / 月度报告
输出: PDF (ReportLab fallback → HTML)
"""
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional

REPORT_DIR = Path(__file__).parent.parent.parent / "data" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class GeneratedReport:
    filename: str
    path: str
    report_type: str
    page_count: int = 0
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def _generate_html_report(title: str, sections: list[dict],
                          watermark: str = "", footer: str = "") -> str:
    """生成HTML格式报表（ReportLab不可用时兜底，也可直接打印）"""
    section_html = ""
    for sec in sections:
        section_html += f'<h2 style="color:#1a1a2e;border-bottom:2px solid #1677ff;padding-bottom:8px">{sec["heading"]}</h2>\n'

        if sec.get("type") == "table":
            section_html += _html_table(sec.get("headers", []), sec.get("rows", []),
                                        sec.get("summary_row"))
        elif sec.get("type") == "kv":
            section_html += _html_keyvalue(sec.get("pairs", []))
        elif sec.get("type") == "text":
            section_html += f'<p style="line-height:1.8;color:#333">{sec["content"]}</p>\n'
        elif sec.get("type") == "entries":
            section_html += _html_entries(sec.get("entries", []))

    watermark_div = ""
    if watermark:
        watermark_div = f'<div style="position:fixed;top:50%;left:50%;transform:translate(-50%,-50%) rotate(-30deg);font-size:80px;color:rgba(0,0,0,0.04);pointer-events:none;white-space:nowrap">{watermark}</div>'

    footer_div = ""
    if footer:
        footer_div = f'<div style="text-align:center;color:#999;font-size:11px;margin-top:30px;border-top:1px solid #eee;padding-top:12px">{footer}</div>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>{title}</title>
<style>
  @page {{ size: A4; margin: 20mm; }}
  body {{ font-family: 'Microsoft YaHei', 'SimSun', sans-serif; color: #333; max-width: 210mm; margin: auto; padding: 15mm; }}
  h1 {{ text-align: center; font-size: 22px; color: #1a1a2e; margin-bottom: 5px; }}
  .subtitle {{ text-align: center; color: #666; font-size: 12px; margin-bottom: 25px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 15px 0; font-size: 13px; }}
  th {{ background: #1677ff; color: #fff; padding: 8px 10px; text-align: left; font-weight: 500; }}
  td {{ padding: 7px 10px; border-bottom: 1px solid #eee; }}
  tr:nth-child(even) {{ background: #f9fafb; }}
  .amount {{ text-align: right; font-family: 'Courier New', monospace; }}
  .total-row {{ font-weight: bold; background: #e6f4ff !important; }}
  .kv-table td:first-child {{ background: #f5f5f5; font-weight: 500; width: 180px; }}
  .stamp {{ position: absolute; right: 30px; top: 80px; border: 2px solid #d00; color: #d00; padding: 8px 15px; border-radius: 4px; font-size: 13px; transform: rotate(8deg); }}
  @media print {{ body {{ padding: 0; }} }}
</style></head>
<body>
{watermark_div}
<h1>{title}</h1>
<div class="subtitle">生成日期：{datetime.now().strftime('%Y-%m-%d %H:%M')} &nbsp;|&nbsp; 智能财税系统</div>
{section_html}
{footer_div}
</body></html>"""


def _html_table(headers: list[str], rows: list[list],
                summary_row: list = None) -> str:
    html = '<table><thead><tr>'
    for h in headers:
        html += f'<th>{h}</th>'
    html += '</tr></thead><tbody>'

    for i, row in enumerate(rows):
        css_class = "total-row" if summary_row and i == len(rows) - 1 else ""
        html += f'<tr class="{css_class}">'
        for j, cell in enumerate(row):
            # 金额列右对齐
            is_amount = any(kw in (headers[j] if j < len(headers) else "").lower()
                            for kw in ["金额", "借方", "贷方", "余额", "收入", "成本", "利润"])
            cls = "amount" if is_amount else ""
            if isinstance(cell, (int, float)):
                formatted = f"¥{cell:,.2f}" if is_amount else str(cell)
            else:
                formatted = str(cell)
            html += f'<td class="{cls}">{formatted}</td>'
        html += '</tr>'
    html += '</tbody></table>'
    return html


def _html_keyvalue(pairs: list[tuple[str, str]]) -> str:
    html = '<table class="kv-table">'
    for k, v in pairs:
        html += f'<tr><td>{k}</td><td>{v}</td></tr>'
    html += '</table>'
    return html


def _html_entries(entries: list[dict]) -> str:
    rows = []
    for e in entries:
        rows.append([
            e.get("account_code", ""),
            e.get("account_name", ""),
            e.get("summary", ""),
            e.get("debit", 0) or 0,
            e.get("credit", 0) or 0,
        ])
    return _html_table(
        ["科目编码", "科目名称", "摘要", "借方金额", "贷方金额"],
        rows,
    )


# ===== 报表生成函数 =====


def generate_balance_sheet(voucher_entries: list[dict],
                           client_name: str = "",
                           period: str = "") -> GeneratedReport:
    """生成资产负债表"""
    # 汇总科目余额
    balances: dict[str, dict] = {}
    for entry in voucher_entries:
        code = entry.get("account_code", "")
        name = entry.get("account_name", "")
        if code not in balances:
            balances[code] = {"name": name, "debit": 0, "credit": 0}
        balances[code]["debit"] += entry.get("debit", 0) or 0
        balances[code]["credit"] += entry.get("credit", 0) or 0

    # 资产类（1开头）和负债权益类（2/3/4开头）
    assets_rows = []
    liabilities_rows = []
    total_assets = 0
    total_liabilities = 0

    for code, bal in sorted(balances.items()):
        if code.startswith("1"):
            amount = bal["debit"] - bal["credit"]
            assets_rows.append([code, bal["name"], amount if amount > 0 else 0])
            total_assets += max(amount, 0)
        else:
            amount = bal["credit"] - bal["debit"]
            liabilities_rows.append([code, bal["name"], amount if amount > 0 else 0])
            total_liabilities += max(amount, 0)

    title = f"资产负债表"
    if client_name:
        title = f"{client_name} — {title}"
    if period:
        title += f"（{period}）"

    sections = [
        {"heading": "资产", "type": "table",
         "headers": ["科目编码", "科目名称", "期末余额"],
         "rows": assets_rows + [["", "资产总计", total_assets]]},
        {"heading": "负债及所有者权益", "type": "table",
         "headers": ["科目编码", "科目名称", "期末余额"],
         "rows": liabilities_rows + [["", "负债及权益总计", total_liabilities]]},
    ]

    report_id = uuid.uuid4().hex[:10]
    filename = f"balance_sheet_{report_id}.html"
    path = REPORT_DIR / filename

    html = _generate_html_report(title, sections,
                                  watermark="内部使用",
                                  footer="本报表由智能财税系统自动生成，仅供参考。最终数据以税务申报为准。")
    path.write_text(html, "utf-8")

    return GeneratedReport(filename=filename, path=str(path), report_type="balance_sheet")


def generate_income_statement(voucher_entries: list[dict],
                              client_name: str = "",
                              period: str = "") -> GeneratedReport:
    """生成利润表"""
    # 按科目类别汇总
    revenue = 0      # 5开头 - 收入
    cost = 0         # 6开头 中成本部分
    expense = 0      # 6开头 中费用部分

    for entry in voucher_entries:
        code = entry.get("account_code", "")
        debit = entry.get("debit", 0) or 0
        credit = entry.get("credit", 0) or 0

        if code.startswith("5"):
            revenue += credit - debit
        elif code.startswith("6"):
            # 简化：6开头全部算费用
            expense += debit - credit

    gross_profit = revenue - cost
    net_profit = gross_profit - expense

    title = "利润表"
    if client_name:
        title = f"{client_name} — {title}"
    if period:
        title += f"（{period}）"

    sections = [{
        "heading": "经营成果",
        "type": "table",
        "headers": ["项目", "本期金额"],
        "rows": [
            ["一、营业收入", revenue],
            ["二、营业成本", cost],
            ["三、毛利", gross_profit],
            ["四、期间费用", expense],
            ["五、净利润", net_profit],
        ],
    }]

    report_id = uuid.uuid4().hex[:10]
    filename = f"income_statement_{report_id}.html"
    path = REPORT_DIR / filename

    html = _generate_html_report(title, sections,
                                  watermark="内部使用",
                                  footer="本报表由智能财税系统自动生成，仅供参考。")
    path.write_text(html, "utf-8")

    return GeneratedReport(filename=filename, path=str(path), report_type="income_statement")


def generate_tax_report(client_name: str, period: str,
                        tax_data: dict) -> GeneratedReport:
    """生成纳税申报表"""
    sections = []

    # 增值税部分
    if "vat" in tax_data:
        vat = tax_data["vat"]
        sections.append({
            "heading": "增值税申报",
            "type": "table",
            "headers": ["项目", "金额"],
            "rows": [
                ["销项税额", vat.get("output_tax", 0)],
                ["进项税额", vat.get("input_tax", 0)],
                ["应纳税额", vat.get("payable", 0)],
                ["实际缴纳", vat.get("paid", 0)],
            ],
        })

    # 企业所得税
    if "cit" in tax_data:
        cit = tax_data["cit"]
        sections.append({
            "heading": "企业所得税申报",
            "type": "table",
            "headers": ["项目", "金额"],
            "rows": [
                ["应纳税所得额", cit.get("taxable_income", 0)],
                ["适用税率", f'{cit.get("rate", 25)}%'],
                ["应纳税额", cit.get("payable", 0)],
                ["减免税额", cit.get("deduction", 0)],
                ["实际应缴", cit.get("net_payable", 0)],
            ],
        })

    # 附加税
    if "surcharge" in tax_data:
        sur = tax_data["surcharge"]
        sections.append({
            "heading": "附加税费",
            "type": "table",
            "headers": ["项目", "金额"],
            "rows": [
                ["城市维护建设税", sur.get("urban_construction", 0)],
                ["教育费附加", sur.get("education", 0)],
                ["地方教育附加", sur.get("local_education", 0)],
            ],
        })

    title = f"{client_name} — 纳税申报表（{period}）"

    report_id = uuid.uuid4().hex[:10]
    filename = f"tax_report_{report_id}.html"
    path = REPORT_DIR / filename

    html = _generate_html_report(title, sections,
                                  footer="本报表由智能财税系统自动生成。实际申报以税务机关核定为准。")
    path.write_text(html, "utf-8")

    return GeneratedReport(filename=filename, path=str(path), report_type="tax_report")


def generate_voucher_print(voucher: dict) -> GeneratedReport:
    """生成记账凭证打印版"""
    entries = voucher.get("entries", [])
    if isinstance(entries, str):
        entries = json.loads(entries)

    sections = [
        {"heading": "基本信息", "type": "kv", "pairs": [
            ("凭证编号", voucher.get("voucher_no", "")),
            ("日期", voucher.get("voucher_date", "")),
            ("摘要", voucher.get("summary", "")),
            ("制单人", voucher.get("maker", "")),
            ("审核人", voucher.get("reviewer", "")),
            ("记账人", voucher.get("bookkeeper", "")),
            ("状态", voucher.get("status", "")),
        ]},
        {"heading": "会计分录", "type": "entries", "entries": entries},
    ]

    # 合计行
    total_debit = sum(e.get("debit", 0) or 0 for e in entries)
    total_credit = sum(e.get("credit", 0) or 0 for e in entries)

    title = f"记账凭证 — {voucher.get('voucher_no', '')}"

    report_id = uuid.uuid4().hex[:10]
    filename = f"voucher_{report_id}.html"
    path = REPORT_DIR / filename

    # 手动构建含合计行的表格
    entries_html = _html_entries(entries)
    summary_html = f"""
    <tr class="total-row">
      <td colspan="3" style="text-align:right"><strong>合计</strong></td>
      <td class="amount"><strong>¥{total_debit:,.2f}</strong></td>
      <td class="amount"><strong>¥{total_credit:,.2f}</strong></td>
    </tr>
    """

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>{title}</title>
<style>
  @page {{ size: A4; margin: 15mm; }}
  body {{ font-family: 'SimSun', serif; max-width: 210mm; margin: auto; padding: 10mm; }}
  h1 {{ text-align: center; font-size: 20px; margin-bottom: 3px; }}
  .subtitle {{ text-align: center; font-size: 11px; color: #888; margin-bottom: 20px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 12px; }}
  th {{ background: #333; color: #fff; padding: 6px 8px; }}
  td {{ padding: 5px 8px; border: 1px solid #ccc; }}
  .amount {{ text-align: right; }}
  .total-row td {{ background: #f0f0f0; font-weight: bold; }}
  .kv-table td:first-child {{ background: #f5f5f5; width: 100px; }}
  .signatures {{ display: flex; justify-content: space-between; margin-top: 40px; }}
  .sig-item {{ width: 30%; text-align: center; border-top: 1px solid #333; padding-top: 5px; }}
  @media print {{ body {{ padding: 0; }} }}
</style></head>
<body>
<h1>记 账 凭 证</h1>
<div class="subtitle">凭证编号：{voucher.get('voucher_no', '')} &nbsp;|&nbsp; 日期：{voucher.get('voucher_date', '')}</div>
<h3>摘要：{voucher.get('summary', '')}</h3>
<table>
  <thead><tr><th>科目编码</th><th>科目名称</th><th>摘要</th><th>借方金额</th><th>贷方金额</th></tr></thead>
  <tbody>{entries_html}{summary_html}</tbody>
</table>
<div class="signatures">
  <div class="sig-item">制单：{voucher.get('maker', '')}</div>
  <div class="sig-item">审核：{voucher.get('reviewer', '')}</div>
  <div class="sig-item">记账：{voucher.get('bookkeeper', '')}</div>
</div>
<div style="text-align:center;margin-top:20px;font-size:11px;color:#999">智能财税系统 — QR追溯码：{voucher.get('qr_code_path', '')}</div>
</body></html>"""

    path.write_text(html, "utf-8")
    return GeneratedReport(filename=filename, path=str(path), report_type="voucher")


def generate_monthly_report(client_name: str, month: str,
                            summary: dict) -> GeneratedReport:
    """生成月度财务报告"""
    sections = [{
        "heading": "月度财务摘要",
        "type": "kv",
        "pairs": [
            ("报告期间", month),
            ("客户名称", client_name),
            ("营业收入", f"¥{summary.get('revenue', 0):,.2f}"),
            ("利润总额", f"¥{summary.get('profit', 0):,.2f}"),
            ("纳税总额", f"¥{summary.get('tax_total', 0):,.2f}"),
            ("凭证数量", f"{summary.get('voucher_count', 0)} 张"),
            ("资产总额", f"¥{summary.get('assets', 0):,.2f}"),
            ("负债总额", f"¥{summary.get('liabilities', 0):,.2f}"),
        ],
    }]

    title = f"{client_name} — {month} 月度财务报告"

    report_id = uuid.uuid4().hex[:10]
    filename = f"monthly_report_{report_id}.html"
    path = REPORT_DIR / filename

    html = _generate_html_report(title, sections,
                                  footer="本报告由智能财税系统自动生成 | 仅供内部管理使用")
    path.write_text(html, "utf-8")

    return GeneratedReport(filename=filename, path=str(path), report_type="monthly_report")
