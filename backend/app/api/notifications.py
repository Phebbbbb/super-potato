"""系统通知 API — 消息中心（含官方公告、税务提醒、风险预警）+ 多渠道推送"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.auth import get_current_user, require_admin
from app.services.notification_service import (
    get_notifications, get_unread_count, mark_read, mark_all_read,
)

router = APIRouter()


class SendNotificationRequest(BaseModel):
    template: str                          # tax_deadline / risk_alert / voucher_confirmed / filing_submitted / monthly_report
    params: dict = {}                      # 模板参数
    recipient: str = ""                    # 接收人
    channels: list[str] = ["in_app"]       # email / sms / wechat / in_app / webhook
    priority: str = "normal"               # low / normal / high / urgent


class SendTestRequest(BaseModel):
    channel: str = "in_app"
    recipient: str = ""


@router.get("/")
def list_notifications(
    limit: int = Query(20, le=100),
    unread_only: bool = Query(False),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    items = get_notifications(db, limit=limit, unread_only=unread_only)
    total_unread = get_unread_count(db)
    return {
        "items": items,
        "total_unread": total_unread,
    }


@router.get("/count")
def notification_count(db: Session = Depends(get_db)):
    unread = get_unread_count(db)
    return {"unread": unread}


@router.patch("/{notification_id}/read")
def read_notification(notification_id: str, db: Session = Depends(get_db)):
    ok = mark_read(db, notification_id)
    if not ok:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="通知不存在")
    db.commit()
    return {"message": "已读"}


@router.patch("/read-all")
def read_all_notifications(db: Session = Depends(get_db)):
    count = mark_all_read(db)
    db.commit()
    return {"message": f"已标记 {count} 条为已读"}


# ===== 多渠道通知推送（Apprise后端）=====

@router.post("/send")
def send_notification(
    body: SendNotificationRequest,
    _=Depends(require_admin),
):
    """发送多渠道通知 — 支持邮件/短信/微信/站内信/Webhook"""
    from app.services.notification_engine import get_notifier, Channel, Priority

    channels = [Channel(c) for c in body.channels if c in [e.value for e in Channel]]
    if not channels:
        channels = [Channel.IN_APP]

    priority = Priority(body.priority) if body.priority in [e.value for e in Priority] else Priority.NORMAL

    results = get_notifier().notify(
        template_key=body.template,
        params=body.params,
        recipient=body.recipient,
        channels=channels,
        priority=priority,
    )

    return {
        "sent": len([r for r in results if r.sent]),
        "delivered": len([r for r in results if r.delivered]),
        "results": [
            {"channel": r.channels[0].value, "sent": r.sent, "delivered": r.delivered, "error": r.error}
            for r in results
        ],
    }


@router.get("/templates")
def list_templates():
    """列出可用通知模板"""
    from app.services.notification_engine import TEMPLATES
    return {
        "templates": [
            {"key": k, "title": v["title"], "priority": str(v.get("priority", "normal"))}
            for k, v in TEMPLATES.items()
        ]
    }


@router.post("/send-test")
def send_test(
    body: SendTestRequest,
    _=Depends(require_admin),
):
    """测试通知渠道连通性"""
    from app.services.notification_engine import get_notifier, Channel
    channel = Channel(body.channel) if body.channel in [e.value for e in Channel] else Channel.IN_APP
    results = get_notifier().notify(
        "voucher_confirmed",
        {"voucher_no": "TEST-001", "summary": "渠道连通性测试",
         "confirmed_at": "", "maker": "系统", "reviewer": "测试"},
        recipient=body.recipient,
        channels=[channel],
    )
    return {
        "channel": body.channel,
        "success": results[0].sent if results else False,
        "error": results[0].error if results else "",
    }
