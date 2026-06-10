"""服务端-客户端交互 API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.db import get_db
from app.services.auth import get_current_user
from app.services.interaction_service import (
    send_message_to_client,
    send_feedback_to_service,
    get_service_messages,
    get_client_messages,
)

router = APIRouter()


class SendToClientRequest(BaseModel):
    client_id: str
    title: str
    message: str
    link: str | None = None


class FeedbackRequest(BaseModel):
    title: str
    message: str


@router.post("/send-to-client")
def notify_client(
    body: SendToClientRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """服务端人员（爻管家/爻工）向客户端推送消息"""
    try:
        result = send_message_to_client(
            db, body.client_id, body.title, body.message, body.link,
            sender_id=current_user.id,
            sender_name=current_user.display_name or current_user.username,
        )
        db.commit()
        return result
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/feedback")
def client_feedback(
    body: FeedbackRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """客户端向服务端发送反馈消息"""
    try:
        result = send_feedback_to_service(db, current_user.id, body.title, body.message)
        db.commit()
        return result
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/service-messages")
def list_service_messages(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """服务端查看交互消息（按员工管辖范围过滤）"""
    items = get_service_messages(db, user_id=current_user.id, limit=limit)
    return {"items": items, "total": len(items)}


@router.get("/client-messages")
def list_client_messages(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """客户端查看发给自己的消息"""
    items = get_client_messages(db, user_id=current_user.id, limit=limit)
    return {"items": items, "total": len(items)}
