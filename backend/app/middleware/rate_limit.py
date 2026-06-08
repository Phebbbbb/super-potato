"""简易速率限制中间件 — 基于内存滑动窗口"""
import time
import threading
from collections import defaultdict
from fastapi import Request, HTTPException

# 配置
WINDOW_SIZE = 60        # 窗口大小（秒）
MAX_REQUESTS = 120      # 每窗口最大请求数
AUTH_MAX_REQUESTS = 10  # 登录接口限制更严
BLOCK_DURATION = 300    # 超限封禁时长（秒）

_lock = threading.Lock()
_hits: dict[str, list[float]] = defaultdict(list)
_blocks: dict[str, float] = {}


def _cleanup():
    """定期清理过期记录"""
    now = time.time()
    with _lock:
        for key in list(_hits.keys()):
            _hits[key] = [t for t in _hits[key] if now - t < WINDOW_SIZE]
            if not _hits[key]:
                del _hits[key]
        for key in list(_blocks.keys()):
            if now > _blocks[key]:
                del _blocks[key]


async def rate_limit_middleware(request: Request, call_next):
    """速率限制中间件 — 全局应用，路径敏感"""
    path = request.url.path

    # 静态资源和健康检查不限流
    if path.startswith("/uploads") or path.startswith("/qrcodes") or path == "/api/health":
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    key = f"{client_ip}:{path}"

    # 登录/认证接口严格限流
    is_auth = path in ("/api/auth/login", "/api/auth/register")
    max_req = AUTH_MAX_REQUESTS if is_auth else MAX_REQUESTS

    now = time.time()

    with _lock:
        # 检查是否被封禁
        if key in _blocks:
            if now < _blocks[key]:
                raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
            del _blocks[key]

        # 清理过期记录
        _hits[key] = [t for t in _hits[key] if now - t < WINDOW_SIZE]

        if len(_hits[key]) >= max_req:
            _blocks[key] = now + BLOCK_DURATION
            raise HTTPException(status_code=429, detail="请求过于频繁，已被临时限制，请 5 分钟后重试")

        _hits[key].append(now)

    # 每 100 次请求触发一次清理
    total_hits = sum(len(v) for v in _hits.values())
    if total_hits % 100 == 0:
        threading.Thread(target=_cleanup, daemon=True).start()

    return await call_next(request)
