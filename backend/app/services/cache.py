"""
Redis 缓存层 — 高频查询加速，降级到内存缓存
"""
import json
import time
import functools
import threading
from typing import Optional, Callable
from app.config import settings


class CacheBackend:
    """缓存后端抽象"""

    def get(self, key: str) -> Optional[str]:
        raise NotImplementedError

    def set(self, key: str, value: str, ttl: int = 300) -> None:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError

    def delete_pattern(self, pattern: str) -> None:
        raise NotImplementedError


class RedisBackend(CacheBackend):
    """Redis 后端"""

    def __init__(self):
        import redis
        self.client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password or None,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=True,
        )
        self.client.ping()

    def get(self, key: str) -> Optional[str]:
        try:
            return self.client.get(key)
        except Exception:
            return None

    def set(self, key: str, value: str, ttl: int = 300) -> None:
        try:
            self.client.setex(key, ttl, value)
        except Exception:
            pass

    def delete(self, key: str) -> None:
        try:
            self.client.delete(key)
        except Exception:
            pass

    def delete_pattern(self, pattern: str) -> None:
        try:
            keys = self.client.keys(pattern)
            if keys:
                self.client.delete(*keys)
        except Exception:
            pass


class MemoryBackend(CacheBackend):
    """内存降级后端（带 TTL + 惰性清理）"""

    def __init__(self):
        self._store: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()
        self._last_cleanup = time.time()
        self._cleanup_interval = 60  # 每 60 秒批量清理一次

    def _cleanup(self):
        """定期批量清理过期键（O(N) 但仅每 60 秒触发一次）"""
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        self._last_cleanup = now
        with self._lock:
            expired = [k for k, (_, exp) in self._store.items() if now > exp]
            for k in expired:
                del self._store[k]

    def get(self, key: str) -> Optional[str]:
        self._cleanup()
        with self._lock:
            entry = self._store.get(key)
            if entry:
                now = time.time()
                if now < entry[1]:
                    return entry[0]
                del self._store[key]
        return None

    def set(self, key: str, value: str, ttl: int = 300) -> None:
        with self._lock:
            self._store[key] = (value, time.time() + ttl)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def delete_pattern(self, pattern: str) -> None:
        import re
        regex = re.compile(pattern.replace("*", ".*"))
        with self._lock:
            keys = [k for k in self._store if regex.match(k)]
            for k in keys:
                del self._store[k]


# ---- 自动选择后端 ----
_backend: CacheBackend = None

def _get_backend() -> CacheBackend:
    global _backend
    if _backend is None:
        if settings.redis_enabled:
            try:
                _backend = RedisBackend()
                print("[Cache] Redis 连接成功")
            except Exception:
                print("[Cache] Redis 不可用，降级到内存缓存")
                _backend = MemoryBackend()
        else:
            _backend = MemoryBackend()
    return _backend


def cache_get(key: str) -> Optional[any]:
    """读取缓存，自动反序列化 JSON"""
    raw = _get_backend().get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw


def cache_set(key: str, value: any, ttl: int = 300) -> None:
    """写入缓存，自动序列化 JSON"""
    try:
        raw = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        raw = str(value)
    _get_backend().set(key, raw, ttl)


def cache_delete(key: str) -> None:
    _get_backend().delete(key)


def cache_invalidate(pattern: str) -> None:
    """按模式失效，如 'accounts:*' """
    _get_backend().delete_pattern(pattern)


def cached(ttl: int = 300, key_prefix: str = ""):
    """装饰器：缓存函数返回值

    usage:
        @cached(ttl=600, key_prefix="accounts")
        def get_account_tree():
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 构建缓存键
            parts = [key_prefix or func.__name__]
            if args:
                parts.append(str(args))
            if kwargs:
                parts.append(str(sorted(kwargs.items())))
            cache_key = ":".join(parts)

            cached_val = cache_get(cache_key)
            if cached_val is not None:
                return cached_val

            import asyncio
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            cache_set(cache_key, result, ttl)
            return result
        return wrapper
    return decorator
