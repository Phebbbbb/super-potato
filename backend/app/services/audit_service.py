"""审计日志服务：记录所有人工修改操作"""
import json
from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog


def log_action(
    db: Session,
    target_type: str,
    target_id: str,
    action: str,
    operator: str = "user",
    detail: dict | None = None,
):
    """记录操作审计日志"""
    log = AuditLog(
        target_type=target_type,
        target_id=target_id,
        action=action,
        operator=operator,
        detail=json.dumps(detail, ensure_ascii=False) if detail else None,
    )
    db.add(log)
    return log


def get_audit_trail(db: Session, target_type: str, target_id: str) -> list[dict]:
    """查询某个目标的所有操作历史"""
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.target_type == target_type, AuditLog.target_id == target_id)
        .order_by(AuditLog.created_at.desc())
        .all()
    )
    return [
        {
            "id": l.id,
            "action": l.action,
            "operator": l.operator,
            "detail": json.loads(l.detail) if l.detail else None,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in logs
    ]
