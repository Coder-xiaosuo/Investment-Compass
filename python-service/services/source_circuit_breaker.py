"""双源断路器 — 东财(主) ⇄ 新浪(备)，整批全局切换。

状态机：
- ``closed``     : 使用主源（东财）。主源连续失败达 ``failure_threshold`` 次 → ``open``。
- ``open``       : 使用备源（新浪）。经过 ``recover_cooldown_s`` 冷却后 → ``half_open`` 探测。
- ``half_open``  : 用主源探测恢复。成功 → ``closed``（回切东财）；失败 → 立即回 ``open``。

切换粒度为整批全局：``get_source()`` 每次调用返回当前批次应使用的源，
运行中熔断后，本批次后续股票统一走备源，不做单票独立状态。
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 源标识
EASTMONEY = "eastmoney"
SINA = "sina"


@dataclass
class SourceCircuitBreaker:
    """线程安全的双源断路器。

    Args:
        failure_threshold: 主源连续失败多少次后熔断切备源（默认 3）。
        recover_cooldown_s: 熔断后经过多少秒允许探测主源恢复（默认 600s）。
    """

    failure_threshold: int = 3
    recover_cooldown_s: float = 600.0

    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _state: str = field(default="closed", init=False, repr=False)
    _failures: int = field(default=0, init=False, repr=False)
    _opened_at: float = field(default=0.0, init=False, repr=False)

    # ── 查询 ──────────────────────────────────────────────────────────────

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def current_source(self) -> str:
        """当前生效源（供日志/状态展示，与 get_source 一致但不触发状态跃迁）。"""
        with self._lock:
            if self._state in ("open", "half_open"):
                return SINA
            return EASTMONEY

    def get_source(self) -> str:
        """返回本次拉取应使用的源，并按冷却时间自动推进 half_open 探测。"""
        with self._lock:
            if self._state == "open":
                if time.monotonic() - self._opened_at >= self.recover_cooldown_s:
                    self._state = "half_open"
                    logger.info("断路器进入 half-open，用主源探测恢复")
                    return EASTMONEY
                return SINA
            if self._state == "half_open":
                return EASTMONEY
            return EASTMONEY

    # ── 反馈 ──────────────────────────────────────────────────────────────

    def record_success(self, source: str) -> None:
        with self._lock:
            self._failures = 0
            # 仅在 half_open 用主源探测成功时回切；open 状态备源成功保持熔断，
            # 待冷却后再探测主源，避免「备源成功即回切」造成来回抖动
            if self._state == "half_open" and source == EASTMONEY:
                self._state = "closed"
                logger.info("主源探测成功，断路器关闭，回切东财")

    def record_failure(self, source: str) -> None:
        with self._lock:
            # half_open 探测失败：一次即回熔断，避免来回抖动
            if self._state == "half_open":
                self._state = "open"
                self._opened_at = time.monotonic()
                self._failures = 1
                logger.warning("主源探测失败，重新熔断，继续使用新浪")
                return
            if source == EASTMONEY:
                self._failures += 1
                if self._failures >= self.failure_threshold:
                    self._state = "open"
                    self._opened_at = time.monotonic()
                    logger.warning(
                        "主源(东财)连续失败 %d 次，断路器熔断，切换新浪",
                        self._failures,
                    )
            else:
                # 备源失败不参与熔断状态；双源皆失败由调用方记录 errors 上报
                logger.warning("备源(新浪)失败，本次同步该标的记录失败")


# ── 模块级单例 ────────────────────────────────────────────────────────────────
_breaker: SourceCircuitBreaker | None = None
_breaker_lock = threading.Lock()


def get_source_breaker() -> SourceCircuitBreaker:
    """获取进程内复用的断路器单例（线程安全）。"""
    global _breaker
    if _breaker is None:
        with _breaker_lock:
            if _breaker is None:
                _breaker = SourceCircuitBreaker()
    return _breaker
