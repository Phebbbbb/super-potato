"""财税 Git 仓库 API — 版本历史、差异对比、回滚"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.auth import require_modify, require_admin, get_current_user
from app.models.user import User
from app.services.version_control import history, diff, revert_to, recent_activity
from app.services.error_handler import api_success, api_error, ErrorCode

router = APIRouter()


@router.get("/history/{target_type}/{target_id}")
def get_history(target_type: str, target_id: str, db: Session = Depends(get_db)):
    """查看某个实体的完整变更历史（git log）"""
    result = history(db, target_type, target_id)
    return api_success(data={"items": result, "total": len(result)})


@router.get("/diff/{target_type}/{target_id}")
def get_diff(target_type: str, target_id: str, db: Session = Depends(get_db)):
    """对比某个实体的最新版本与上一版本（git diff）"""
    result = diff(db, target_type, target_id)
    return api_success(data=result)


@router.post("/revert/{target_type}/{target_id}")
def revert_entity(
    target_type: str,
    target_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _=Depends(require_modify),
):
    """回滚到指定版本（git revert）"""
    snapshot = revert_to(db, target_type, target_id, version_id, user.display_name or "unknown")
    if snapshot is None:
        return api_error(ErrorCode.NOT_FOUND, "指定版本不存在")
    db.commit()
    return api_success(data={"snapshot": snapshot}, message="已回滚")


@router.get("/recent")
def get_recent_activity(limit: int = Query(50, le=200), db: Session = Depends(get_db)):
    """最近的变更活动"""
    result = recent_activity(db, limit=limit)
    return api_success(data={"items": result, "total": len(result)})
