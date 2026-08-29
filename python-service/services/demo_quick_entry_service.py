"""DEMO 数据源 — 对话页投研快捷入口联调用（真实 AkShare 数据）。

本模块为演示实现，数据来自 AkShare 公开接口；生产环境可替换/校验数据源。

策略：后台线程异步预加载 + 10 分钟内存缓存；首次请求若缓存未就绪则返回
模拟占位数据，后台加载完成后自动切为真实数据。
"""
from __future__ import annotations

import logging
import threading
import time

import akshare as ak
import pandas as pd

logger = logging.getLogger(__name__)

# 内存缓存（成功 TTL 10分钟 / 失败 TTL 60秒）
_cache: dict[str, tuple[list | None, float]] = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 600
_CACHE_ERROR_TTL = 60


def _get_cache(key: str) -> list | None:
    with _cache_lock:
        item = _cache.get(key)
        if item and time.time() < item[1]:
            return item[0]
    return None


def _set_cache(key: str, value: list, error: bool = False) -> None:
    ttl = _CACHE_ERROR_TTL if error else _CACHE_TTL
    with _cache_lock:
        _cache[key] = (value, time.time() + ttl)


def _safe_num(v) -> float:
    try:
        return float(v) if pd.notna(v) else 0.0
    except (ValueError, TypeError):
        return 0.0


# ====================================================================
#  后台预加载（服务启动后异步拉取）— 首次请求秒回
# ====================================================================

_preloaded = False
_preload_lock = threading.Lock()


def preload():
    """在后台线程中预拉取所有快捷入口数据（调用后异步执行）。"""
    def _run():
        global _preloaded
        with _preload_lock:
            if _preloaded:
                return
            _preloaded = True
        logger.info("DEMO quick-entry preload started")
        try:
            _refresh_hot()
        except Exception:
            pass
        try:
            _refresh_rankings()
        except Exception:
            pass
        try:
            _refresh_events()
        except Exception:
            pass
        logger.info("DEMO quick-entry preload done")

    t = threading.Thread(target=_run, daemon=True)
    t.start()


# ====================================================================
#  真实数据拉取
# ====================================================================

def _refresh_hot():
    """拉取板块资金流排行 → 热点板块。"""
    try:
        # 概念板块资金流排行（轻量 API）
        df = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="概念资金流")
        if df is None or df.empty:
            return
        results = []
        for _, row in df.head(8).iterrows():
            name = str(row.get("名称", ""))
            pct = _safe_num(row.get("主力净流入-净占比"))
            # 用净占比近似涨跌幅方向
            results.append({
                "name": name,
                "change": round(pct, 2),
                "reason": f"{name}板块{'主力流入' if pct > 0 else '主力流出'}",
            })
        if results:
            _set_cache("hot_sectors", results)
    except Exception as e:
        logger.warning("Hot sectors refresh failed: %s", e)


