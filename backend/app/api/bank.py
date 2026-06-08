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
    line.match_status = "manual_matched"
    line.matched_voucher_id = data.get("voucher_id", "")
    line.match_confidence = 1.0
    db.commit()
    return {"message": "手动匹配成功"}


@router.post("/unmatch/{statement_id}")
def unmatch(statement_id: str, db: Session = Depends(get_db), _=Depends(require_modify)):
    line = db.query(BankStatementLine).filter(BankStatementLine.id == statement_id).first()
    if not line: raise HTTPException(404, "流水不存在")
    line.match_status = "unmatched"
    line.matched_voucher_id = None
    line.match_confidence = 0
    db.commit()
    return {"message": "已取消匹配"}


@router.get("/reconciliation/{bank_account_id}")
def reconciliation(bank_account_id: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return get_reconciliation_summary(db, bank_account_id)
