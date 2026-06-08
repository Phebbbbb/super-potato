"""数据库备份 API"""
from fastapi import APIRouter, Depends
from app.services.auth import require_admin
from app.services.backup import backup_database, restore_database
from app.services.error_handler import api_success, api_error, ErrorCode

router = APIRouter()


@router.post("/backup")
def trigger_backup(_=Depends(require_admin)):
    """手动触发备份（需管理员）"""
    result = backup_database()
    if result["success"]:
        return api_success(data=result, message=f"备份完成: {result['file']}")
    return api_error(ErrorCode.INTERNAL_ERROR, result.get("error", "备份失败"))


@router.post("/restore")
def trigger_restore(backup_file: str, _=Depends(require_admin)):
    """从备份恢复（需管理员）"""
    result = restore_database(backup_file)
    if result["success"]:
        return api_success(message=result["message"])
    return api_error(ErrorCode.INTERNAL_ERROR, result.get("error", "恢复失败"))
