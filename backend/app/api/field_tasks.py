"""外勤任务 API"""
import json, uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.field_task import FieldTask
from app.services.auth import get_current_user, require_modify
from app.models.user import User
from app.services.version_control import commit
from app.schemas.core import FieldTaskCreate

router = APIRouter()


@router.get("/")
def list_tasks(client_id: str = Query(None), status: str = Query(None),
               assigned_to: str = Query(None), page: int = Query(1), page_size: int = Query(50),
               db: Session = Depends(get_db), _=Depends(get_current_user)):
    q = db.query(FieldTask)
    if client_id: q = q.filter(FieldTask.client_id == client_id)
    if status: q = q.filter(FieldTask.status == status)
    if assigned_to: q = q.filter(FieldTask.assigned_to == assigned_to)
    total = q.count()
    items = q.order_by(FieldTask.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    return {"items": [{"id": t.id, "client_id": t.client_id, "task_type": t.task_type, "title": t.title,
            "description": t.description, "status": t.status, "assigned_to": t.assigned_to,
            "priority": t.priority, "deadline": str(t.deadline) if t.deadline else None,
            "completed_at": str(t.completed_at) if t.completed_at else None,
            "attachments": json.loads(t.attachments) if t.attachments else [],
            "notes": t.notes, "created_at": str(t.created_at)} for t in items],
            "total": total, "page": page, "page_size": page_size}


@router.post("/")
def create_task(data: FieldTaskCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user), _=Depends(require_modify)):
    t = FieldTask(id=uuid.uuid4().hex, client_id=data.client_id,
                  task_type=data.task_type, title=data.title,
                  description=data.description, priority=data.priority,
                  assigned_to=data.assigned_to, deadline=data.deadline)
    db.add(t)
    commit(db, "field_task", t.id, "created", user.display_name or "",
           after={"title": t.title, "task_type": t.task_type, "client_id": t.client_id})
    db.commit()
    return {"id": t.id, "message": "外勤任务创建成功"}


@router.patch("/{task_id}")
def update_task(task_id: str, data: dict, db: Session = Depends(get_db), _=Depends(get_current_user)):
    t = db.query(FieldTask).filter(FieldTask.id == task_id).first()
    if not t: raise HTTPException(404, "任务不存在")
    before = {"title": t.title, "status": t.status, "assigned_to": t.assigned_to}
    for f in ["title","description","status","assigned_to","priority","deadline","notes"]:
        if f in data: setattr(t, f, data[f])
    if "attachments" in data:
        t.attachments = json.dumps(data["attachments"], ensure_ascii=False)
    if data.get("status") == "completed":
        t.completed_at = datetime.now()
    commit(db, "field_task", task_id, "updated", data.get("assigned_to", "") or "",
           before=before, after={"title": t.title, "status": t.status, "assigned_to": t.assigned_to})
    db.commit()
    return {"message": "任务已更新"}


@router.delete("/{task_id}")
def delete_task(task_id: str, db: Session = Depends(get_db), _=Depends(require_modify)):
    t = db.query(FieldTask).filter(FieldTask.id == task_id).first()
    if t:
        commit(db, "field_task", task_id, "deleted", "",
               before={"title": t.title, "task_type": t.task_type, "status": t.status})
    db.query(FieldTask).filter(FieldTask.id == task_id).delete()
    db.commit()
    return {"message": "任务已删除"}
