"""智能任务优先级 API"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.auth import get_current_user
from app.services.task_priority import compute_client_priority, get_priority_queue, get_daily_worklist

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/priority/queue")
def priority_queue(db: Session = Depends(get_db)):
    """全局优先级队列（所有活跃客户按优先级排序）"""
    return {"queue": get_priority_queue(db)}


@router.get("/priority/worklist")
def daily_worklist(top_n: int = Query(10), db: Session = Depends(get_db)):
    """今日工作清单 — 按优先级排序的待办事项"""
    return get_daily_worklist(db, top_n)


@router.get("/priority/{client_id}")
def client_priority(client_id: str, db: Session = Depends(get_db)):
    """计算单个客户的综合优先级"""
    return compute_client_priority(db, client_id)
