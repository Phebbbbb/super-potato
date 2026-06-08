"""财税 Git 仓库 — 每笔数据变更自动 commit（before/after snapshot），支持 history / diff / revert"""
import json
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog


def commit(
    db: Session,
    target_type: str,  # voucher / invoice / filing / document / client / employee
    target_id: str,
    action: str,       # created / updated / deleted / confirmed / reverted
    operator: str,
    before: dict = None,
    after: dict = None,
) -> AuditLog:
    """
    创建一条版本快照。before = 变更前状态，after = 变更后状态。
    相当于 git commit，记录完整 diff。
    """
    log = AuditLog(
        id=str(uuid.uuid4()),
        target_type=target_type,
        target_id=target_id,
        action=action,
        operator=operator,
        detail=json.dumps({
            "before": before,
            "after": after,
        }, ensure_ascii=False, default=str),
    )
    db.add(log)
    return log


def history(db: Session, target_type: str, target_id: str) -> list[dict]:
    """
    查看某个实体的完整变更历史（git log）
    """
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.target_type == target_type, AuditLog.target_id == target_id)
        .order_by(AuditLog.created_at.desc())
        .all()
    )
    result = []
    for log in logs:
        detail = {}
        if log.detail:
            try:
                detail = json.loads(log.detail)
            except json.JSONDecodeError:
                detail = {"raw": log.detail}
        result.append({
            "id": log.id,
            "action": log.action,
            "operator": log.operator,
            "before": detail.get("before"),
            "after": detail.get("after"),
            "created_at": log.created_at.isoformat() if log.created_at else None,
        })
    return result


def diff(db: Session, target_type: str, target_id: str, version_a: int = None, version_b: int = None) -> dict:
    """
    对比两个版本之间的差异（git diff）
    不指定版本则对比最新与上一版本
    """
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.target_type == target_type, AuditLog.target_id == target_id)
        .order_by(AuditLog.created_at.desc())
        .all()
    )
    if len(logs) < 1:
        return {"diff": [], "message": "无历史记录"}

    a_log = logs[0]  # 最新
    b_log = logs[1] if len(logs) > 1 else None  # 上一版本

    a_data = json.loads(a_log.detail).get("after", {}) if a_log.detail else {}
    b_data = json.loads(b_log.detail).get("after", {}) if b_log and b_log.detail else {}

    changes = []
    all_keys = set(list(a_data.keys()) + list(b_data.keys()))
    for key in all_keys:
        old_val = b_data.get(key)
        new_val = a_data.get(key)
        if old_val != new_val:
            changes.append({
                "field": key,
                "old": old_val,
                "new": new_val,
            })

    return {
        "current_version": a_log.id,
        "previous_version": b_log.id if b_log else None,
        "diff": changes,
    }


def revert_to(db: Session, target_type: str, target_id: str, version_id: str, operator: str) -> Optional[dict]:
    """
    回滚到指定版本（git revert）
    返回该版本的 after 快照，供调用方恢复数据
    """
    target_log = (
        db.query(AuditLog)
        .filter(AuditLog.id == version_id)
        .first()
    )
    if not target_log:
        return None

    detail = {}
    if target_log.detail:
        try:
            detail = json.loads(target_log.detail)
        except json.JSONDecodeError:
            pass

    snapshot = detail.get("after", {})

    # 创建一条回滚记录
    commit(
        db=db,
        target_type=target_type,
        target_id=target_id,
        action="reverted",
        operator=operator,
        before={"reverted_from_version": version_id},
        after=snapshot,
    )

    return snapshot


def recent_activity(db: Session, client_id: str = None, limit: int = 50) -> list[dict]:
    """获取最近的变更活动（跨类型的 git log --all）"""
    q = db.query(AuditLog).order_by(AuditLog.created_at.desc())
    logs = q.limit(limit).all()
    result = []
    for log in logs:
        result.append({
            "id": log.id,
            "target_type": log.target_type,
            "target_id": log.target_id,
            "action": log.action,
            "operator": log.operator,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        })
    return result
