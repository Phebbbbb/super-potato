"""统一错误处理 v2 — loguru结构化日志 + 错误码枚举 + 熔断器感知"""

import sys
from pathlib import Path
from enum import Enum
from datetime import datetime

from loguru import logger


# ===== 移除默认 handler，配置 loguru =====
logger.remove()

# 开发环境：彩色输出到控制台
logger.add(
    sys.stderr,
    level="DEBUG",
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>",
    colorize=True,
)

# 生产环境：结构化 JSON 到文件（按天轮转，保留 30 天）
LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger.add(
    LOG_DIR / "app_{time:YYYYMMDD}.log",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message} | extra={extra}",
    rotation="00:00",  # 每天午夜轮转
    retention="30 days",
    encoding="utf-8",
    enqueue=True,  # 多进程安全
    backtrace=True,
    diagnose=False,  # 生产环境不泄露变量值
)

# 错误日志单独文件
logger.add(
    LOG_DIR / "error_{time:YYYYMMDD}.log",
    level="ERROR",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message} | extra={extra}",
    rotation="00:00",
    retention="90 days",
    encoding="utf-8",
    enqueue=True,
    backtrace=True,
    diagnose=True,  # 错误日志保留诊断信息
)


# ===== 错误码 =====
class ErrorCode(str, Enum):
    SUCCESS = "SUCCESS"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    CONFLICT = "CONFLICT"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    RATE_LIMIT = "RATE_LIMIT"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"  # 熔断器打开


def api_error(code: ErrorCode, detail: str, retry: bool = False, data: dict = None) -> dict:
    err = {"code": code.value, "detail": detail, "retry": retry}
    if data:
        err["data"] = data
    return err


def api_success(data: dict = None, message: str = "") -> dict:
    result = {"code": ErrorCode.SUCCESS.value}
    if data:
        result["data"] = data
    if message:
        result["message"] = message
    return result


def log_error(module: str, exc: Exception, context: dict = None):
    """记录异常 — loguru 自动捕获 traceback"""
    logger.opt(exception=exc).error(
        f"[{module}] {type(exc).__name__}: {str(exc)[:300]}",
        context=context or {},
        module=module,
    )


def log_info(module: str, action: str, detail: str = ""):
    """记录操作"""
    logger.info(f"[{module}] {action} | {detail}", module=module, action=action)


def log_warning(module: str, message: str, **kwargs):
    """记录警告"""
    logger.warning(f"[{module}] {message}", module=module, **kwargs)


def log_debug(module: str, message: str, **kwargs):
    """记录调试信息"""
    logger.debug(f"[{module}] {message}", module=module, **kwargs)
