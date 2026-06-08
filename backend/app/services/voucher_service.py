"""记账凭证服务：科目规则匹配、借贷平衡校验、凭证编号生成"""
import json
import re
from datetime import date
from sqlalchemy.orm import Session
from app.models.account import ChartOfAccount
from app.models.voucher import AccountingVoucher

# ===== 科目匹配规则引擎 =====
# 基于发票内容关键词自动匹配最可能的会计科目

INVOICE_KEYWORD_RULES = [
    # (关键词, 科目编码, 科目名称, 方向)
    ("技术服务费", "660209", "管理费用-咨询服务费", "debit"),
    ("咨询费", "660209", "管理费用-咨询服务费", "debit"),
    ("软件", "660201", "管理费用-办公费", "debit"),
    ("办公用品", "660201", "管理费用-办公费", "debit"),
    ("差旅", "660202", "管理费用-差旅费", "debit"),
    ("住宿", "660202", "管理费用-差旅费", "debit"),
    ("餐饮", "660203", "管理费用-业务招待费", "debit"),
    ("招待", "660203", "管理费用-业务招待费", "debit"),
    ("房租", "660210", "管理费用-租赁费", "debit"),
    ("租赁", "660210", "管理费用-租赁费", "debit"),
    ("物业", "660211", "管理费用-物业费", "debit"),
    ("水电", "660212", "管理费用-水电费", "debit"),
    ("电费", "660212", "管理费用-水电费", "debit"),
    ("交通", "660205", "管理费用-交通费", "debit"),
    ("通讯", "660204", "管理费用-通讯费", "debit"),
    ("运输", "6601", "销售费用", "debit"),
    ("广告", "6601", "销售费用", "debit"),
    ("利息", "660301", "财务费用-利息费用", "debit"),
    ("手续费", "660302", "财务费用-手续费", "debit"),
    ("设备", "1601", "固定资产", "debit"),
    ("电脑", "1601", "固定资产", "debit"),
    ("服务器", "1601", "固定资产", "debit"),
    ("维修", "660201", "管理费用-办公费", "debit"),
    ("原材料", "1403", "原材料", "debit"),
    ("库存", "1405", "库存商品", "debit"),
    ("商标", "1701", "无形资产", "debit"),
    ("专利", "1701", "无形资产", "debit"),
]


def match_account_by_keyword(item_name: str, summary: str = "") -> tuple[str, str, str]:
    """基于关键词匹配会计科目，返回 (科目编码, 科目名称, 方向)"""
    search_text = f"{item_name} {summary}"

    for keyword, code, name, direction in INVOICE_KEYWORD_RULES:
        if keyword in search_text:
            return code, name, direction

    # 默认：管理费用-其他
    return "6602", "管理费用", "debit"


def generate_voucher_no(db: Session, voucher_date: date) -> str:
    """自动生成凭证编号: JZ-YYYYMM-NNNN"""
    period = voucher_date.strftime("%Y%m")
    # 查询当前期间已有凭证数量
    count = (
        db.query(AccountingVoucher)
        .filter(AccountingVoucher.voucher_no.like(f"JZ-{period}-%"))
        .count()
    )
    return f"JZ-{period}-{count + 1:04d}"


def validate_balance(entries: list[dict]) -> tuple[bool, float, float]:
    """校验借贷平衡"""
    total_debit = sum(e.get("debit", 0) or 0 for e in entries)
    total_credit = sum(e.get("credit", 0) or 0 for e in entries)
    balanced = abs(total_debit - total_credit) < 0.01 and total_debit > 0
    return balanced, total_debit, total_credit


def get_account_map(db: Session) -> dict[str, dict]:
    """获取所有科目映射 {code: {name, category, direction}}"""
    accounts = db.query(ChartOfAccount).filter(ChartOfAccount.is_active == True).all()
    return {
        a.code: {"name": a.name, "category": a.category, "direction": a.direction}
        for a in accounts
    }


def build_entries_from_documents(
    db: Session,
    documents: list[dict],
    summary: str = "",
) -> list[dict]:
    """
    从原始凭证数据自动构建借贷分录
    核心逻辑：发票金额 → 自动匹配科目 → 生成借贷分录
    """
    entries = []
    account_map = get_account_map(db)

    for doc in documents:
        ocr = doc.get("ocr_structured") or {}
        doc_type = doc.get("doc_type", "invoice")

        # 无 OCR 数据的票据，基于文件信息生成占位分录
        if not ocr:
            file_name = doc.get("file_name", "unknown")
            entries.append({
                "account_code": "660299" if doc_type == "invoice" else "660399",
                "account_name": "管理费用" if doc_type == "invoice" else "其他费用",
                "debit": 100.00,
                "credit": 0,
                "summary": f"自动处理: {file_name}（OCR待完善）",
            })
            entries.append({
                "account_code": "100201",
                "account_name": "银行存款",
                "debit": 0,
                "credit": 100.00,
                "summary": f"自动处理: {file_name}",
            })
            continue

        total = ocr.get("total_amount") or 0
        excluding_tax = ocr.get("amount_excluding_tax") or total
        tax_amount = ocr.get("tax_amount") or 0

        items = ocr.get("items", [])

        if doc_type == "invoice":
            # === 进项发票处理 ===
            # 借方：根据发票内容匹配费用/资产科目
            if items:
                for item in items:
                    item_name = item.get("name", "")
                    item_amount = item.get("amount") or item.get("unit_price", 0) * item.get("quantity", 1)
                    code, name, direction = match_account_by_keyword(item_name, summary)
                    entries.append({
                        "account_code": code,
                        "account_name": name,
                        "debit": round(item_amount, 2),
                        "credit": 0,
                        "summary": item_name,
                    })
            else:
                code, name, direction = match_account_by_keyword(summary or "其他", summary)
                entries.append({
                    "account_code": code,
                    "account_name": name,
                    "debit": round(excluding_tax, 2),
                    "credit": 0,
                    "summary": summary or "采购",
                })

            # 应交税费-应交增值税（进项税额）
            if tax_amount > 0:
                entries.append({
                    "account_code": "222101",
                    "account_name": "应交增值税",
                    "debit": round(tax_amount, 2),
                    "credit": 0,
                    "summary": "进项税额",
                })

            # 贷方：银行存款/应付账款
            entries.append({
                "account_code": "1002",
                "account_name": "银行存款",
                "debit": 0,
                "credit": round(total, 2),
                "summary": "支付货款",
            })

        elif doc_type == "bank_receipt" or doc_type == "receipt":
            # === 银行回单 / 收据 ===
            # 根据场景灵活处理
            if "收入" in summary or "收款" in summary:
                entries.append({
                    "account_code": "1002",
                    "account_name": "银行存款",
                    "debit": round(total, 2),
                    "credit": 0,
                    "summary": summary or "收到款项",
                })
                entries.append({
                    "account_code": "6001",
                    "account_name": "主营业务收入",
                    "debit": 0,
                    "credit": round(excluding_tax, 2),
                    "summary": summary or "收入",
                })
                if tax_amount > 0:
                    entries.append({
                        "account_code": "222101",
                        "account_name": "应交增值税",
                        "debit": 0,
                        "credit": round(tax_amount, 2),
                        "summary": "销项税额",
                    })

    # 合并相同科目的分录
    merged = {}
    for e in entries:
        key = e["account_code"]
        if key in merged:
            merged[key]["debit"] += e["debit"]
            merged[key]["credit"] += e["credit"]
        else:
            merged[key] = dict(e)

    return [v for v in merged.values()]
