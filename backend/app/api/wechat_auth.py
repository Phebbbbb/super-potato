"""微信授权与绑定 API"""
import secrets
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.db import get_db
from app.config import settings
from app.services.auth import get_current_user
from app.models.user import User
from app.models.wechat_binding import WeChatBinding

router = APIRouter(prefix="/wechat", tags=["wechat"])


# 模拟: 开发环境无需真实微信公众号即可绑定
_DEV_OPENID_PREFIX = "dev_openid_"
_DEV_UNIONID_PREFIX = "dev_unionid_"


class BindRequest(BaseModel):
    openid: str
    nickname: str | None = None
    avatar: str | None = None


class BindResponse(BaseModel):
    success: bool
    message: str
    binding: dict | None = None


@router.get("/authorize-url")
def get_authorize_url(request: Request):
    """获取微信 OAuth 授权 URL。
    生产环境: 跳转到微信授权页面。
    开发环境: 返回模拟授权链接。
    """
    if not settings.wechat_app_id:
        # 开发模式 — 直接返回本地模拟链接
        return {
            "url": f"{settings.base_url}/api/wechat/dev-authorize",
            "app_id": "dev_mode",
            "is_dev": True,
        }

    redirect_uri = f"{settings.base_url}/api/wechat/callback"
    url = (
        f"https://open.weixin.qq.com/connect/oauth2/authorize"
        f"?appid={settings.wechat_app_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope=snsapi_userinfo"
        f"&state={secrets.token_hex(8)}"
        f"#wechat_redirect"
    )
    return {"url": url, "app_id": settings.wechat_app_id, "is_dev": False}


@router.get("/dev-authorize")
def dev_authorize(user_id: str = "", nickname: str = "", _=Depends(get_current_user)):
    """开发环境: 模拟微信授权，直接生成 openid 并绑定。"""
    if not user_id:
        return {"error": "缺少 user_id 参数", "message": "请提供 user_id 参数模拟授权"}

    openid = f"{_DEV_OPENID_PREFIX}{user_id}"
    return {
        "openid": openid,
        "unionid": f"{_DEV_UNIONID_PREFIX}{user_id}",
        "nickname": nickname or f"微信用户{user_id[:4]}",
        "avatar": "",
        "message": "开发模式授权成功，请调用 /api/wechat/bind 完成绑定",
    }


@router.post("/bind")
def bind_wechat(
    body: BindRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """绑定微信账号到当前登录用户。
    一对多: 服务端人员可绑定自己的微信，向多个客户推送。
    一对一: 客户端用户绑定微信后，仅与爻管家通信。
    """
    # 检查 openid 是否已被绑定
    existing = db.query(WeChatBinding).filter(WeChatBinding.openid == body.openid).first()
    if existing and existing.user_id != current_user.id:
        raise HTTPException(status_code=409, detail="该微信账号已绑定到其他用户")

    # 检查当前用户是否已绑定微信
    user_binding = db.query(WeChatBinding).filter(WeChatBinding.user_id == current_user.id).first()

    if user_binding:
        # 更新绑定
        user_binding.openid = body.openid
        user_binding.nickname = body.nickname
        user_binding.avatar = body.avatar
        user_binding.last_sync_at = __import__("datetime").datetime.now()
        msg = "微信绑定已更新"
    else:
        # 新建绑定
        user_binding = WeChatBinding(
            user_id=current_user.id,
            openid=body.openid,
            nickname=body.nickname,
            avatar=body.avatar,
        )
        db.add(user_binding)
        msg = "微信绑定成功"

    db.commit()

    return {
        "success": True,
        "message": msg,
        "binding": {
            "openid": user_binding.openid,
            "nickname": user_binding.nickname,
            "avatar": user_binding.avatar,
            "bound_at": user_binding.bound_at.isoformat() if user_binding.bound_at else None,
        },
    }


@router.get("/status")
def get_binding_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询当前用户的微信绑定状态"""
    binding = db.query(WeChatBinding).filter(WeChatBinding.user_id == current_user.id).first()
    if not binding:
        return {"bound": False, "binding": None}

    return {
        "bound": True,
        "binding": {
            "openid": binding.openid,
            "nickname": binding.nickname,
            "avatar": binding.avatar,
            "bound_at": binding.bound_at.isoformat() if binding.bound_at else None,
        },
    }


@router.post("/unbind")
def unbind_wechat(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """解绑微信账号"""
    binding = db.query(WeChatBinding).filter(WeChatBinding.user_id == current_user.id).first()
    if not binding:
        raise HTTPException(status_code=404, detail="未绑定微信账号")

    db.delete(binding)
    db.commit()
    return {"success": True, "message": "微信解绑成功"}
