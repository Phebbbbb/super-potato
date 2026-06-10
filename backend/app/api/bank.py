"""银行对账 API"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.bank import BankAccount, BankStatementLine, ImportBatch
from app.services.bank_service import import_statement, auto_match, get_reconciliation_summary, parse_statement_excel
from app.services.auth import get_current_user, require_modify
from app.models.user import User
from app.services.version_control import commit
from app.schemas.core import BankAccountCreate

router = APIRouter()


@router.get("/accounts/")
def list_accounts(client_id: str = Query(None), db: Session = Depends(get_db), _=Depends(get_current_user)):
    q = db.query(BankAccount)
    if client_id: q = q.filter(BankAccount.client_id == client_id)
    items = q.all()
    return {"items": [{"id": a.id, "account_no": a.account_no, "bank_name": a.bank_name,
            "account_name": a.account_name, "currency": a.currency, "is_active": a.is_active} for a in items]}


@router.post("/accounts/")
def create_account(data: BankAccountCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user), _=Depends(require_modify)):
    a = BankAccount(id=uuid.uuid4().hex, client_id=data.client_id,
                    account_no=data.account_no, bank_name=data.bank_name,
                    account_name=data.account_name)
    db.add(a)
    commit(db, "bank_account", a.id, "created", user.display_name or "",
           after={"bank_name": a.bank_name, "account_no": a.account_no[-4:], "client_id": a.client_id})
    db.commit()
    return {"id": a.id, "message": "银行账户添加成功"}


@router.post("/import")
async def import_statement_file(file: UploadFile = File(...), bank_account_id: str = Query(...),
                                 client_id: str = Query(...), db: Session = Depends(get_db), _=Depends(require_modify)):
    content = await file.read()
    lines = parse_statement_excel(content, file.filename or "unknown")
    if not lines: raise HTTPException(400, "无法解析文件，请上传 CSV 格式（含日期/摘要/借方/贷方/余额列）")
    result = import_statement(db, bank_account_id, client_id, lines, file.filename or "unknown")
    return result


@router.get("/statements/")
def list_statements(bank_account_id: str = Query(None), match_status: str = Query(None),
                    page: int = Query(1), page_size: int = Query(200),
                    db: Session = Depends(get_db), _=Depends(get_current_user)):
    q = db.query(BankStatementLine)
    if bank_account_id: q = q.filter(BankStatementLine.bank_account_id == bank_account_id)
    if match_status: q = q.filter(BankStatementLine.match_status == match_status)
    total = q.count()
    items = q.order_by(BankStatementLine.transaction_date.desc()).offset((page-1)*page_size).limit(page_size).all()
    return {"items": [{"id": s.id, "transaction_date": str(s.transaction_date), "description": s.description,
            "debit": s.debit, "credit": s.credit, "balance": s.balance, "counterparty": s.counterparty,
            "match_status": s.match_status, "matched_voucher_id": s.matched_voucher_id,
            "match_confidence": s.match_confidence} for s in items], "total": total, "page": page, "page_size": page_size}


@router.post("/auto-match/{bank_account_id}")
def trigger_auto_match(bank_account_id: str, db: Session = Depends(get_db), _=Depends(require_modify)):
    result = auto_match(db, bank_account_id)
    return result


@router.post("/match/{statement_id}")
def manual_match(statement_id: str, data: dict, db: Session = Depends(get_db), _=Depends(require_modify)):
    line = db.query(BankStatementLine).filter(BankStatementLine.id == statement_id).first()
    if not line: raise HTTPException(404, "流水不存在")
    before = {"match_status": line.match_status, "matched_voucher_id": line.matched_voucher_id}
    line.match_status = "manual_matched"
    line.matched_voucher_id = data.get("voucher_id", "")
    line.match_confidence = 1.0
    commit(db, "bank_statement", statement_id, "updated", "manual",
           before=before, after={"match_status": "manual_matched", "matched_voucher_id": line.matched_voucher_id})
    db.commit()
    return {"message": "手动匹配成功"}


@router.post("/unmatch/{statement_id}")
def unmatch(statement_id: str, db: Session = Depends(get_db), _=Depends(require_modify)):
    line = db.query(BankStatementLine).filter(BankStatementLine.id == statement_id).first()
    if not line: raise HTTPException(404, "流水不存在")
    before = {"match_status": line.match_status, "matched_voucher_id": line.matched_voucher_id}
    line.match_status = "unmatched"
    line.matched_voucher_id = None
    line.match_confidence = 0
    commit(db, "bank_statement", statement_id, "updated", "manual",
           before=before, after={"match_status": "unmatched", "matched_voucher_id": None})
    db.commit()
    return {"message": "已取消匹配"}


@router.get("/reconciliation/{bank_account_id}")
def reconciliation(bank_account_id: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return get_reconciliation_summary(db, bank_account_id)


@router.post("/auto-generate-vouchers/{bank_account_id}")
def auto_generate_vouchers(
    bank_account_id: str,
    period: str = Query(..., description="期间 YYYY-MM"),
    db: Session = Depends(get_db),
    _=Depends(require_modify),
):
    """银行流水自动生成记账凭证 — 对未匹配的流水行，根据对方名称自动归集科目并生成凭证"""
    from app.models.bank import BankAccount
    from app.models.voucher import AccountingVoucher
    from app.services.voucher_service import generate_voucher_no, validate_balance
    from datetime import date as dt_date
    import json as _json

    account = db.query(BankAccount).filter(BankAccount.id == bank_account_id).first()
    if not account:
        raise HTTPException(404, "银行账户不存在")

    y, m = map(int, period.split("-"))
    lines = (
        db.query(BankStatementLine)
        .filter(
            BankStatementLine.bank_account_id == bank_account_id,
            BankStatementLine.match_status == "unmatched",
            BankStatementLine.transaction_date.like(f"{period}%"),
        )
        .all()
    )

    if not lines:
        return {"message": "没有未匹配的流水需处理", "vouchers_created": 0}

    # 对方名称 → 会计科目映射
    COUNTERPARTY_ACCOUNT_MAP = {
        "工资": ("2211", "应付职工薪酬"),
        "社保": ("2241", "应付社会保险费"),
        "公积金": ("2242", "应付住房公积金"),
        "税金": ("2221", "应交税费"),
        "房租": ("6602", "管理费用"),
        "物业": ("6602", "管理费用"),
        "水电": ("6602", "管理费用"),
        "办公": ("6602", "管理费用"),
        "采购": ("1403", "原材料"),
        "销售收入": ("6001", "主营业务收入"),
        "服务": ("6001", "主营业务收入"),
    }

    vouchers_created = 0
    for line in lines:
        counterparty = line.counterparty or line.description or ""
        # 自动匹配科目
        account_code = "1001"  # 默认现金
        account_name = "库存现金"
        for keyword, (code, name) in COUNTERPARTY_ACCOUNT_MAP.items():
            if keyword in counterparty:
                account_code, account_name = code, name
                break

        is_receipt = float(line.credit or 0) > 0
        amount = float(line.credit or 0) if is_receipt else float(line.debit or 0)

        entries = []
        if is_receipt:
            entries = [
                {"account_code": "1002", "account_name": "银行存款", "debit": round(amount, 2), "credit": 0, "summary": f"{counterparty} - {line.description or ''}"},
                {"account_code": account_code, "account_name": account_name, "debit": 0, "credit": round(amount, 2), "summary": f"银行流水自动归集"},
            ]
        else:
            entries = [
                {"account_code": account_code, "account_name": account_name, "debit": round(amount, 2), "credit": 0, "summary": f"{counterparty} - {line.description or ''}"},
                {"account_code": "1002", "account_name": "银行存款", "debit": 0, "credit": round(amount, 2), "summary": f"银行流水自动归集"},
            ]

        balanced, td, tc = validate_balance(entries)
        vno = generate_voucher_no(db, dt_date(y, m, 1))
        voucher = AccountingVoucher(
            id=str(uuid.uuid4()),
            voucher_no=vno,
            voucher_date=dt_date(y, m, 1),
            summary=f"银行流水自动生成 — {counterparty}",
            entries=_json.dumps(entries, ensure_ascii=False),
            total_debit=td,
            total_credit=tc,
            status="draft",
            created_by="auto_bank",
            client_id=account.client_id,
        )
        db.add(voucher)
        db.flush()

        line.match_status = "auto_matched"
        line.matched_voucher_id = voucher.id
        line.match_confidence = 0.9
        vouchers_created += 1

    db.commit()
    return {
        "message": f"银行流水自动生成 {vouchers_created} 张记账凭证",
        "vouchers_created": vouchers_created,
        "total_lines": len(lines),
    }
