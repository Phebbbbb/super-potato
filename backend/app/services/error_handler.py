"""统一错误处理 — 错误码枚举、结构化异常、日志落文件"""
import logging
import traceback
from pathlib import Path
from enum import Enum
from datetime import datetime
from app.config import settings


# ===== 日志配置 =====
def setup_logging():
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"app_{datetime.now().strftime('%Y%m%d')}.log"

    logger = logging.getLogger("smart_tax")
    logger.setLevel(logging.INFO)

    # 文件 handler
    fh = logging.FileHandler(str(log_file), encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(fh)

    # 控制台 handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)
    ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(ch)

    # 清理超过30天的日志
    cutoff = datetime.now().timestamp() - 30 * 86400
    for f in log_dir.iterdir():
        if f.is_file() and f.stat().st_mtime < cutoff:
            f.unlink()

    return logger


logger = setup_logging()


# ===== 错误码 =====
class ErrorCode(str, Enum):
    SUCCESS = "SUCCESS"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    CONFLICT = "CONFLICT"  # 状态冲突（如重复操作）
    UPSTREAM_ERROR = "UPSTREAM_ERROR"  # Playwright/第三方异常
    INTERNAL_ERROR = "INTERNAL_ERROR"
    RATE_LIMIT = "RATE_LIMIT"


def api_error(code: ErrorCode, detail: str, retry: bool = False, data: dict = None) -> dict:
    """构造统一错误响应"""
    err = {"code": code.value, "detail": detail, "retry": retry}
    if data:
        err["data"] = data
    return err


def api_success(data: dict = None, message: str = "") -> dict:
    """构造统一成功响应"""
    result = {"code": ErrorCode.SUCCESS.value}
    if data:
        result["data"] = data
    if message:
        result["message"] = message
    return result


def log_error(module: str, exc: Exception, context: dict = None):
    """记录异常到日志"""
    logger.error(
        f"[{module}] {type(exc).__name__}: {str(exc)[:300]}\n"
        f"context: {context or {}}\n"
        f"traceback: {traceback.format_exc()[-500:]}"
    )


def log_info(module: str, action: str, detail: str = ""):
    """记录操作到日志"""
    logger.info(f"[{module}] {action} | {detail}")
