"""K 线缓存失效信号（跨语言：Python 写 → Java 读）。

Python 侧写完 market_data 后递增版本号，Java 侧读缓存的 key 拼入版本戳：

    Java key = kline:{timeframe}:{symbol}:{limit}:v{version}
    version  = GET kline:ver:{symbol}   ← 本模块在写后 INCR

为什么用版本号而不是 DEL / Pub‑Sub：
  - DEL 需要按通配扫描（KEYS 会阻塞 Redis，只能 SCAN），且 Python 并不知道
    Java 缓存了哪些 limit 组合，无法精确删除；
  - Pub/Sub 要求订阅者在线，Java 重启期间的消息会永久丢失，缓存将永不失效；
  - 版本号一次 INCR 即可原子失效，旧版本 key 由各自的 TTL 自然回收。

时序约束：INCR 必须发生在事务 commit 之后。若在 commit 之前发出，Java 可能
抢先回源读到旧值并写回缓存，把旧值固化下来（read-modify-write 竞态）。

失效信号属于"可丢失"语义：丢失只会让 Java 多命中一次旧值（由 TTL 兜底），
不会产生错误数据。因此本模块绝不抛异常，避免拖垮数据写入主流程。
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Iterable

from shared.config import settings

logger = logging.getLogger(__name__)

# 版本号 key 前缀；完整 key 形如 kline:ver:600519
_VERSION_KEY_PREFIX = "kline:ver:"

# Redis 不可用时的重试冷却（秒），避免每次写入都打日志刷屏
_RETRY_COOLDOWN_S = 60.0

_client: Any = None
_next_retry_at: float = 0.0


def version_key(symbol: str) -> str:
    """由股票代码构造版本号 key，符号归一化为库内 canonical 形式。

    market_data.symbol 与 stock_metadata.symbol 均为不带后缀的 6 位代码，
    而 Python 侧调用方可能传入 ``600519`` 或 ``600519.SH`` 两种形式。
    这里统一剥离非数字字符，保证两侧 key 完全一致（Java 用 6 位代码拼 key）。
    """
    digits = re.sub(r"\D", "", symbol)
    code = digits[-6:] if len(digits) >= 6 else digits
    return f"{_VERSION_KEY_PREFIX}{code}"


def _get_client() -> Any:
    """惰性创建同步 Redis 客户端（调用方跑在工作线程中，不能用 asyncio 客户端）。"""
    global _client
    if _client is None:
        import redis

        _client = redis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
    return _client


def bump_kline_version(symbol: str) -> int | None:
    """递增指定标的的 K 线缓存版本号，返回新版本；Redis 不可用时返回 None。

    版本号 key 不设 TTL：若它过期归零，Java 侧可能仍持有旧版本号对应的缓存，
    再次 INCR 会从 1 重新计数从而与旧 key 撞号（读到过期数据）。
    每个标的仅一个 key，全市场约 5.5k 个、占用可忽略。
    """
    global _client, _next_retry_at

    now = time.monotonic()
    if now < _next_retry_at:  # 冷却期内静默跳过，避免日志刷屏
        return None

    try:
        return int(_get_client().incr(version_key(symbol)))
    except Exception as exc:
        # 丢弃可能已损坏的连接，冷却后重建
        _client = None
        _next_retry_at = now + _RETRY_COOLDOWN_S
        logger.warning(
            "K 线缓存版本号递增失败（%ds 内不再重试）%s: %s",
            int(_RETRY_COOLDOWN_S), symbol, exc,
        )
        return None


def bump_kline_versions(symbols: Iterable[str]) -> None:
    """批量递增（按去重后的标的逐个 INCR，单标的只加一次）。"""
    for symbol in {s for s in symbols if s}:
        bump_kline_version(symbol)
