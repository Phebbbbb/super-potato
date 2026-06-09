"""系统配置 API — 敏感值加密存储"""
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.system_config import SystemConfig
from app.models.user import User
from app.services.auth import require_admin, get_current_user
from app.services.version_control import commit
from app.services.cache import cache_get, cache_set, cache_invalidate
from app.config import encrypt_config_value, decrypt_config_value

router = APIRouter()


def get_tax_credentials(db: Session) -> dict:
    """获取解密的电子税务局凭据 — 供其他模块调用"""
    cfg = db.query(SystemConfig).filter(SystemConfig.config_key == "tax_bureau_auth").first()
    if not cfg or not cfg.config_value:
        return {}
    return _load_value("tax_bureau_auth", cfg.config_value)

# 需要加密存储的配置键
SENSITIVE_KEYS = {"tax_bureau_auth"}


def _is_sensitive(config_key: str) -> bool:
    return config_key in SENSITIVE_KEYS or "password" in config_key or "credential" in config_key or "auth" in config_key


def _store_value(config_key: str, data: dict) -> str:
    raw = json.dumps(data, ensure_ascii=False)
    return encrypt_config_value(raw) if _is_sensitive(config_key) else raw


def _load_value(config_key: str, stored: str) -> dict:
    if _is_sensitive(config_key):
        raw = decrypt_config_value(stored)
        if raw is None:
            return {}
        return json.loads(raw)
    try:
        return json.loads(stored)
    except (json.JSONDecodeError, TypeError):
        return {}


@router.get("/{config_key}")
def get_config(config_key: str, db: Session = Depends(get_db)):
    cache_key = f"settings:{config_key}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    cfg = db.query(SystemConfig).filter(SystemConfig.config_key == config_key).first()
    if not cfg:
        result = {"config_key": config_key, "config_value": {}}
    else:
        result = {"config_key": config_key, "config_value": _load_value(config_key, cfg.config_value)}
    cache_set(cache_key, result, ttl=600)
    return result


@router.patch("/{config_key}")
def update_config(config_key: str, data: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user), _=Depends(require_admin)):
    cfg = db.query(SystemConfig).filter(SystemConfig.config_key == config_key).first()
    value_str = _store_value(config_key, data.get("config_value", data))
    before = {"config_key": config_key, "exists": cfg is not None}
    if cfg:
        cfg.config_value = value_str
    else:
        cfg = SystemConfig(
            id=uuid.uuid4().hex,
            config_key=config_key,
            config_value=value_str,
        )
        db.add(cfg)
    commit(db, "system_config", config_key, "updated", user.display_name or "admin",
           before=before, after={"config_key": config_key, "exists": True})
    db.commit()
    cache_invalidate(f"settings:{config_key}")
    return {"config_key": config_key, "message": "保存成功"}