def _refresh_rankings():
    """拉取实时行情 → 四大榜单。"""
    try:
        # 使用涨幅榜+快速涨幅榜（轻量 API）
        df_up = ak.stock_zh_a_spot_em()
        if df_up is None or df_up.empty:
            return

        col_map = {"代码": "code", "名称": "name", "涨跌幅": "change", "成交额": "amount"}
        df = df_up.rename(columns={k: v for k, v in col_map.items() if k in df_up.columns})
        rankings = []

        # 涨幅榜
        if "change" in df.columns:
            top = df.nlargest(3, "change")
            stocks = [f'{r["name"]} {_safe_num(r.get("change")):+.2f}%' for _, r in top.iterrows()]
            rankings.append({"title": "涨幅榜", "desc": "今日涨幅TOP3", "stocks": stocks})

        # 成交额榜
        if "amount" in df.columns:
            top = df.nlargest(3, "amount")
            stocks = [str(r["name"]) for _, r in top.iterrows()]
            rankings.append({"title": "成交额榜", "desc": "今日成交额TOP3", "stocks": stocks})

        # 放量上涨
        if "change" in df.columns and "amount" in df.columns:
            up = df[df["change"] > 0]
            if not up.empty:
                top = up.nlargest(3, "amount")
                stocks = [str(r["name"]) for _, r in top.iterrows()]
                rankings.append({"title": "放量上涨", "desc": "成交活跃上涨TOP3", "stocks": stocks})

        # 中盘精选
        if "change" in df.columns and len(df) > 100:
            mid = df.iloc[len(df) // 3 : 2 * len(df) // 3]
            top = mid.nlargest(3, "change")
            stocks = [str(r["name"]) + f' {_safe_num(r.get("change")):+.2f}%' for _, r in top.iterrows()]
            rankings.append({"title": "中盘精选", "desc": "中盘涨幅TOP3", "stocks": stocks})

        if len(rankings) >= 3:
            _set_cache("rankings_all", rankings)
    except Exception as e:
        logger.warning("Rankings refresh failed: %s", e)


def _refresh_events():
    """拉取央视新闻摘要 → 大事日历。"""
    try:
        df = ak.news_cctv(date=None)
        if df is None or df.empty:
            return
        results = []
        for _, row in df.head(5).iterrows():
            title = str(row.get("title", "") or row.get("content", ""))[:20]
            date_str = str(row.get("date", ""))
            if title:
                results.append({
                    "date": date_str[-5:] if len(date_str) >= 5 else date_str,
                    "name": title,
                    "desc": "央视新闻联播要闻",
                })
        if results:
            _set_cache("calendar_events", results)
    except Exception as e:
        logger.warning("Events refresh failed: %s", e)


# ====================================================================
#  公共接口（缓存优先 → 回退模拟）
# ====================================================================

def get_hot_sectors() -> list[dict]:
    cached = _get_cache("hot_sectors")
    if cached:
        return cached

    # 尝试同步拉一次
    try:
        _refresh_hot()
    except Exception:
        pass

    cached = _get_cache("hot_sectors")
    if cached:
        return cached

    # 回退
    fallback = [
        {"name": "AI人工智能", "change": 4.32, "reason": "OpenAI发布新一代推理模型"},
        {"name": "半导体", "change": 3.15, "reason": "国产替代政策加速落地"},
        {"name": "新能源车", "change": 2.87, "reason": "8月销量同比增长45%"},
        {"name": "机器人", "change": -1.23, "reason": "特斯拉Optimus量产推迟"},
        {"name": "低空经济", "change": 5.61, "reason": "多省市发布低空空域开放政策"},
        {"name": "数据要素", "change": 1.98, "reason": "数据资产入表细则出台"},
        {"name": "创新药", "change": -0.76, "reason": "集采范围扩大影响预期"},
        {"name": "光伏", "change": -2.14, "reason": "组件价格持续低迷"},
    ]
    _set_cache("hot_sectors", fallback, error=True)
    return fallback


def get_calendar_events() -> list[dict]:
    cached = _get_cache("calendar_events")
    if cached:
        return cached

    fallback = [
        {"date": "08-15", "name": "美联储议息会议纪要", "desc": "关注降息路径指引"},
        {"date": "08-18", "name": "世界人工智能大会", "desc": "大模型+具身智能"},
        {"date": "08-20", "name": "LPR报价日", "desc": "关注5年期LPR调整"},
        {"date": "08-25", "name": "光伏行业峰会", "desc": "新技术路线与产能"},
        {"date": "08-28", "name": "中报披露截止日", "desc": "业绩暴雷/超预期"},
    ]
    _set_cache("calendar_events", fallback, error=True)
    return fallback


def get_rankings(ranking_type: str | None = None) -> list[dict]:
    cached = _get_cache("rankings_all")
    if cached:
        result = [r for r in cached if not ranking_type or r["title"] == ranking_type]
        return result or cached

    fallback = [
        {"title": "涨幅榜", "desc": "今日涨幅TOP3", "stocks": ["N强邦 +120%", "双成药业 +10%", "华立股份 +10%"]},
        {"title": "营收榜", "desc": "连续5年营收增长", "stocks": ["贵州茅台", "宁德时代", "比亚迪"]},
        {"title": "主力资金榜", "desc": "今日主力净流入TOP", "stocks": ["科大讯飞", "中科曙光", "浪潮信息"]},
        {"title": "行业龙头榜", "desc": "细分行业市占率第一", "stocks": ["海康威视", "恒瑞医药", "迈瑞医疗"]},
    ]
    _set_cache("rankings_all", fallback, error=True)
    return fallback


def get_strategies() -> list[dict]:
    return [
        {"name": "主力控盘低价股战法", "annual": 18.6, "total": 142.3, "drawdown": -15.2},
        {"name": "高股息稳健策略", "annual": 12.4, "total": 89.7, "drawdown": -8.5},
        {"name": "北向资金流入战法", "annual": 15.8, "total": 115.2, "drawdown": -12.1},
    ]
