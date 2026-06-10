"""异常检测 API"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.user import User
from app.services.auth import get_current_user
from app.services.anomaly_detector import detect_all_anomalies, run_batch_anomaly_detection

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/anomaly/batch")
def batch_check(period: str = Query(None), db: Session = Depends(get_db)):
    """批量检测所有客户"""
    return {"results": run_batch_anomaly_detection(db)}


@router.get("/anomaly/{client_id}")
def check_anomalies(client_id: str, period: str = Query(None), db: Session = Depends(get_db)):
    """对指定客户执行全量异常检测"""
    return detect_all_anomalies(db, client_id, period)
