"""银行对账服务"""
import json, uuid
from datetime import datetime, date
from sqlalchemy.orm import Session
from app.models.bank import BankAccount, BankStatementLine, ImportBatch
from app.models.voucher import AccountingVoucher


def _safe_float(val) -> float:
    """安全转换为 float，无效值返回 0"""
    if val is None or val == "":
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def parse_statement_excel(file_content: bytes, file_name: str) -> list[dict]:
    """解析银行流水 Excel/CSV（简化版：假设 CSV 格式）"""
    import csv, io
    lines = []
    reader = csv.DictReader(io.StringIO(file_content.decode("utf-8-sig")))
    for row in reader:
        lines.append({
            "transaction_date": row.get("日期", row.get("date", "")),
            "description": row.get("摘要", row.get("description", "")),
            "debit": _safe_float(row.get("借方", row.get("debit", 0)) or 0),
            "credit": _safe_float(row.get("贷方", row.get("credit", 0)) or 0),
            "balance": _safe_float(row.get("余额", row.get("balance", 0)) or 0),
            "counterparty": row.get("对方户名", row.get("counterparty", "")),
        })
    return lines


def import_statement(db: Session, bank_account_id: str, client_id: str, lines: list[dict], file_name: str) -> dict:
    """导入银行流水"""
    batch = ImportBatch(
        id=uuid.uuid4().hex, bank_account_id=bank_account_id, client_id=client_id,
        file_name=file_name, line_count=len(lines),
    )
    db.add(batch)
    db.flush()

    total_debit = total_credit = 0.0
    for line in lines:
        total_debit += line.get("debit", 0)
        total_credit += line.get("credit", 0)
        stmt = BankStatementLine(
            id=uuid.uuid4().hex, bank_account_id=bank_account_id, client_id=client_id,
            transaction_date=line.get("transaction_date", date.today()),
            description=line.get("description", ""),
            debit=line.get("debit", 0), credit=line.get("credit", 0),
            balance=line.get("balance", 0), counterparty=line.get("counterparty", ""),
            import_batch_id=batch.id,
        )
        db.add(stmt)

    batch.total_debit = total_debit
    batch.total_credit = total_credit
    db.commit()
    return {"imported": len(lines), "batch_id": batch.id, "total_debit": total_debit, "total_credit": total_credit}


def auto_match(db: Session, bank_account_id: str) -> dict:
    """自动匹配银行流水与记账凭证"""
    unmatched = db.query(BankStatementLine).filter(
        BankStatementLine.bank_account_id == bank_account_id,
        BankStatementLine.match_status == "unmatched",
    ).all()

    vouchers = db.query(AccountingVoucher).filter(
        AccountingVoucher.status == "confirmed",
    ).all()

    matched = 0
    for line in unmatched:
        amount = line.debit if line.debit > 0 else line.credit
        for v in vouchers:
            entries = json.loads(v.entries) if isinstance(v.entries, str) else v.entries
            for e in entries:
                if e.get("account_code") in ("1002", "1001"):
                    entry_amt = e.get("debit", 0) or e.get("credit", 0)
                    if abs(float(entry_amt) - amount) < 0.02:
                        line.match_status = "auto_matched"
                        line.matched_voucher_id = v.id
                        line.match_confidence = 1.0
                        matched += 1
                        break
            if line.match_status == "auto_matched":
                break

    db.commit()
    return {"matched_count": matched, "total": len(unmatched)}


def get_reconciliation_summary(db: Session, bank_account_id: str) -> dict:
    """对账汇总"""
    all_lines = db.query(BankStatementLine).filter(
        BankStatementLine.bank_account_id == bank_account_id,
    ).all()
    matched = [l for l in all_lines if l.match_status in ("auto_matched", "manual_matched")]
    unmatched = [l for l in all_lines if l.match_status == "unmatched"]

    return {
        "total_lines": len(all_lines),
        "matched_count": len(matched),
        "matched_debit": sum(l.debit for l in matched),
        "matched_credit": sum(l.credit for l in matched),
        "unmatched_count": len(unmatched),
        "unmatched_debit": sum(l.debit for l in unmatched),
        "unmatched_credit": sum(l.credit for l in unmatched),
    }
