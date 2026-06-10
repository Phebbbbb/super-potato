"""订阅服务 — 试用/VIP 管理 + 权限校验"""
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.models.subscription import ClientSubscription, LoginHistory
from app.models.user import User
from app.models.client import Client

TRIAL_MONTHS = 6
VIP_MONTHS = 12


# ================================================================
# 订阅生命周期
# ================================================================

def create_trial(db: Session, client_id: str, phone: str) -> ClientSubscription:
    """为新客户创建半年试用"""
    now = datetime.now(timezone.utc)
    now_naive = now.replace(tzinfo=None)

    # 检查是否已有有效订阅
    existing = db.query(ClientSubscription).filter(
        ClientSubscription.client_id == client_id,
        ClientSubscription.phone == phone,
        ClientSubscription.status == "active",
    ).first()
    if existing:
        return existing

    sub = ClientSubscription(
        id=uuid.uuid4().hex,
        client_id=client_id,
        phone=phone,
        tier="trial",
        status="active",
        start_date=now_naive,
        end_date=now_naive + timedelta(days=TRIAL_MONTHS * 30),
        created_by="system",
    )
    db.add(sub)
    db.flush()
    return sub


def upgrade_to_vip(db: Session, client_id: str, phone: str, operator: str = "admin") -> ClientSubscription:
    """升级为 VIP 年费会员（从当前日期起 1 年）"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # 停用旧订阅
    db.query(ClientSubscription).filter(
        ClientSubscription.client_id == client_id,
        ClientSubscription.phone == phone,
        ClientSubscription.status == "active",
    ).update({"status": "cancelled"})

    sub = ClientSubscription(
        id=uuid.uuid4().hex,
        client_id=client_id,
        phone=phone,
        tier="vip",
        status="active",
        start_date=now,
        end_date=now + timedelta(days=VIP_MONTHS * 30),
        created_by=operator,
    )
    db.add(sub)
    db.flush()
    return sub


def renew_subscription(db: Session, subscription_id: str, operator: str = "admin") -> ClientSubscription | None:
    """续费（按当前 tier 续期）"""
    sub = db.query(ClientSubscription).filter(ClientSubscription.id == subscription_id).first()
    if not sub:
        return None

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    months = VIP_MONTHS if sub.tier == "vip" else TRIAL_MONTHS

    sub.status = "active"
    sub.start_date = now
    sub.end_date = now + timedelta(days=months * 30)
    sub.auto_renew = True
    sub.updated_at = now
    db.flush()
    return sub


def check_subscription_valid(db: Session, client_id: str, phone: str) -> dict:
    """
    校验订阅是否有效

    Returns:
        {"valid": True/False, "tier": "trial"/"vip", "days_left": N, "reason": "..."}
    """
    sub = db.query(ClientSubscription).filter(
        ClientSubscription.client_id == client_id,
        ClientSubscription.phone == phone,
        ClientSubscription.status == "active",
    ).order_by(ClientSubscription.end_date.desc()).first()

    if not sub:
        return {"valid": False, "tier": None, "days_left": 0, "reason": "无有效订阅，请先开通"}

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    days_left = (sub.end_date - now).days

    if days_left <= 0:
        sub.status = "expired"
        db.flush()
        return {"valid": False, "tier": sub.tier, "days_left": 0, "reason": "订阅已过期，请续费"}

    return {"valid": True, "tier": sub.tier, "days_left": max(days_left, 0),
            "end_date": sub.end_date.isoformat()[:10], "subscription_id": sub.id}


def get_client_subscription(db: Session, client_id: str) -> dict | None:
    """获取客户当前订阅信息"""
    sub = db.query(ClientSubscription).filter(
        ClientSubscription.client_id == client_id,
        ClientSubscription.status == "active",
    ).order_by(ClientSubscription.end_date.desc()).first()

    if not sub:
        # 查最近一条（可能已过期）
        sub = db.query(ClientSubscription).filter(
            ClientSubscription.client_id == client_id,
        ).order_by(ClientSubscription.end_date.desc()).first()

    if not sub:
        return None

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    days_left = max(0, (sub.end_date - now).days) if sub.status == "active" else 0

    return {
        "subscription_id": sub.id,
        "client_id": sub.client_id,
        "phone": sub.phone,
        "tier": sub.tier,
        "tier_label": "VIP 年费会员" if sub.tier == "vip" else "半年试用",
        "status": sub.status,
        "start_date": sub.start_date.isoformat()[:10] if sub.start_date else "",
        "end_date": sub.end_date.isoformat()[:10] if sub.end_date else "",
        "days_left": days_left,
        "auto_renew": sub.auto_renew,
    }


def list_all_subscriptions(db: Session) -> list[dict]:
    """列出所有客户订阅"""
    from app.models.client import Client

    clients = db.query(Client).filter(Client.is_active == True).all()
    results = []
    for c in clients:
        info = get_client_subscription(db, c.id)
        if info:
            info["client_name"] = c.name
        else:
            info = {
                "client_id": c.id, "client_name": c.name,
                "phone": c.contact_phone or "", "tier": "none",
                "tier_label": "未开通", "status": "none",
                "days_left": 0, "start_date": "", "end_date": "",
            }
        results.append(info)
    return results


# ================================================================
# 登录历史 — 服务端人员使用状态
# ================================================================

def record_login(db: Session, user: User, ip: str = "", ua: str = "", login_type: str = "password") -> LoginHistory:
    """记录登录"""
    h = LoginHistory(
        id=uuid.uuid4().hex,
        user_id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        ip_address=ip,
        user_agent=ua,
        login_type=login_type,
    )
    db.add(h)
    db.flush()
    return h


def get_staff_usage_status(db: Session) -> list[dict]:
    """
    获取所有服务端人员的使用状态

    Returns:
        [{user_id, username, display_name, role, is_active,
          last_login_at, login_count_30d, account_created_at}]
    """
    from sqlalchemy import func as sqla_func

    users = db.query(User).filter(User.role != "client").all()

    thirty_days_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)

    results = []
    for u in users:
        # 最近一次登录
        last_login = db.query(LoginHistory).filter(
            LoginHistory.user_id == u.id,
        ).order_by(LoginHistory.login_at.desc()).first()

        # 30天内登录次数
        login_count = db.query(sqla_func.count(LoginHistory.id)).filter(
            LoginHistory.user_id == u.id,
            LoginHistory.login_at >= thirty_days_ago,
        ).scalar() or 0

        results.append({
            "user_id": u.id,
            "username": u.username,
            "display_name": u.display_name,
            "role": u.role,
            "phone": u.phone,
            "is_active": u.is_active,
            "account_locked": bool(u.locked_until and u.locked_until > datetime.now(timezone.utc)),
            "last_login_at": last_login.login_at.isoformat() if last_login else None,
            "last_login_ip": last_login.ip_address if last_login else None,
            "login_count_30d": login_count,
            "failed_attempts": u.failed_login_attempts,
            "created_at": u.created_at.isoformat() if u.created_at else "",
        })

    # 按最近登录时间排序（最近在前）
    results.sort(key=lambda r: r.get("last_login_at") or "", reverse=True)
    return results


def get_staff_login_history(db: Session, user_id: str = None, limit: int = 50) -> list[dict]:
    """获取服务端人员登录历史"""
    q = db.query(LoginHistory).filter(LoginHistory.login_type == "password")
    if user_id:
        q = q.filter(LoginHistory.user_id == user_id)
    q = q.order_by(LoginHistory.login_at.desc()).limit(limit)

    return [{
        "id": h.id,
        "user_id": h.user_id,
        "username": h.username,
        "display_name": h.display_name,
        "role": h.role,
        "login_at": h.login_at.isoformat() if h.login_at else "",
        "ip_address": h.ip_address,
    } for h in q.all()]
