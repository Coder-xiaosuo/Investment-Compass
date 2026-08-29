"""AkShare 全局限流保护 — 所有实时调用的统一入口。

提供跨模块共享的访问限制和重试机制，避免东财 API 限流（RemoteDisconnected）。
"""
from __future__ import annotations

import concurrent.futures
import logging
import threading
import time
from functools import wraps
from typing import Any, Callable

logger = logging.getLogger(__name__)

_throttle_lock = threading.Lock()
_last_call_mono: float = 0.0

# 最小调用间隔（秒）
MIN_INTERVAL_S = 1.2

# 内存缓存：{ cache_key: (value, expiry_timestamp) }
_cache: dict[str, tuple[Any, float]] = {}
_cache_lock = threading.Lock()

# AkShare 调用线程池 + 默认超时：请求挂起（不抛异常）时由超时兜底，
# 避免拖垮 FastAPI 请求线程导致接口长时间无响应。
_FETCH_POOL = concurrent.futures.ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="akshare-fetch"
)
_FETCH_TIMEOUT_S = 15.0


def run_with_timeout(fn: Callable, timeout: float = _FETCH_TIMEOUT_S, *args, **kwargs) -> Any:
    """在线程池中执行阻塞调用并限制最大等待时间。

    超时后主流程立即抛出 TimeoutError，底层线程在后台自然结束（无法强杀，
    但不会阻塞请求线程）。用于保护 AkShare 等无超时参数的第三方调用。
    """
    fut = _FETCH_POOL.submit(fn, *args, **kwargs)
    try:
        return fut.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        fut.cancel()
        raise TimeoutError(f"AkShare call timed out after {timeout}s")


def throttle():
    """调用前等待，保证两次 AkShare API 调用间隔 >= MIN_INTERVAL_S。"""
    global _last_call_mono
    with _throttle_lock:
        now = time.monotonic()
        wait = MIN_INTERVAL_S - (now - _last_call_mono)
        if wait > 0:
            time.sleep(wait)
        _last_call_mono = time.monotonic()


def cached(cache_key: str, ttl_seconds: int = 300):
    """装饰器：对 AkShare 调用结果做内存缓存。

    Args:
        cache_key: 缓存键（如 "financial_600519"）
        ttl_seconds: 缓存有效期（默认 5 分钟）
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            with _cache_lock:
                if cache_key in _cache:
                    val, expiry = _cache[cache_key]
                    if time.time() < expiry:
                        logger.debug("AkShare cache HIT: %s", cache_key)
                        return val
            # 缓存未命中
            result = func(*args, **kwargs)
            with _cache_lock:
                _cache[cache_key] = (result, time.time() + ttl_seconds)
            return result
        return wrapper
    return decorator


def with_retry(max_retries: int = 2, timeout: float = _FETCH_TIMEOUT_S):
    """装饰器：AkShare 调用失败时自动重试，并带超时保护防止挂起。"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries):
                try:
                    throttle()
                    return run_with_timeout(func, timeout, *args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    if attempt < max_retries - 1:
                        wait = (attempt + 1) * 2.0
                        logger.warning("AkShare retry %d/%d after %.1fs: %s", 
                                       attempt + 1, max_retries, wait, exc)
                        time.sleep(wait)
                    else:
                        logger.error("AkShare failed after %d retries: %s", max_retries, exc)
            raise last_exc
        return wrapper
    return decorator


def clear_cache(cache_key: str | None = None):
    """清除 AkShare 内存缓存。"""
    with _cache_lock:
        if cache_key:
            _cache.pop(cache_key, None)
        else:
            _cache.clear()


def invalidate_stock_cache(symbol: str):
    """清除某只股票的所有缓存。"""
    with _cache_lock:
        keys = [k for k in _cache if symbol in k]
        for k in keys:
            _cache.pop(k, None)
