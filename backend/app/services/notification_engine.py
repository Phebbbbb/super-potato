"""
多渠道通知引擎 — 底层 Apprise + 业务模板层

Apprise: 95+ 通知渠道统一API (邮件/短信/微信/钉钉/Slack/Telegram/...)
我们保留: 模板系统、优先级路由、故障转移逻辑、站内信落库
"""
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

# Apprise 可选依赖 — pip install apprise
try:
    import apprise as _apprise_lib
    APPRISE_AVAILABLE = True
except ImportError:
    APPRISE_AVAILABLE = False


class Channel(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    WECHAT = "wechat"
    IN_APP = "in_app"
    WEBHOOK = "webhook"


class Priority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class Notification:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    title: str = ""
    body: str = ""
    priority: Priority = Priority.NORMAL
    channels: list[Channel] = field(default_factory=lambda: [Channel.IN_APP])
    recipient: str = ""          # 邮箱/手机号/openid
    recipient_name: str = ""
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sent: bool = False
    delivered: bool = False
    error: str = ""


# ===== 通知模板 =====

TEMPLATES = {
    "tax_deadline": {
        "title": "⏰ 税务申报截止提醒",
        "body": "{client_name}，您好！\n\n{period} 期 {tax_type} 申报截止日期为 {deadline}，距截止还有 {days_left} 天。\n请尽快完成申报，避免逾期产生滞纳金（每日万分之五）。\n\n— 智能财税系统",
        "priority": Priority.HIGH,
    },
    "risk_alert": {
        "title": "🚨 税务风险预警",
        "body": "系统检测到 {client_name} 存在以下税务风险：\n\n{risk_details}\n\n风险等级：{risk_level}\n建议措施：{recommendation}\n\n请及时处理。\n— 智能财税系统",
        "priority": Priority.URGENT,
    },
    "voucher_confirmed": {
        "title": "📋 凭证审核通过",
        "body": "凭证 {voucher_no}（{summary}）已于 {confirmed_at} 审核通过。\n制单人：{maker}\n审核人：{reviewer}\n\n— 智能财税系统",
        "priority": Priority.LOW,
    },
    "filing_submitted": {
        "title": "📤 申报已提交",
        "body": "{client_name} {period} 期 {tax_type} 申报已于 {submitted_at} 提交。\n申报状态：{status}\n\n— 智能财税系统",
        "priority": Priority.NORMAL,
    },
    "monthly_report": {
        "title": "📊 {month} 月度财务报告",
        "body": "{client_name} {month} 月度财务摘要：\n\n营业收入：¥{revenue:,.2f}\n利润总额：¥{profit:,.2f}\n纳税总额：¥{tax_total:,.2f}\n凭证数量：{voucher_count} 张\n\n详细报告请登录系统查看。\n— 智能财税系统",
        "priority": Priority.NORMAL,
    },
}


class NotificationEngine:
    """统一通知引擎 — 借鉴 Apprise 的多渠道统一API"""

    def __init__(self):
        self.sent_log: list[Notification] = []
        self._smtp_config: dict = {}
        self._sms_config: dict = {}
        self._wechat_config: dict = {}
        self._webhook_config: dict = {}
        self._load_config()

    def _load_config(self):
        config_path = Path(__file__).parent.parent.parent / "data" / "notification_config.json"
        if config_path.exists():
            try:
                cfg = json.loads(config_path.read_text("utf-8"))
                self._smtp_config = cfg.get("email", {})
                self._sms_config = cfg.get("sms", {})
                self._wechat_config = cfg.get("wechat", {})
                self._webhook_config = cfg.get("webhook", {})
            except Exception:
                pass

    def notify(self, template_key: str, params: dict,
               recipient: str = "", channels: list[Channel] = None,
               priority: Priority = None) -> list[Notification]:
        """
        核心API: 发送通知
        - template_key: 模板名 (tax_deadline, risk_alert, etc.)
        - params: 模板参数
        - channels: 指定渠道，默认 [IN_APP]
        - 返回发送结果列表
        """
        template = TEMPLATES.get(template_key, TEMPLATES["tax_deadline"])

        try:
            title = template["title"].format(**params)
            body = template["body"].format(**params)
        except KeyError as e:
            title = template["title"]
            body = template["body"]

        if channels is None:
            channels = [Channel.IN_APP]
        if priority is None:
            priority = Priority(template.get("priority", "normal"))

        notifications = []
        for channel in channels:
            notif = Notification(
                title=title, body=body, priority=priority,
                channels=[channel], recipient=recipient
            )

            try:
                if channel == Channel.EMAIL:
                    self._send_email(notif)
                elif channel == Channel.SMS:
                    self._send_sms(notif)
                elif channel == Channel.WECHAT:
                    self._send_wechat(notif)
                elif channel == Channel.WEBHOOK:
                    self._send_webhook(notif)
                elif channel == Channel.IN_APP:
                    self._send_in_app(notif)
                notif.sent = True
                notif.delivered = True
            except Exception as e:
                notif.error = str(e)[:200]
                # 故障转移: 邮件 → 站内信
                if channel != Channel.IN_APP:
                    fallback = Notification(
                        title=title, body=body, priority=priority,
                        channels=[Channel.IN_APP], recipient=recipient
                    )
                    fallback.sent = True
                    fallback.delivered = True
                    fallback.metadata["fallback_from"] = channel.value
                    self._send_in_app(fallback)
                    notifications.append(fallback)

            notifications.append(notif)
            self.sent_log.append(notif)

        return notifications

    # ===== 渠道实现 — Apprise 后端 =====

    def _get_apprise(self) -> object:
        """获取 Apprise 实例"""
        if not APPRISE_AVAILABLE:
            raise RuntimeError("Apprise 未安装: pip install apprise")
        a = _apprise_lib.Apprise()
        # 从配置加载渠道URL
        cfg = self._load_config_raw()
        for channel_url in cfg.get("apprise_urls", []):
            a.add(channel_url)
        return a

    def _load_config_raw(self) -> dict:
        config_path = Path(__file__).parent.parent.parent / "data" / "notification_config.json"
        if config_path.exists():
            try:
                return json.loads(config_path.read_text("utf-8"))
            except Exception:
                pass
        return {}

    def _send_email(self, n: Notification):
        if APPRISE_AVAILABLE:
            a = self._get_apprise()
            a.notify(body=n.body, title=n.title, notify_type=_apprise_lib.NotifyType.INFO)
        else:
            self._send_email_fallback(n)

    def _send_email_fallback(self, n: Notification):
        """邮件兜底 — 无 Apprise 时使用 smtplib"""
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        cfg = self._smtp_config
        if not cfg:
            raise RuntimeError("邮件服务未配置")

        msg = MIMEMultipart()
        msg["From"] = cfg.get("from", "noreply@smarttax.com")
        msg["To"] = n.recipient or cfg.get("default_to", "")
        msg["Subject"] = n.title
        msg.attach(MIMEText(n.body, "plain", "utf-8"))

        with smtplib.SMTP(cfg.get("host", "smtp.example.com"),
                          cfg.get("port", 587), timeout=15) as server:
            server.starttls()
            server.login(cfg.get("user", ""), cfg.get("password", ""))
            server.send_message(msg)

    def _send_sms(self, n: Notification):
        if APPRISE_AVAILABLE:
            a = self._get_apprise()
            a.notify(body=n.body[:200], title=n.title)
        elif self._sms_config:
            self._send_sms_fallback(n)
        else:
            raise RuntimeError("短信服务未配置")

    def _send_sms_fallback(self, n: Notification):
        import urllib.request
        import urllib.parse
        params = urllib.parse.urlencode({
            "phone": n.recipient,
            "content": n.body[:200],
            "access_key": self._sms_config.get("access_key", ""),
        })
        url = f"{self._sms_config.get('endpoint', '')}?{params}"
        with urllib.request.urlopen(url, timeout=10) as resp:
            pass

    def _send_wechat(self, n: Notification):
        if APPRISE_AVAILABLE:
            a = self._get_apprise()
            a.notify(body=n.body, title=n.title)
        else:
            self._send_wechat_fallback(n)

    def _send_wechat_fallback(self, n: Notification):
        if not self._wechat_config:
            raise RuntimeError("微信通知未配置")
        # 通过微信模板消息发送 (保留原有实现)
        import urllib.request
        access_token = self._get_wechat_token()
        payload = json.dumps({
            "touser": n.recipient,
            "template_id": self._wechat_config.get("template_id", ""),
            "data": {
                "first": {"value": n.title},
                "keyword1": {"value": n.body[:100]},
                "remark": {"value": "点击查看详情 →"},
            },
        }, ensure_ascii=False).encode("utf-8")
        url = f"https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={access_token}"
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get("errcode") != 0:
                raise RuntimeError(f"WeChat failed: {result.get('errmsg')}")

    _wechat_token: str = ""
    _wechat_token_expiry: float = 0

    def _get_wechat_token(self) -> str:
        import time as _time
        if self._wechat_token and _time.time() < self._wechat_token_expiry:
            return self._wechat_token

        import urllib.request
        appid = self._wechat_config.get("app_id", "")
        secret = self._wechat_config.get("app_secret", "")
        url = f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={appid}&secret={secret}"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
            self._wechat_token = data.get("access_token", "")
            self._wechat_token_expiry = _time.time() + data.get("expires_in", 7200) - 300
            return self._wechat_token

    def _send_webhook(self, n: Notification):
        if not self._webhook_config:
            raise RuntimeError("Webhook未配置")

        import urllib.request
        payload = json.dumps({
            "title": n.title,
            "body": n.body,
            "priority": n.priority.value,
            "timestamp": n.created_at,
        }, ensure_ascii=False).encode("utf-8")

        url = self._webhook_config.get("url", "")
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            pass

    def _send_in_app(self, n: Notification):
        """站内信 — 写入数据库通知表"""
        try:
            from app.db import SessionLocal
            from app.models.notification import Notification as NotifModel
            db = SessionLocal()
            try:
                record = NotifModel(
                    id=n.id,
                    title=n.title,
                    content=n.body,
                    type="system" if n.priority in (Priority.HIGH, Priority.URGENT) else "info",
                    is_read=False,
                )
                db.add(record)
                db.commit()
                n.delivered = True
            finally:
                db.close()
        except Exception:
            pass  # 数据库不可用时静默失败

    def get_recent(self, limit: int = 20) -> list[dict]:
        return [
            {"id": n.id, "title": n.title, "body": n.body[:100],
             "priority": n.priority.value, "channels": [c.value for c in n.channels],
             "sent": n.sent, "delivered": n.delivered, "error": n.error,
             "created_at": n.created_at}
            for n in self.sent_log[-limit:]
        ]


# 全局单例
_engine: Optional[NotificationEngine] = None


def get_notifier() -> NotificationEngine:
    global _engine
    if _engine is None:
        _engine = NotificationEngine()
    return _engine


def send_deadline_reminder(client_name: str, period: str, tax_type: str,
                           deadline: str, days_left: int, recipient: str = "",
                           channels: list[Channel] = None):
    return get_notifier().notify("tax_deadline", {
        "client_name": client_name, "period": period, "tax_type": tax_type,
        "deadline": deadline, "days_left": days_left,
    }, recipient=recipient, channels=channels)


def send_risk_alert(client_name: str, risk_details: str, risk_level: str,
                    recommendation: str = "", recipient: str = "",
                    channels: list[Channel] = None):
    return get_notifier().notify("risk_alert", {
        "client_name": client_name, "risk_details": risk_details,
        "risk_level": risk_level, "recommendation": recommendation or "建议立即排查",
    }, recipient=recipient, channels=channels, priority=Priority.URGENT)
