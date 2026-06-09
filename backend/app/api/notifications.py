"""系统通知 API — 消息中心（含官方公告、税务提醒、风险预警）"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.auth import get_current_user
from app.services.notification_service import (
    get_notifications, get_unread_count, mark_read, mark_all_read,
)

router = APIRouter()


@router.get("/")
def list_notifications(
    limit: int = Query(20, le=100),
    unread_only: bool = Query(False),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    items = get_notifications(db, limit=limit, unread_only=unread_only)
    total_unread = get_unread_count(db)
    return {
        "items": items,
        "total_unread": total_unread,
    }


@router.get("/count")
def notification_count(db: Session = Depends(get_db)):
    unread = get_unread_count(db)
    return {"unread": unread}


@router.patch("/{notification_id}/read")
def read_notification(notification_id: str, db: Session = Depends(get_db)):
    ok = mark_read(db, notification_id)
    if not ok:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="通知不存在")
    db.commit()
    return {"message": "已读"}


@router.patch("/read-all")
def read_all_notifications(db: Session = Depends(get_db)):
    count = mark_all_read(db)
    db.commit()
    return {"message": f"已标记 {count} 条为已读"}
