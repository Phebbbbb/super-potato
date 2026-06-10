"""订阅管理 + 人员使用状态 API"""
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.user import User
from app.services.auth import get_current_user, require_admin
from app.services.subscription_service import (
    create_trial, upgrade_to_vip, renew_subscription,
    check_subscription_valid, get_client_subscription, list_all_subscriptions,
    record_login, get_staff_usage_status, get_staff_login_history,
)

router = APIRouter()


# ================================================================
# 客户订阅管理
# ================================================================

@router.get("/subscriptions")
def list_subscriptions(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """列出所有客户订阅状态"""
    return {"subscriptions": list_all_subscriptions(db)}


@router.get("/subscriptions/{client_id}")
def client_subscription(client_id: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    """获取单个客户的订阅详情"""
    sub = get_client_subscription(db, client_id)
    if not sub:
        return {"client_id": client_id, "tier": "none", "tier_label": "未开通", "status": "none"}
    return sub


@router.post("/subscriptions/{client_id}/trial")
def start_trial(client_id: str, phone: str = Query(...), db: Session = Depends(get_db), _=Depends(get_current_user)):
    """开通半年试用"""
    sub = create_trial(db, client_id, phone)
    db.commit()
    return {"subscription_id": sub.id, "tier": "trial", "end_date": sub.end_date.isoformat()[:10]}


@router.post("/subscriptions/{client_id}/upgrade")
def upgrade(client_id: str, phone: str = Query(...),
            db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """升级为 VIP 年费会员"""
    sub = upgrade_to_vip(db, client_id, phone, operator=user.display_name or user.username)
    db.commit()
    return {"subscription_id": sub.id, "tier": "vip", "end_date": sub.end_date.isoformat()[:10]}


@router.post("/subscriptions/{subscription_id}/renew")
def renew(subscription_id: str, db: Session = Depends(get_db),
          user: User = Depends(get_current_user)):
    """续费订阅"""
    sub = renew_subscription(db, subscription_id, operator=user.display_name or user.username)
    if not sub:
        return {"error": "订阅不存在"}
    db.commit()
    return {"subscription_id": sub.id, "tier": sub.tier, "end_date": sub.end_date.isoformat()[:10]}


# ================================================================
# 服务端人员使用状态
# ================================================================

@router.get("/staff/usage")
def staff_usage(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """所有服务端人员使用状态"""
    return {"staff": get_staff_usage_status(db)}


@router.get("/staff/login-history")
def staff_login_history(user_id: str = Query(None), limit: int = Query(50), db: Session = Depends(get_db), _=Depends(get_current_user)):
    """服务端人员登录历史"""
    return {"history": get_staff_login_history(db, user_id, limit)}


@router.post("/staff/login-record")
def log_staff_login(request: Request, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """记录当前用户登录（供前端登录后调用）"""
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")
    h = record_login(db, user, ip=ip, ua=ua, login_type="password")
    db.commit()
    return {"recorded": True}
