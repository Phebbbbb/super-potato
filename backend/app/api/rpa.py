import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.rpa_task import RPATask
from app.services.auth import require_modify
from app.schemas.rpa import RPAIngestRequest, RPATaskUpdate
from app.services.ingest_service import ingest_documents
from app.services.qr_service import create_trace

router = APIRouter()


@router.post("/ingest")
def rpa_ingest(req: RPAIngestRequest, db: Session = Depends(get_db), _=Depends(require_modify)):
    """RPA 推送原始凭证数据到自研系统"""
    docs_dict = [d.model_dump() for d in req.documents]
    if not docs_dict:
        raise HTTPException(status_code=400, detail="documents 不能为空")

    results = ingest_documents(
        db=db,
        task_id=req.task_id,
        task_type=req.task_type,
        documents=docs_dict,
        client_id=req.client_id,
    )

    # 为每个成功入库的凭证生成 QR 码 #1
    for r in results:
        if r["success"] and r["document_id"]:
            create_trace(db, "document", r["document_id"], "ingest")

    success_count = sum(1 for r in results if r["success"])
    return {
        "total": len(results),
        "success_count": success_count,
        "failed_count": len(results) - success_count,
        "results": results,
    }


@router.get("/tasks")
def rpa_tasks(status: str = "pending", task_type: str = None, client_id: str = Query(None), db: Session = Depends(get_db)):
    """自研 → RPA: 下发待处理任务列表"""
    q = db.query(RPATask)
    q = q.filter(RPATask.status == status)
    if task_type:
        q = q.filter(RPATask.task_type == task_type)
    if client_id:
        q = q.filter(RPATask.client_id == client_id)
    tasks = q.order_by(RPATask.created_at.desc()).limit(50).all()

    return {
        "total": len(tasks),
        "items": [
            {
                "id": t.id,
                "task_type": t.task_type,
                "status": t.status,
                "payload": json.loads(t.payload) if t.payload else {},
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tasks
        ],
    }


@router.patch("/tasks/{task_id}")
def rpa_task_update(task_id: str, data: RPATaskUpdate, db: Session = Depends(get_db), _=Depends(require_modify)):
    """RPA 回写任务处理状态"""
    task = db.query(RPATask).filter(RPATask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if data.status is not None:
        task.status = data.status
    if data.result is not None:
        task.result = json.dumps(data.result, ensure_ascii=False)
    if data.assigned_rpa is not None:
        task.assigned_rpa = data.assigned_rpa
    if data.error_message is not None:
        task.error_message = data.error_message

    db.commit()
    return {"message": "任务状态已更新", "task_id": task_id, "status": task.status}
