"""系统通知服务 — 生成、查询、标记已读"""
import uuid
from sqlalchemy.orm import Session
from app.models.notification import Notification


def create_notification(
    db: Session,
    type: str,
    title: str,
    message: str = "",
    user_id: str = None,
    link: str = None,
) -> Notification:
    """创建一条系统通知"""
    n = Notification(
        id=uuid.uuid4().hex,
        type=type,
        title=title,
        message=message,
        user_id=user_id,
        link=link,
    )
    db.add(n)
    db.flush()
    return n


def create_bulk_notifications(db: Session, items: list[dict]) -> int:
    """批量创建通知，跳过重复（同title）"""
    count = 0
    for item in items:
        existing = db.query(Notification).filter(
            Notification.title == item["title"],
            Notification.type == item.get("type", "system"),
        ).first()
        if existing:
            continue
        n = Notification(
            id=uuid.uuid4().hex,
            type=item.get("type", "system"),
            title=item["title"],
            message=item.get("message", ""),
            user_id=item.get("user_id"),
            link=item.get("link"),
        )
        db.add(n)
        count += 1
    if count > 0:
        db.flush()
    return count


def get_unread_count(db: Session, user_id: str = None) -> int:
    """获取未读通知数量"""
    q = db.query(Notification).filter(Notification.is_read == False)
    return q.count()


def get_notifications(db: Session, user_id: str = None, limit: int = 20, unread_only: bool = False) -> list:
    """获取通知列表"""
    q = db.query(Notification)
    if unread_only:
        q = q.filter(Notification.is_read == False)
    items = q.order_by(Notification.created_at.desc()).limit(limit).all()
    return [
        {
            "id": n.id,
            "type": n.type,
            "title": n.title,
            "message": n.message,
            "is_read": n.is_read,
            "link": n.link,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in items
    ]


def mark_read(db: Session, notification_id: str) -> bool:
    """标记单条通知为已读"""
    n = db.query(Notification).filter(Notification.id == notification_id).first()
    if not n:
        return False
    n.is_read = True
    return True


def mark_all_read(db: Session) -> int:
    """全部标为已读"""
    count = db.query(Notification).filter(Notification.is_read == False).update({"is_read": True})
    return count
