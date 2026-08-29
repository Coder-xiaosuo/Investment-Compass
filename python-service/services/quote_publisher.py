"""Realtime quote publisher — 定时轮询 AkShare spot 行情，发布到 Redis。

数据流：
  AkShare stock_zh_a_spot() → Redis Hash (quote:{symbol}) + Pub/Sub "quotes"
    → Java WebSocket 订阅 Redis → 推送到前端
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime, time as time_cls
from typing import Any

logger = logging.getLogger(__name__)

_POLL_INTERVAL_S = 3.0
_REDIS_QUOTES_CHANNEL = "quotes"
_QUOTE_HASH_PREFIX = "quote:"

_6DIGIT_CODE_RE = re.compile(r"(\d{6})")

_redis_client: Any = None
_poll_task: asyncio.Task | None = None
_running = False


def _extract_symbol(raw_code: str) -> str:
    """从带前缀的代码中提取纯 6 位 code。"""
    m = _6DIGIT_CODE_RE.search(raw_code)
    return m.group(1) if m else raw_code.strip()


def _is_trading_time(now: datetime | None = None) -> bool:
    """判断当前是否为 A 股交易时段（周一至五 09:30-15:00）。"""
    now = now or datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return 9 * 60 + 30 <= t < 15 * 60


def _fetch_spot_sync() -> Any:
    """同步拉取 AkShare 全市场实时行情（阻塞调用，须放入线程池执行）。"""
    import akshare as ak
    return ak.stock_zh_a_spot()


async def _publish_quotes():
    """核心逻辑：拉 spot 行情 → 写 Redis Hash → 发布 Pub/Sub。"""
    import pandas as pd

    try:
        # AkShare 为同步阻塞调用（全市场拉取可能数十秒），放入线程池并加超时，
        # 防止拉取挂起导致事件循环卡死、全部 HTTP 接口无响应。
        df = await asyncio.wait_for(asyncio.to_thread(_fetch_spot_sync), timeout=30)
    except asyncio.TimeoutError:
        logger.warning("AkShare spot fetch timed out after 30s")
        return
    except Exception as exc:
        logger.warning("AkShare spot fetch failed: %s", exc)
        return

    if df is None or df.empty:
        logger.warning("AkShare spot returned empty")
        return

    pipeline = _redis_client.pipeline()

    quotes_batch: list[dict[str, Any]] = []
    now_ms = int(time.time() * 1000)

    for _, row in df.iterrows():
        try:
            raw_code = str(row.get("代码", "")).strip()
            symbol = _extract_symbol(raw_code)
            if not symbol or len(symbol) != 6:
                continue

            quote = {
                "symbol": symbol,
                "name": str(row.get("名称", "")),
                "price": float(row.get("最新价", 0) or 0),
                "change_pct": float(row.get("涨跌幅", 0) or 0),
                "change_amount": float(row.get("涨跌额", 0) or 0),
                "pre_close": float(row.get("昨收", 0) or 0),
                "open": float(row.get("今开", 0) or 0),
                "high": float(row.get("最高", 0) or 0),
                "low": float(row.get("最低", 0) or 0),
                "volume": float(row.get("成交量", 0) or 0),
                "amount": float(row.get("成交额", 0) or 0),
                "timestamp": now_ms,
            }

            hash_key = f"{_QUOTE_HASH_PREFIX}{symbol}"
            pipeline.hset(hash_key, mapping=quote)

            quotes_batch.append(quote)
        except Exception as exc:
            logger.debug("Skip quote row: %s", exc)

    if not quotes_batch:
        return

    pipeline.publish(_REDIS_QUOTES_CHANNEL, json.dumps(quotes_batch, ensure_ascii=False))
    await pipeline.execute()


async def _poll_loop():
    """后台轮询循环：盘内 3s 间隔，盘外 60s。"""
    global _running
    _running = True
    logger.info("Quote publisher started (interval=%ss)", _POLL_INTERVAL_S)

    while _running:
        try:
            if _is_trading_time():
                await _publish_quotes()
                await asyncio.sleep(_POLL_INTERVAL_S)
            else:
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Quote poll loop error: %s", exc)
            await asyncio.sleep(5)

    logger.info("Quote publisher stopped")


def start(redis_client: Any):
    """启动后台轮询任务。"""
    global _redis_client, _poll_task
    _redis_client = redis_client
    if _poll_task is not None and not _poll_task.done():
        logger.warning("Quote publisher already running")
        return
    _poll_task = asyncio.create_task(_poll_loop())


def stop():
    """停止后台轮询任务。"""
    global _running, _poll_task
    _running = False
    if _poll_task:
        _poll_task.cancel()
        _poll_task = None
    logger.info("Quote publisher stop signal sent")
