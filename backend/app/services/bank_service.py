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
    """自动匹配银行流水与记账凭证 — 金额桶索引 + 多维度综合匹配"""
    from datetime import timedelta

    unmatched = db.query(BankStatementLine).filter(
        BankStatementLine.bank_account_id == bank_account_id,
        BankStatementLine.match_status == "unmatched",
    ).all()

    vouchers = db.query(AccountingVoucher).filter(
        AccountingVoucher.status == "confirmed",
    ).all()

    # 构建金额桶索引 — 按 nearest-100-yuan 分桶，将 O(V*E) 降为 O(V/E)
    # 对每条银行流水只需检查同桶及邻桶的条目
    amt_index: dict[int, list[tuple]] = {}  # bucket -> [(voucher_id, entry_amt, entry, voucher)]
    bucket_size = 100  # 100元一桶

    for v in vouchers:
        entries = json.loads(v.entries) if isinstance(v.entries, str) else (v.entries or [])
        for e in entries:
            if e.get("account_code") not in ("1002", "1001"):
                continue
            entry_amt = float(e.get("debit", 0) or 0) or float(e.get("credit", 0) or 0)
            if entry_amt == 0:
                continue
            bucket = int(entry_amt / bucket_size)
            amt_index.setdefault(bucket, []).append((v.id, entry_amt, e, v))

    matched = 0
    for line in unmatched:
        line_amount = line.debit if line.debit > 0 else line.credit
        if line_amount <= 0:
            continue
        best_match = None
        best_score = 0.0

        # 仅检查同桶和相邻桶（±1）的候选条目
        line_bucket = int(line_amount / bucket_size)
        candidates = []
        for b in (line_bucket - 1, line_bucket, line_bucket + 1):
            candidates.extend(amt_index.get(b, []))

        for voucher_id, entry_amt, e, v in candidates:
            score = 0.0

            # 1. 金额匹配（0-100分）
            amt_diff_pct = abs(entry_amt - line_amount) / max(line_amount, 1)
            if amt_diff_pct < 0.01:
                score += 100 - amt_diff_pct * 10
            elif amt_diff_pct < 0.05:
                score += 50 - amt_diff_pct * 10
            else:
                continue

            # 2. 日期匹配（0-20分）
            try:
                line_date = line.transaction_date
                if isinstance(line_date, str):
                    from datetime import date as dt_date
                    line_date = dt_date.fromisoformat(line_date)
                if hasattr(v, 'voucher_date') and v.voucher_date:
                    days_diff = abs((line_date - v.voucher_date).days)
                    if days_diff <= 1:
                        score += 20
                    elif days_diff <= 3:
                        score += 15
                    elif days_diff <= 7:
                        score += 5
            except Exception:
                pass

            # 3. 对方户名匹配（0-15分）
            counterparty = (line.counterparty or "").strip()
            if counterparty and len(counterparty) >= 2:
                entry_summary = str(e.get("summary", ""))
                voucher_summary = str(getattr(v, 'summary', '') or '')
                combined = entry_summary + voucher_summary
                if counterparty in combined:
                    score += 15
                elif any(c in combined for c in counterparty[:2]):
                    score += 5

            # 4. 摘要关键词匹配（0-10分）
            line_desc = (line.description or "").lower()
            entry_summary = str(e.get("summary", "")).lower()
            voucher_summary = str(getattr(v, 'summary', '') or '').lower()
            combined_text = entry_summary + " " + voucher_summary
            common_keywords = ["货款", "服务费", "工资", "租金", "水电", "税金", "社保", "报销"]
            keyword_hits = sum(1 for kw in common_keywords if kw in line_desc and kw in combined_text)
            score += min(keyword_hits * 5, 10)

            if score > best_score:
                best_score = score
                best_match = (voucher_id, entry_amt)

        if best_match and best_score >= 70:
            line.match_status = "auto_matched"
            line.matched_voucher_id = best_match[0]
            line.match_confidence = round(min(best_score / 100, 1.0), 2)
            matched += 1

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
