import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.account import ChartOfAccount
from app.services.auth import require_modify, require_admin, get_current_user
from app.models.user import User
from app.services.version_control import commit
from app.services.cache import cache_get, cache_set, cache_invalidate
from app.schemas.core import AccountCreate

router = APIRouter()


@router.post("/")
def create_account(data: AccountCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user), _=Depends(require_admin)):
    """新增会计科目"""
    existing = db.query(ChartOfAccount).filter(ChartOfAccount.code == data.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="科目编码已存在")
    account = ChartOfAccount(
        id=str(uuid.uuid4()),
        code=data.code,
        name=data.name,
        category=data.category,
        parent_code=data.parent_code,
        direction=data.direction,
        is_active=data.is_active,
    )
    db.add(account)
    commit(db, "account", account.id, "created", user.display_name or "",
           after={"code": account.code, "name": account.name, "category": account.category})
    db.commit()
    cache_invalidate("accounts:*")
    return {"message": "科目创建成功", "code": account.code}


@router.get("/")
def list_accounts(category: str = None, is_active: bool = True, db: Session = Depends(get_db)):
    """会计科目列表"""
    cache_key = f"accounts:list:{category}:{is_active}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    q = db.query(ChartOfAccount)
    if category:
        q = q.filter(ChartOfAccount.category == category)
    if is_active:
        q = q.filter(ChartOfAccount.is_active == True)

    accounts = q.order_by(ChartOfAccount.code).all()
    result = {
        "items": [
            {
                "id": a.id,
                "code": a.code,
                "name": a.name,
                "category": a.category,
                "parent_code": a.parent_code,
                "direction": a.direction,
            }
            for a in accounts
        ],
        "total": len(accounts),
    }
    cache_set(cache_key, result, ttl=300)
    return result


@router.get("/tree")
def get_account_tree(db: Session = Depends(get_db)):
    """会计科目树形结构"""
    cache_key = "accounts:tree"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    accounts = db.query(ChartOfAccount).filter(ChartOfAccount.is_active == True).order_by(ChartOfAccount.code).all()

    nodes = {}
    roots = []
    for a in accounts:
        node = {
            "id": a.id,
            "code": a.code,
            "name": a.name,
            "category": a.category,
            "direction": a.direction,
            "children": [],
        }
        nodes[a.code] = node

        if a.parent_code and a.parent_code in nodes:
            nodes[a.parent_code]["children"].append(node)
        else:
            roots.append(node)

    result = {
        "items": roots,
        "total": len(accounts),
    }
    cache_set(cache_key, result, ttl=600)
    return result


@router.get("/{account_id}")
def get_account(account_id: str, db: Session = Depends(get_db)):
    """会计科目详情"""
    a = db.query(ChartOfAccount).filter(ChartOfAccount.id == account_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="科目不存在")
    return {
        "id": a.id,
        "code": a.code,
        "name": a.name,
        "category": a.category,
        "parent_code": a.parent_code,
        "direction": a.direction,
        "is_active": a.is_active,
    }
