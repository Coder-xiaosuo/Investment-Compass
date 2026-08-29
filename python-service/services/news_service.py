"""新闻/资讯/研报服务 — DB CRUD + 增量同步。

遵循与 financial_data_service.py 相同的模式：
- DB miss → 自动从 AkShare 拉取（live fetch）→ 写入 → 返回
- sync_* 接口：全量/增量同步（触发 AkShare 拉取 + 写入 DB，返回条数统计）
- list_* 接口：纯 DB 查询（按条件返回结构化列表）
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import desc, or_, text

from shared.config import _engine
from shared.models import ResearchReport as DBResearchReport
from shared.models import StockNews as DBStockNews
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_CN_TZ = ZoneInfo("Asia/Shanghai")

_news_source = None


def _get_news_source():
    """懒初始化 NewsSource。"""
    global _news_source
    if _news_source is None:
        from data_source.news_source import NewsSource
        _news_source = NewsSource()
        _news_source.connect()
    return _news_source


def _strip_symbol_suffix(symbol: str) -> str:
    digits = re.sub(r"\D", "", symbol or "")
    return digits[-6:] if len(digits) >= 6 else digits


def _session() -> Session:
    return Session(_engine)


# ====================================================================
#  StockNews  — 查询
# ====================================================================

def list_news(
    symbol: str | None = None,
    source: str | None = None,
    days: int = 7,
    limit: int = 100,
    live_fetch: bool = True,
) -> list[dict[str, Any]]:
    """查询新闻列表。

    Args:
        symbol: 股票代码过滤（支持 6 位 / 带前缀后缀）；None=不过滤，返回全市场+个股混排
        source: 'em_news' / 'cls_telegraph' / 'em_global'；None=全部
        days: 只查最近 N 天（限制查询范围，避免全表扫描）
        limit: 返回条数上限
        live_fetch: DB 数据不足时是否触发 AkShare 实时拉取后再查
    """
    code = _strip_symbol_suffix(symbol) if symbol else ""
    min_time = datetime.now(tz=_CN_TZ) - timedelta(days=days)

    # Step 1: DB 查询
    with _session() as s:
        q = s.query(DBStockNews).filter(DBStockNews.publish_time >= min_time.replace(tzinfo=None))
        if code:
            q = q.filter(or_(DBStockNews.symbol == code, DBStockNews.symbol == None))  # noqa: E711
        if source:
            q = q.filter(DBStockNews.source == source)
        q = q.order_by(desc(DBStockNews.publish_time)).limit(limit)
        rows = q.all()

        if rows:
            return [_news_row_to_dict(r) for r in rows]

    # Step 2: DB 空 → 按需 live fetch（整体限时，超时快速降级，避免接口长时间阻塞）
    if not live_fetch:
        return []
    try:
        from shared.akshare_throttle import run_with_timeout

        def _do_live_fetch() -> int:
            ns = _get_news_source()
            w = 0
            # 指定了 symbol → 先拉个股新闻
            if code:
                w += sync_stock_news(code)
            # 没指定 symbol 或 明确要全市场快讯 → 拉财联社电报
            if (not code and source in (None, "cls_telegraph")) or source == "cls_telegraph":
                w += sync_global_telegraph()
            # 没指定 symbol 或 明确要全球资讯 → 拉东方财富全球资讯
            if (not code and source in (None, "em_global")) or source == "em_global":
                w += sync_global_news_em()
            return w

        written = run_with_timeout(_do_live_fetch, 15.0)
        if written > 0:
            # 写进去了，再查一次
            return list_news(symbol=symbol, source=source, days=days, limit=limit, live_fetch=False)
    except Exception as exc:
        logger.warning("list_news live fetch failed or timed out: %s", exc)
    return []


def _news_row_to_dict(r: DBStockNews) -> dict[str, Any]:
    return {
        "id": r.id,
        "source": r.source,
        "symbol": r.symbol,
        "title": r.title,
        "content": r.content,
        "publish_time": r.publish_time.strftime("%Y-%m-%d %H:%M:%S") if r.publish_time else None,
        "url": r.url,
        "source_name": r.source_name,
        "fetched_at": r.fetched_at.strftime("%Y-%m-%d %H:%M:%S") if r.fetched_at else None,
    }


# ====================================================================
#  ResearchReport — 查询
# ====================================================================

def list_research_reports(
    symbol: str | None = None,
    institute: str | None = None,
    rating: str | None = None,
    days: int = 90,
    limit: int = 200,
    live_fetch: bool = True,
) -> list[dict[str, Any]]:
    """查询券商研报列表。

    Args:
        symbol: 股票代码过滤；None=全部
        institute: 机构名过滤（模糊匹配）
        rating: '买入' / '增持' / '中性' / '减持' / '卖出'
        days: 只查最近 N 天
        limit: 返回条数上限
        live_fetch: DB 空时是否触发 AkShare 拉取
    """
    code = _strip_symbol_suffix(symbol) if symbol else ""
    min_date = datetime.combine(
        (datetime.now(tz=_CN_TZ) - timedelta(days=days)).date(),
        datetime.min.time(),
    )

    with _session() as s:
        q = s.query(DBResearchReport).filter(DBResearchReport.publish_date >= min_date)
        if code:
            q = q.filter(DBResearchReport.symbol == code)
        if institute:
            q = q.filter(DBResearchReport.institute.like(f"%{institute}%"))
        if rating:
            q = q.filter(DBResearchReport.rating == rating)
        q = q.order_by(desc(DBResearchReport.publish_date)).limit(limit)
        rows = q.all()

        if rows:
            return [_rr_row_to_dict(r) for r in rows]

    if not live_fetch:
        return []
    try:
        from shared.akshare_throttle import run_with_timeout
        written = run_with_timeout(lambda: sync_research_reports(code), 15.0)
        if written > 0:
            return list_research_reports(symbol=symbol, institute=institute, rating=rating, days=days, limit=limit, live_fetch=False)
    except Exception as exc:
        logger.warning("list_research_reports live fetch failed or timed out: %s", exc)
    return []


def _rr_row_to_dict(r: DBResearchReport) -> dict[str, Any]:
    return {
        "id": r.id,
        "symbol": r.symbol,
        "stock_name": r.stock_name,
        "title": r.title,
        "institute": r.institute,
        "analyst": r.analyst,
        "rating": r.rating,
        "target_price": float(r.target_price) if r.target_price is not None else None,
        "eps_2025": float(r.eps_2025) if r.eps_2025 is not None else None,
        "eps_2026": float(r.eps_2026) if r.eps_2026 is not None else None,
        "eps_2027": float(r.eps_2027) if r.eps_2027 is not None else None,
        "eps_2028": float(r.eps_2028) if r.eps_2028 is not None else None,
        "pe_2025": float(r.pe_2025) if r.pe_2025 is not None else None,
        "pe_2026": float(r.pe_2026) if r.pe_2026 is not None else None,
        "pe_2027": float(r.pe_2027) if r.pe_2027 is not None else None,
        "publish_date": r.publish_date.strftime("%Y-%m-%d") if r.publish_date else None,
        "pdf_url": r.pdf_url,
        "fetched_at": r.fetched_at.strftime("%Y-%m-%d %H:%M:%S") if r.fetched_at else None,
    }


# ====================================================================
#  同步接口（写入 DB，返回写入条数）
# ====================================================================

def sync_stock_news(symbol: str) -> int:
    """同步某只股票的新闻（AkShare → DB，幂等：冲突键 do update/do nothing）。"""
    code = _strip_symbol_suffix(symbol)
    if not code:
        raise ValueError(f"无效 symbol: {symbol!r}")
    ns = _get_news_source()
    items = ns.get_stock_news(code)
    if not items:
        return 0
    rows = [
        {
            "source": it.source,
            "symbol": it.symbol,
            "title": it.title,
            "content": it.content,
            "publish_time": it.publish_time.replace(tzinfo=None),
            "url": it.url,
            "source_name": it.source_name,
            "fetched_at": datetime.utcnow(),
        }
        for it in items
    ]
    return _bulk_upsert_news(rows)


def sync_global_telegraph() -> int:
    """同步财联社 7×24 电报。"""
    ns = _get_news_source()
    items = ns.get_global_telegraph()
    if not items:
        return 0
    rows = [
        {
            "source": it.source,
            "symbol": it.symbol,
            "title": it.title,
            "content": it.content,
            "publish_time": it.publish_time.replace(tzinfo=None),
            "url": it.url,
            "source_name": it.source_name,
            "fetched_at": datetime.utcnow(),
        }
        for it in items
    ]
    return _bulk_upsert_news(rows)


def sync_global_news_em() -> int:
    """同步东方财富全球财经资讯。"""
    ns = _get_news_source()
    items = ns.get_global_news_em()
    if not items:
        return 0
    rows = [
        {
            "source": it.source,
            "symbol": it.symbol,
            "title": it.title,
            "content": it.content,
            "publish_time": it.publish_time.replace(tzinfo=None),
            "url": it.url,
            "source_name": it.source_name,
            "fetched_at": datetime.utcnow(),
        }
        for it in items
    ]
    return _bulk_upsert_news(rows)


def sync_research_reports(symbol: str | None = None) -> int:
    """同步券商研报；symbol 指定则只同步该只股票的。"""
    code = _strip_symbol_suffix(symbol) if symbol else None
    ns = _get_news_source()
    # 全量同步时拉2000条覆盖6xxxx股票；指定symbol时NewsSource内部自动放大到3000
    fetch_limit = 2000 if not code else 500
    items = ns.get_research_reports(symbol=code, limit=fetch_limit)
    if not items:
        return 0
    rows = [
        {
            "symbol": it.symbol,
            "stock_name": it.stock_name,
            "title": it.title,
            "institute": it.institute,
            "analyst": None,
            "rating": it.rating,
            "target_price": None,
            "eps_2026": it.eps_2026,
            "eps_2027": it.eps_2027,
            "eps_2028": it.eps_2028,
            "pe_2026": it.pe_2026,
            "pe_2027": it.pe_2027,
            "publish_date": datetime.combine(it.publish_date, datetime.min.time()),
            "pdf_url": it.pdf_url,
            "fetched_at": datetime.utcnow(),
        }
        for it in items
    ]
    return _bulk_upsert_reports(rows)


def sync_all_news(symbols: list[str] | None = None) -> dict[str, int]:
    """一键同步所有资讯来源。

    Args:
        symbols: 指定要同步个股新闻的股票代码列表；None 则只同步全市场资讯+研报

    Returns:
        { 'stock_news': N, 'telegraph': N, 'global_news': N, 'research_reports': N }
    """
    stats: dict[str, int] = {
        "stock_news": 0,
        "telegraph": 0,
        "global_news": 0,
        "research_reports": 0,
    }
    try:
        stats["telegraph"] = sync_global_telegraph()
    except Exception as exc:
        logger.error("sync telegraph failed: %s", exc)
    try:
        stats["global_news"] = sync_global_news_em()
    except Exception as exc:
        logger.error("sync global_news failed: %s", exc)
    try:
        stats["research_reports"] = sync_research_reports()
    except Exception as exc:
        logger.error("sync research_reports failed: %s", exc)
    if symbols:
        for sym in symbols:
            try:
                stats["stock_news"] += sync_stock_news(sym)
            except Exception as exc:
                logger.error("sync stock_news %s failed: %s", sym, exc)
    return stats


# ====================================================================
#  内部 upsert 实现（原生 SQL，与 market_data_service.py / financial_data_service.py 风格一致）
# ====================================================================

_NEWS_COLUMNS = [
    "source", "symbol", "title", "content", "publish_time",
    "url", "source_name", "fetched_at",
]


def _bulk_upsert_news(rows: list[dict[str, Any]]) -> int:
    """批量写入/更新新闻。使用 MySQL INSERT ... ON DUPLICATE KEY UPDATE。"""
    if not rows:
        return 0
    cols = _NEWS_COLUMNS
    placeholders = ", ".join(f":{c}" for c in cols)
    update_parts = [f"{c} = VALUES({c})" for c in cols if c not in ("source", "publish_time", "title")]
    update_sql = ", ".join(update_parts)
    sql = text(f"""
        INSERT INTO stock_news ({', '.join(cols)})
        VALUES ({placeholders})
        ON DUPLICATE KEY UPDATE {update_sql}
    """)
    s = _session()
    written = 0
    try:
        for r in rows:
            try:
                s.execute(sql, {c: r.get(c) for c in cols})
                written += 1
            except Exception as exc:
                logger.warning("news insert skip: %s", exc)
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
    logger.info("stock_news upsert: %d written (out of %d fetched)", written, len(rows))
    return written


_RR_COLUMNS = [
    "symbol", "stock_name", "title", "institute", "analyst", "rating",
    "target_price", "eps_2025", "eps_2026", "eps_2027", "eps_2028",
    "pe_2025", "pe_2026", "pe_2027", "publish_date", "pdf_url", "fetched_at",
]


def _bulk_upsert_reports(rows: list[dict[str, Any]]) -> int:
    """批量写入/更新研报。"""
    if not rows:
        return 0
    cols = _RR_COLUMNS
    placeholders = ", ".join(f":{c}" for c in cols)
    update_parts = [f"{c} = VALUES({c})" for c in cols
                    if c not in ("symbol", "institute", "publish_date", "title")]
    update_sql = ", ".join(update_parts)
    sql = text(f"""
        INSERT INTO research_reports ({', '.join(cols)})
        VALUES ({placeholders})
        ON DUPLICATE KEY UPDATE {update_sql}
    """)
    s = _session()
    written = 0
    try:
        for r in rows:
            try:
                s.execute(sql, {c: r.get(c) for c in cols})
                written += 1
            except Exception as exc:
                logger.warning("research_report insert skip: %s", exc)
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
    logger.info("research_reports upsert: %d written (out of %d fetched)", written, len(rows))
    return written
