"""DEMO 数据源服务 — 技术面看板演示用数据（仅演示级）。

DEMO 标注：本模块为演示实现，数据来自 AkShare 公开接口，**仅用于前端
技术面数据看板的开发联调**；生产环境需替换/校验数据源后移除本模块。

接口：
- get_stock_fundflow  个股资金流向（同花顺当日快照主源 / 东财逐日备源）+ N 日净流入汇总
- get_shareholder_count  股东户数历史变化（散户数量维度）

说明：外部源实时抓取慢且不稳定（东财接口被反爬 RemoteDisconnected），
因此对最终结果做 10 分钟内存缓存，避免每次请求都实时拉取。
"""
from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

# DEMO 结果缓存（成功 TTL 10 分钟 / 失败 TTL 60 秒）：缓存成功与失败结果，二次请求秒回
_demo_cache: dict[str, tuple[dict, float]] = {}
_demo_cache_lock = threading.Lock()
_DEMO_CACHE_TTL = 600
_DEMO_CACHE_TTL_ERROR = 60


def _cache_get(key: str) -> dict | None:
    with _demo_cache_lock:
        item = _demo_cache.get(key)
        if item and time.time() < item[1]:
            return item[0]
    return None


def _cache_set(key: str, value: dict) -> None:
    # 失败结果只做 60 秒短缓存，避免数据源恢复后仍被旧失败挡住
    ttl = _DEMO_CACHE_TTL_ERROR if value.get("error") else _DEMO_CACHE_TTL
    with _demo_cache_lock:
        _demo_cache[key] = (value, time.time() + ttl)


def _strip_suffix(symbol: str) -> str:
    """去掉交易所后缀（000001.SZ → 000001）。"""
    return (symbol or "").strip().split(".")[0]


def _market_suffix(code: str) -> str:
    """按 6 位代码推断交易所前缀（AkShare fund_flow 参数）。"""
    if code.startswith("6"):
        return "sh"
    if code.startswith(("0", "3")):
        return "sz"
    return "bj"


def _num(value) -> float | None:
    """安全转 float；None / NaN / 无法解析返回 None。"""
    if value is None:
        return None
    try:
        v = float(value)
        return None if v != v else v  # 过滤 NaN
    except (TypeError, ValueError):
        return None


def _fetch_ths_snapshot(code: str) -> dict | None:
    """同花顺当日资金流快照（主源）。"""
    import akshare as ak

    from shared.akshare_throttle import with_retry

    @with_retry(max_retries=1)
    def _fetch():
        return ak.stock_fund_flow_individual(symbol="即时")

    try:
        df = _fetch()
        if df is not None and not df.empty and "股票代码" in df.columns:
            # 同花顺页面经 AkShare read_html 解析会把 000/001/002/003 前导零丢成
            # 2230/2350/779，补齐后再精确匹配
            hit = df[df["股票代码"].astype(str).str.zfill(6) == code]
            if not hit.empty:
                r = hit.iloc[0]
                return {
                    "symbol": code,
                    "source": "ths",
                    "mode": "snapshot",
                    "snapshot": {
                        "name": str(r.get("股票简称", "")),
                        "price": _num(r.get("最新价")),
                        "change_pct": str(r.get("涨跌幅", "")),
                        "turnover": str(r.get("换手率", "")),
                        "inflow": str(r.get("流入资金", "")),
                        "outflow": str(r.get("流出资金", "")),
                        "net": str(r.get("净额", "")),
                        "amount": str(r.get("成交额", "")),
                    },
                }
    except Exception as exc:
        logger.warning("fundflow 同花顺源失败 %s: %s", code, exc)
    return None


def _fetch_em_daily(code: str, market: str, days: int) -> dict | None:
    """东财逐日资金流（备源，当前被反爬通常失败）。"""
    import akshare as ak

    from shared.akshare_throttle import with_retry

    @with_retry(max_retries=1)
    def _fetch():
        return ak.stock_individual_fund_flow(stock=code, market=market)

    try:
        df = _fetch()
        if df is None or df.empty:
            logger.warning("fundflow 东财备源无数据 %s", code)
            return None
        df = df.tail(days)
        rows = []
        for _, r in df.iterrows():
            rows.append({
                "date": str(r.get("日期", "")),
                "main_net": _num(r.get("主力净流入-净额")),
                "super_net": _num(r.get("超大单净流入-净额")),
                "large_net": _num(r.get("大单净流入-净额")),
                "medium_net": _num(r.get("中单净流入-净额")),
                "small_net": _num(r.get("小单净流入-净额")),
                "main_net_pct": _num(r.get("主力净流入-净占比")),
            })
        summary = {}
        for n in (3, 5, 10):
            seg = rows[-n:] if n <= len(rows) else rows
            summary[f"{n}d"] = round(sum(_num(x["main_net"]) or 0 for x in seg), 2)
        return {
            "symbol": code,
            "source": "em",
            "mode": "daily",
            "daily": rows,
            "summary": summary,
        }
    except Exception as exc:
        logger.warning("fundflow 东财备源失败 %s: %s", code, exc)
    return None


def get_stock_fundflow(symbol: str, days: int = 10) -> dict:
    """个股资金流向：主源同花顺当日快照，失败回退东财逐日序列。

    DEMO：演示级数据源，AkShare 实时拉取，结果缓存 10 分钟。
    """
    code = _strip_suffix(symbol)
    if not code:
        return {"error": True, "message": f"无效股票代码: {symbol}"}

    cache_key = f"fundflow_{code}"
    hit = _cache_get(cache_key)
    if hit:
        return hit

    market = _market_suffix(code)

    # 主源：同花顺当日快照
    result = _fetch_ths_snapshot(code)
    # 备源：东财逐日资金流
    if result is None:
        result = _fetch_em_daily(code, market, days)
    if result is None:
        result = {"error": True, "message": f"{code} 资金流获取失败（同花顺/东财均不可用）"}

    _cache_set(cache_key, result)
    return result


def get_shareholder_count(symbol: str) -> dict:
    """股东户数历史变化（散户数量维度，用于筹码情绪卡片）。

    DEMO：演示级数据源，AkShare `stock_zh_a_gdhs_detail_em` 实时拉取，结果缓存 10 分钟。
    """
    code = _strip_suffix(symbol)
    if not code:
        return {"error": True, "message": f"无效股票代码: {symbol}"}

    cache_key = f"shareholders_{code}"
    hit = _cache_get(cache_key)
    if hit:
        return hit

    import akshare as ak

    from shared.akshare_throttle import with_retry

    @with_retry(max_retries=2)
    def _fetch():
        return ak.stock_zh_a_gdhs_detail_em(symbol=code)

    try:
        df = _fetch()
        if df is None or df.empty:
            result = {"error": True, "message": f"{code} 无股东户数数据"}
        else:
            rows = []
            for _, r in df.tail(20).iterrows():
                rows.append({
                    "date": str(r.get("股东户数统计截止日", r.get("股东户数公告日期", ""))),
                    "count": _num(r.get("股东户数-本次")),
                    "change": _num(r.get("股东户数-增减")),
                    "change_pct": _num(r.get("股东户数-增减比例")),
                })
            result = {"symbol": code, "rows": rows}
    except Exception as exc:
        logger.warning("shareholders fetch failed %s: %s", code, exc)
        result = {"error": True, "message": f"股东户数获取失败: {exc}"}

    _cache_set(cache_key, result)
    return result
