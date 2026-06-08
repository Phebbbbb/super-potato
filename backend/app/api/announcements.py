"""国家税务总局公告 API"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.tax_announcement import refresh_announcements, get_latest_announcements

router = APIRouter()


@router.get("/")
def list_announcements(limit: int = Query(10, le=50), db: Session = Depends(get_db)):
    """获取最新公告列表"""
    items = get_latest_announcements(db, limit=limit)
    return {"items": items, "total": len(items)}


@router.post("/refresh")
def refresh(db: Session = Depends(get_db)):
    """手动刷新公告"""
    count = refresh_announcements(db)
    return {"message": f"公告刷新完成，新增 {count} 条"}
