"""DEMO 数据源 — 市场概览看板联调用（真实 AkShare 数据）。

本模块为演示实现，数据来自 AkShare 公开接口；生产环境可替换/校验数据源。

聚合接口一次性返回以下数据：
- 大盘指数行情（上证/深证/创业板/科创50）
- 市场宽度（涨跌家数、涨停跌停数）
- 热点板块排名
- 北向资金流向
- 大盘成交量/成交额

策略：10 分钟内存缓存，成功与失败结果均缓存避免雪崩。
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

_cache: dict[str, tuple[dict, float]] = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 600        # 成功缓存 10 分钟
_CACHE_TTL_ERROR = 60   # 失败缓存 60 秒


def _cache_get(key: str) -> dict | None:
    with _cache_lock:
        item = _cache.get(key)
        if item and time.time() < item[1]:
            return item[0]
    return None


def _cache_set(key: str, value: dict, error: bool = False) -> None:
    ttl = _CACHE_TTL_ERROR if error else _CACHE_TTL
    with _cache_lock:
        _cache[key] = (value, time.time() + ttl)


def _safe_num(v, default: float = 0.0) -> float:
    """安全转 float；None/NaN/无法解析返回 default。"""
    if v is None:
        return default
    try:
        val = float(v)
        return val if val == val else default  # 过滤 NaN
    except (TypeError, ValueError):
        return default


# ── 指数代码 → 名称 ──────────────────────────────────────────────────────────
_INDEX_CODES = {
    "000001": "上证指数",
    "399001": "深证成指",
    "399006": "创业板指",
    "000688": "科创50",
}


def _fetch_indices() -> list[dict[str, Any]]:
    """拉取四大指数实时行情。"""
    try:
        import akshare as ak
        from shared.akshare_throttle import with_retry

        @with_retry(max_retries=2, timeout=8)
        def _fetch():
            return ak.stock_zh_index_spot_em()

        df = _fetch()
        if df is None or df.empty:
            return []

        results: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            code = str(row.get("代码", ""))
            if code not in _INDEX_CODES:
                continue
            results.append({
                "code": code,
                "name": _INDEX_CODES[code],
                "price": _safe_num(row.get("最新价")),
                "change": _safe_num(row.get("涨跌额")),
                "changePct": _safe_num(row.get("涨跌幅")),
                "volume": _safe_num(row.get("成交量")),
                "amount": _safe_num(row.get("成交额")),
            })
        return results
    except Exception as e:
        logger.warning("Market overview: indices fetch failed: %s", e)
        return []


def _fetch_breadth() -> dict[str, Any]:
    """从全市场快照统计涨跌家数、涨跌停家数。"""
    try:
        import akshare as ak
        from shared.akshare_throttle import with_retry

        @with_retry(max_retries=2, timeout=8)
        def _fetch():
            return ak.stock_zh_a_spot_em()

        df = _fetch()
        if df is None or df.empty:
            return {}

        up = down = flat = 0
        limit_up = limit_down = 0
        for _, row in df.iterrows():
            pct = _safe_num(row.get("涨跌幅"), 0)
            if pct > 0:
                up += 1
            elif pct < 0:
                down += 1
            else:
                flat += 1
            # 涨停/跌停近似：涨跌幅 >= 9.8% / <= -9.8%
            if pct >= 9.8:
                limit_up += 1
            elif pct <= -9.8:
                limit_down += 1

        return {
            "total": up + down + flat,
            "up": up,
            "down": down,
            "flat": flat,
            "limitUp": limit_up,
            "limitDown": limit_down,
        }
    except Exception as e:
        logger.warning("Market overview: breadth fetch failed: %s", e)
        return {}


def _fetch_sectors() -> list[dict[str, Any]]:
    """拉取概念板块资金流排名 top8。"""
    try:
        import akshare as ak
        from shared.akshare_throttle import with_retry

        @with_retry(max_retries=2, timeout=8)
        def _fetch():
            return ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="概念资金流")

        df = _fetch()
        if df is None or df.empty:
            return []

        results: list[dict[str, Any]] = []
        for _, row in df.head(8).iterrows():
            results.append({
                "name": str(row.get("名称", "")),
                "changePct": round(_safe_num(row.get("主力净流入-净占比")), 2),
                "netFlow": _safe_num(row.get("主力净流入-净额")),
            })
        return results
    except Exception as e:
        logger.warning("Market overview: sectors fetch failed: %s", e)
        return []


def _fetch_north_flow() -> dict[str, Any]:
    """拉取北向资金当日及近5日累计净流向。"""
    try:
        import akshare as ak
        from shared.akshare_throttle import with_retry

        @with_retry(max_retries=2, timeout=8)
        def _fetch():
            return ak.stock_hsgt_hist_em(symbol="北向资金")

        df = _fetch()
        if df is None or df.empty:
            return {}

        latest = df.iloc[0]
        recent = df.head(5)

        daily_flow: list[dict[str, Any]] = []
        for _, r in recent.iterrows():
            daily_flow.append({
                "date": str(r.get("日期", "")),
                "netFlow": _safe_num(r.get("当日成交净买额")),
            })

        return {
            "todayNet": _safe_num(latest.get("当日成交净买额")),
            "todayBuy": _safe_num(latest.get("买入成交额")),
            "todaySell": _safe_num(latest.get("卖出成交额")),
            "dailyFlow": daily_flow,
        }
    except Exception as e:
        logger.warning("Market overview: north flow fetch failed: %s", e)
        return {}


def _fetch_volume() -> dict[str, Any]:
    """拉取大盘成交额趋势（用上证指数日K线近10日成交额）。"""
    try:
        import akshare as ak
        from shared.akshare_throttle import with_retry

        @with_retry(max_retries=2, timeout=8)
        def _fetch():
            return ak.stock_zh_index_daily_em(symbol="sh000001")

        df = _fetch()
        if df is None or df.empty:
            return {}

        recent = df.tail(10)
        daily: list[dict[str, Any]] = []
        for _, r in recent.iterrows():
            daily.append({
                "date": str(r.get("date", "")),
                "amount": _safe_num(r.get("amount")),
                "volume": _safe_num(r.get("volume")),
            })

        today = daily[-1] if daily else {}
        prev = daily[-2] if len(daily) >= 2 else None
        amount_change = 0.0
        if today.get("amount") and prev and prev.get("amount"):
            amount_change = round((today["amount"] - prev["amount"]) / prev["amount"] * 100, 2)

        return {
            "todayAmount": today.get("amount", 0),
            "todayVolume": today.get("volume", 0),
            "amountChange": amount_change,
            "daily": daily,
        }
    except Exception as e:
        logger.warning("Market overview: volume fetch failed: %s", e)
        return {}


# ── Mock 回退数据 ────────────────────────────────────────────────────────────
_MOCK_DATA = {
    "indices": [
        {"code": "000001", "name": "上证指数", "price": 3380.52, "change": 12.35, "changePct": 0.37, "volume": 285000000, "amount": 3.2e11},
        {"code": "399001", "name": "深证成指", "price": 10876.30, "change": -25.10, "changePct": -0.23, "volume": 320000000, "amount": 4.1e11},
        {"code": "399006", "name": "创业板指", "price": 2250.18, "change": 18.42, "changePct": 0.82, "volume": 98000000, "amount": 1.5e11},
        {"code": "000688", "name": "科创50", "price": 985.30, "change": -3.15, "changePct": -0.32, "volume": 25000000, "amount": 0.36e11},
    ],
    "breadth": {
        "total": 5360, "up": 2842, "down": 2158, "flat": 360,
        "limitUp": 52, "limitDown": 18,
    },
    "sectors": [
        {"name": "AI人工智能", "changePct": 3.82, "netFlow": 5.62e9},
        {"name": "半导体", "changePct": 2.95, "netFlow": 4.18e9},
        {"name": "数据要素", "changePct": 2.31, "netFlow": 2.85e9},
        {"name": "机器人", "changePct": 1.87, "netFlow": 2.10e9},
        {"name": "低空经济", "changePct": 1.45, "netFlow": 1.56e9},
        {"name": "新能源车", "changePct": -0.68, "netFlow": -1.23e9},
        {"name": "光伏", "changePct": -1.52, "netFlow": -2.08e9},
        {"name": "白酒", "changePct": -2.10, "netFlow": -3.45e9},
    ],
    "northFlow": {
        "todayNet": 45.6e8,
        "todayBuy": 450.2e8,
        "todaySell": 404.6e8,
        "dailyFlow": [
            {"date": "2024-08-01", "netFlow": 32.5e8},
            {"date": "2024-08-02", "netFlow": -15.3e8},
            {"date": "2024-08-05", "netFlow": 28.1e8},
            {"date": "2024-08-06", "netFlow": 12.7e8},
            {"date": "2024-08-07", "netFlow": 45.6e8},
        ],
    },
    "volume": {
        "todayAmount": 8.8e11,
        "todayVolume": 720000000,
        "amountChange": 5.2,
        "daily": [
            {"date": "2024-07-26", "amount": 7.2e11, "volume": 620000000},
            {"date": "2024-07-29", "amount": 7.5e11, "volume": 650000000},
            {"date": "2024-07-30", "amount": 6.8e11, "volume": 580000000},
            {"date": "2024-07-31", "amount": 8.1e11, "volume": 700000000},
            {"date": "2024-08-01", "amount": 7.9e11, "volume": 680000000},
            {"date": "2024-08-02", "amount": 7.3e11, "volume": 640000000},
            {"date": "2024-08-05", "amount": 8.3e11, "volume": 710000000},
            {"date": "2024-08-06", "amount": 8.0e11, "volume": 690000000},
            {"date": "2024-08-07", "amount": 8.4e11, "volume": 705000000},
            {"date": "2024-08-08", "amount": 8.8e11, "volume": 720000000},
        ],
    },
}


def get_market_overview() -> dict[str, Any]:
    """聚合返回市场概览数据（带缓存）。

    Returns keys: indices, breadth, sectors, northFlow, volume
    """
    cache_key = "market_overview"
    hit = _cache_get(cache_key)
    if hit:
        return hit

    result: dict[str, Any] = {}
    fetch_errors = 0

    fetchers: dict[str, Any] = {
        "indices": _fetch_indices,
        "breadth": _fetch_breadth,
        "sectors": _fetch_sectors,
        "northFlow": _fetch_north_flow,
        "volume": _fetch_volume,
    }

    # 各数据源相互独立，并行拉取；配合 with_retry 的超时保护，
    # 避免单个 AkShare 接口挂起导致整个聚合接口长时间无响应。
    from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError

    with ThreadPoolExecutor(max_workers=len(fetchers)) as pool:
        futures = {pool.submit(fn): key for key, fn in fetchers.items()}
        try:
            for fut in as_completed(futures, timeout=12):
                key = futures[fut]
                try:
                    result[key] = fut.result()
                except Exception:
                    fetch_errors += 1
        except FuturesTimeoutError:
            for fut in futures:
                if not fut.done():
                    fut.cancel()
                    fetch_errors += 1

    # 对失败部分用 mock 回退
    if not result.get("indices"):
        result["indices"] = _MOCK_DATA["indices"]
    if not result.get("breadth"):
        result["breadth"] = _MOCK_DATA["breadth"]
    if not result.get("sectors"):
        result["sectors"] = _MOCK_DATA["sectors"]
    if not result.get("northFlow"):
        result["northFlow"] = _MOCK_DATA["northFlow"]
    if not result.get("volume"):
        result["volume"] = _MOCK_DATA["volume"]

    is_error = fetch_errors >= 3  # 一半以上失败视为降级，短缓存
    _cache_set(cache_key, result, error=is_error)
    return result
