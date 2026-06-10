"""应用配置 — 敏感信息从环境变量/.env 读取"""
import os
import secrets
from pathlib import Path
from pydantic_settings import BaseSettings
from cryptography.fernet import Fernet


def _get_or_create_jwt_secret() -> str:
    """获取 JWT 密钥：环境变量 > .jwt_secret 文件 > 自动生成"""
    env_val = os.environ.get("JWT_SECRET_KEY", "")
    if env_val:
        return env_val
    secret_file = Path(".jwt_secret")
    if secret_file.exists():
        return secret_file.read_text().strip()
    key = secrets.token_hex(32)
    secret_file.write_text(key)
    secret_file.chmod(0o600)
    return key


def _get_encryption_key() -> bytes:
    """获取敏感配置加密密钥"""
    env_val = os.environ.get("CONFIG_ENCRYPTION_KEY", "")
    if env_val:
        return env_val.encode()
    key_file = Path(".encryption_key")
    if key_file.exists():
        return key_file.read_text().strip().encode()
    key = Fernet.generate_key()
    key_file.write_text(key.decode())
    key_file.chmod(0o600)
    return key


class Settings(BaseSettings):
    app_name: str = "智能财税系统"
    database_url: str = "sqlite:///./smart_tax.db"
    upload_dir: str = "uploads"
    qrcode_dir: str = "qrcodes"
    base_url: str = "http://localhost:8000"
    backup_dir: str = "backups"
    log_dir: str = "logs"

    # JWT
    jwt_secret_key: str = ""  # 启动时自动生成
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # Redis
    redis_enabled: bool = False
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""

    # WeChat OAuth
    wechat_app_id: str = ""
    wechat_app_secret: str = ""
    wechat_token: str = ""
    wechat_encoding_aes_key: str = ""

    # LLM
    llm_provider: str = "claude"
    llm_api_key: str = ""
    llm_model: str = "claude-sonnet-4-6"
    llm_base_url: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
if not settings.jwt_secret_key:
    settings.jwt_secret_key = _get_or_create_jwt_secret()

# 敏感配置加密器
_encryption_key = _get_encryption_key()
_fernet = Fernet(_encryption_key)


def encrypt_config_value(plain: str) -> str:
    return _fernet.encrypt(plain.encode()).decode()


def decrypt_config_value(cipher: str) -> str | None:
    try:
        return _fernet.decrypt(cipher.encode()).decode()
    except Exception:
        return None
