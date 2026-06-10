"""国家税务总局 & 地方税务局公告 API"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.auth import get_current_user, require_admin
from app.services.tax_announcement import refresh_announcements, get_latest_announcements

router = APIRouter()


@router.get("/")
def list_announcements(
    limit: int = Query(10, le=50),
    source: str = Query(None, description="按来源筛选：国家税务总局 / 安徽税务 / 亳州税务"),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """获取最新公告列表，可按来源筛选"""
    items = get_latest_announcements(db, limit=limit, source=source)
    return {"items": items, "total": len(items)}


@router.get("/sources")
def list_sources():
    """列出所有公告来源"""
    return {
        "sources": [
            {"key": "国家税务总局", "label": "国家税务总局", "icon": "nation"},
            {"key": "安徽税务", "label": "安徽税务", "icon": "province"},
            {"key": "亳州税务", "label": "亳州税务", "icon": "city"},
        ]
    }


@router.post("/refresh")
def refresh(db: Session = Depends(get_db), _=Depends(require_admin)):
    """手动刷新所有公告源"""
    count = refresh_announcements(db)
    return {"message": f"公告刷新完成，新增 {count} 条"}
