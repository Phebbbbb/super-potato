"""服务端-客户端交互消息服务

架构：
  客户端 ←→ 爻管家（总管理员，人工客服中心）
  客户端 ←→ 爻工（服务端员工，按客户分配可见）
  客户端 — 仅与一人对话，看到的是一条统一的消息流
  服务端 — 每个员工可见自己管辖客户的对话
"""
import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.notification import Notification
from app.models.user import User, UserClientAssignment
from app.models.client import Client
from app.models.subscription import ClientSubscription


def send_message_to_client(
    db: Session,
    client_id: str,
    title: str,
    message: str,
    link: str = None,
    sender_id: str = None,
    sender_name: str = None,
) -> dict:
    """服务端人员（爻管家/爻工）向客户端发送消息"""
    # 查找该客户绑定的客户端用户
    sub = db.query(ClientSubscription).filter(
        ClientSubscription.client_id == client_id,
        ClientSubscription.status == "active",
    ).first()

    user_id = None
    client_name = None
    if sub and sub.phone:
        user = db.query(User).filter(
            User.phone == sub.phone,
            User.role == "client",
        ).first()
        if user:
            user_id = user.id

    # 获取客户名称
    client = db.query(Client).filter(Client.id == client_id).first()
    if client:
        client_name = client.name

    # 确定发送者显示名称
    from app.models.user import User as UserModel
    display_sender_name = sender_name or "爻管家"
    if sender_id:
        sender_user = db.query(UserModel).filter(UserModel.id == sender_id).first()
        if sender_user:
            display_sender_name = sender_user.display_name or sender_user.username

    n = Notification(
        id=uuid.uuid4().hex,
        type="interaction",
        title=title,
        message=message,
        user_id=user_id,
        link=link,
        sender_id=sender_id,
        sender_name=display_sender_name,
        client_id=client_id,
    )
    db.add(n)
    db.flush()

    return {
        "id": n.id,
        "client_id": client_id,
        "client_name": client_name,
        "user_id": user_id,
        "title": title,
        "message": message,
        "sender_name": display_sender_name,
        "delivered": user_id is not None,
    }


def send_feedback_to_service(
    db: Session,
    user_id: str,
    title: str,
    message: str,
) -> dict:
    """客户端向服务端发送反馈/咨询消息"""
    # 查找该客户端用户关联的客户
    user = db.query(User).filter(User.id == user_id).first()
    client_id = None
    sender_name = user.display_name if user else "客户"
    if user:
        assign = db.query(UserClientAssignment).filter(
            UserClientAssignment.user_id == user_id
        ).first()
        if assign:
            client_id = assign.client_id

    n = Notification(
        id=uuid.uuid4().hex,
        type="feedback",
        title=title,
        message=message,
        user_id=None,  # 全局可见，所有服务端人员都能看到
        sender_id=user_id,
        sender_name=sender_name,
        client_id=client_id,
        link="/interactions",
    )
    db.add(n)
    db.flush()

    return {
        "id": n.id,
        "title": title,
        "message": message,
        "sender_name": sender_name,
        "client_id": client_id,
    }


def get_client_messages(db: Session, user_id: str = None, limit: int = 30) -> list:
    """客户端获取消息列表（含爻管家/爻工的回复）"""
    q = db.query(Notification).filter(
        Notification.type.in_(["interaction", "feedback", "deadline", "rpa"])
    )
    if user_id:
        q = q.filter(
            (Notification.user_id == user_id) | (Notification.sender_id == user_id)
        )
    items = q.order_by(Notification.created_at.desc()).limit(limit).all()
    return [
        {
            "id": n.id,
            "type": n.type,
            "title": n.title,
            "message": n.message,
            "is_read": n.is_read,
            "link": n.link,
            "sender_name": n.sender_name,
            "sender_id": n.sender_id,
            "client_id": n.client_id,
            "direction": "out" if (n.sender_id == user_id or n.type == "feedback") else "in",
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in items
    ]


def get_service_messages(db: Session, user_id: str = None, limit: int = 50) -> list:
    """服务端获取交互消息（含发件人身份）

    若 user_id 为普通员工，仅返回其管辖客户的对话；
    若 user_id 为 admin/super_admin，返回全部对话。
    """
    q = db.query(Notification).filter(
        Notification.type.in_(["feedback", "interaction"])
    )
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
        if user and user.role not in ("admin", "super_admin"):
            # 普通员工只能看到自己管辖的客户消息
            my_client_ids = [
                a.client_id for a in
                db.query(UserClientAssignment.client_id).filter(
                    UserClientAssignment.user_id == user_id
                ).all()
            ]
            if my_client_ids:
                q = q.filter(
                    (Notification.client_id.in_(my_client_ids)) |
                    (Notification.client_id.is_(None))
                )
            else:
                # 没有分配客户，只显示全局消息
                q = q.filter(Notification.client_id.is_(None))
    items = (
        q.order_by(Notification.created_at.desc())
        .limit(limit)
        .all()
    )
    # 批量获取客户名称
    client_ids = [n.client_id for n in items if n.client_id]
    client_name_map = {}
    if client_ids:
        from app.models.client import Client as ClientModel
        clients = db.query(ClientModel).filter(ClientModel.id.in_(client_ids)).all()
        client_name_map = {c.id: c.name for c in clients}
    return [
        {
            "id": n.id,
            "type": n.type,
            "title": n.title,
            "message": n.message,
            "is_read": n.is_read,
            "user_id": n.user_id,
            "sender_id": n.sender_id,
            "sender_name": n.sender_name,
            "client_id": n.client_id,
            "client_name": client_name_map.get(n.client_id) if n.client_id else None,
            "direction": "out" if n.type == "interaction" else "in",
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in items
    ]
