"""Valuation service — 个股估值数据获取与同步。"""
from __future__ import annotations

import logging
import re
import time
from datetime import date
from typing import Any, Optional

from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.config import settings

logger = logging.getLogger(__name__)

_engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_recycle=settings.DATABASE_POOL_RECYCLE,
    pool_timeout=30,
)

# 东方财富实时行情全量缓存（避免频繁调用被限流）
_EM_SPOT_CACHE: Optional[dict] = None
_EM_SPOT_CACHE_TS: float = 0.0
_EM_SPOT_CACHE_TTL = 60  # 缓存有效期（秒）


def _session() -> Session:
    return Session(_engine)


def _strip_suffix(symbol: str) -> str:
    digits = re.sub(r"\D", "", symbol)
    return digits[-6:] if len(digits) >= 6 else digits


def _row_to_dict(row) -> dict[str, Any]:
    if row is None:
        return {}
    return {
        "symbol": row.symbol,
        "trade_date": str(row.trade_date) if row.trade_date is not None else None,
        "close_price": float(row.close_price) if row.close_price is not None else None,
        "pe_ttm": float(row.pe_ttm) if row.pe_ttm is not None else None,
        "pe_static": float(row.pe_static) if row.pe_static is not None else None,
        "pb": float(row.pb) if row.pb is not None else None,
        "ps_ttm": float(row.ps_ttm) if row.ps_ttm is not None else None,
        "market_cap": float(row.market_cap) if row.market_cap is not None else None,
        "float_market_cap": float(row.float_market_cap) if row.float_market_cap is not None else None,
        "turnover_rate": float(row.turnover_rate) if row.turnover_rate is not None else None,
        "volume_ratio": float(row.volume_ratio) if row.volume_ratio is not None else None,
        "source": row.source if row.source else None,
    }


def _fetch_from_sina(symbol: str) -> dict[str, Any]:
    """从新浪接口获取实时行情（可靠但仅有基础价格字段）。"""
    import akshare as ak

    from shared.akshare_throttle import throttle

    code = _strip_suffix(symbol)
    throttle()
    df = ak.stock_zh_a_spot()
    if df is None or df.empty:
        return {}

    for _, row in df.iterrows():
        raw_code = str(row.get("代码", "")).strip()
        code_digits = re.sub(r"\D", "", raw_code)
        if code_digits[-6:] == code:
            try:
                close_price = float(row.get("最新价", 0))
            except (ValueError, TypeError):
                close_price = None

            return {
                "symbol": code,
                "trade_date": date.today().isoformat(),
                "close_price": close_price,
                "pe_ttm": None,
                "pe_static": None,
                "pb": None,
                "ps_ttm": None,
                "market_cap": None,
                "float_market_cap": None,
                "turnover_rate": None,
                "volume_ratio": None,
                "source": "akshare_sina",
            }
    return {}


def _fetch_from_em(symbol: str) -> dict[str, Any]:
    """从东方财富接口获取实时行情（数据丰富，使用缓存避免限流）。"""
    global _EM_SPOT_CACHE, _EM_SPOT_CACHE_TS
    import akshare as ak

    from shared.akshare_throttle import throttle

    code = _strip_suffix(symbol)
    now = time.time()

    # 缓存有效期内重用
    if _EM_SPOT_CACHE is not None and (now - _EM_SPOT_CACHE_TS) < _EM_SPOT_CACHE_TTL:
        df = _EM_SPOT_CACHE
    else:
        try:
            throttle()
            df = ak.stock_zh_a_spot_em()
        except Exception as exc:
            logger.warning("EM 实时行情请求失败: %s，尝试使用缓存", exc)
            if _EM_SPOT_CACHE is not None:
                df = _EM_SPOT_CACHE
            else:
                return {}
        if df is None or df.empty:
            return {}
        _EM_SPOT_CACHE = df
        _EM_SPOT_CACHE_TS = now

    if df is None or df.empty:
        return {}

    for _, row in df.iterrows():
        raw_code = str(row.get("代码", "")).strip()
        code_digits = re.sub(r"\D", "", raw_code)
        if code_digits[-6:] == code:
            def _safe_float(val):
                if val is None:
                    return None
                try:
                    v = float(str(val).strip())
                    return v
                except (ValueError, TypeError):
                    return None

            return {
                "symbol": code,
                "trade_date": date.today().isoformat(),
                "close_price": _safe_float(row.get("最新价")),
                "pe_ttm": _safe_float(row.get("市盈率-动态")),
                "pe_static": None,
                "pb": _safe_float(row.get("市净率")),
                "ps_ttm": None,
                "market_cap": _safe_float(row.get("总市值")),
                "float_market_cap": _safe_float(row.get("流通市值")),
                "turnover_rate": _safe_float(row.get("换手率")),
                "volume_ratio": _safe_float(row.get("量比")),
                "source": "akshare_em",
            }
    return {}


def _fetch_live(symbol: str) -> dict[str, Any]:
    """尝试从实时接口获取估值数据，优先东方财富（含 PE/PB），失败后回退新浪。"""
    data = _fetch_from_em(symbol)
    if data and data.get("pe_ttm") is not None:
        return data
    # EM 无数据或缺少 PE/PB，合并新浪基础数据
    sina_data = _fetch_from_sina(symbol)
    if not sina_data:
        # EM 有数据但缺 PE/PB，用 EM
        if data:
            return data
        logger.error("所有实时接口均未返回 %s 的数据", symbol)
        return {}
    # 合并：sina 为基础，EM 补充 PE/PB
    if data:
        for key in ("pe_ttm", "pb", "ps_ttm", "market_cap", "float_market_cap",
                     "turnover_rate", "volume_ratio"):
            if data.get(key) is not None:
                sina_data[key] = data[key]
        sina_data["source"] = "akshare_merged"
    return sina_data


def get_valuation(symbol: str, as_of: Any = None) -> dict[str, Any]:
    """获取指定标的的估值数据（在线模式实时优先，回测模式仅查表）。

    在线模式（as_of 为空）：
      - DB 已有近 3 个自然日内的记录视为"实时"，直接返回（新鲜度短路，避免限流）；
      - DB 无记录 / 陈旧 → 从实时接口多源拉取（东财优先、新浪兜底），
        成功则写入 DB 后返回；实时拉取失败 → 降级返回 DB 旧记录。
    回测模式（as_of 指定）：仅查 DB 历史数据，绝不触发实时拉取（防未来函数）。
    """
    code = _strip_suffix(symbol)
    session = _session()
    try:
        if as_of is None:
            row = session.execute(
                text("""
                    SELECT symbol, trade_date, close_price, pe_ttm, pe_static, pb,
                           ps_ttm, market_cap, float_market_cap, turnover_rate,
                           volume_ratio, source
                    FROM stock_valuation_daily
                    WHERE symbol = :sym
                    ORDER BY trade_date DESC
                    LIMIT 1
                """),
                {"sym": code},
            ).fetchone()

            # 新鲜度短路：DB 记录在近 3 个自然日内 → 视为实时，直接返回
            if row and _row_fresh(row.trade_date):
                return _row_to_dict(row)

            # DB 无数据 / 陈旧 → 实时多源拉取（东财 → 新浪）
            logger.info("估值数据需更新（%s），尝试实时多源拉取", symbol)
            fresh = _fetch_live(code)
            if fresh:
                try:
                    _persist_valuation(code, fresh)
                except Exception as exc:
                    logger.warning("估值数据入库失败 %s（不影响返回）: %s", symbol, exc)
                return fresh

            # 实时拉取失败 → 降级返回 DB 旧记录（保证诊断可用）
            if row:
                logger.warning("估值实时拉取失败 %s，降级返回 DB 缓存", symbol)
                return _row_to_dict(row)
            return {}

        # as_of 分支：仅查 DB 历史数据，不触发实时拉取
        as_of_date = as_of if isinstance(as_of, date) else date.fromisoformat(str(as_of))
        row = session.execute(
            text("""
                SELECT symbol, trade_date, close_price, pe_ttm, pe_static, pb,
                       ps_ttm, market_cap, float_market_cap, turnover_rate,
                       volume_ratio, source
                FROM stock_valuation_daily
                WHERE symbol = :sym AND trade_date <= :as_of
                ORDER BY trade_date DESC
                LIMIT 1
            """),
            {"sym": code, "as_of": as_of_date},
        ).fetchone()

        return _row_to_dict(row)
    except Exception as exc:
        logger.error("获取 %s 估值数据失败: %s", symbol, exc)
        return {}
    finally:
        session.close()


def _row_fresh(trade_date: Any, max_age_days: int = 3) -> bool:
    """估值记录是否新鲜：trade_date 距今 <= max_age_days 自然日。"""
    try:
        from datetime import datetime

        if trade_date is None:
            return False
        td = trade_date if isinstance(trade_date, date) else date.fromisoformat(str(trade_date))
        return (datetime.now().date() - td).days <= max_age_days
    except Exception:
        return False


def _persist_valuation(symbol: str, data: dict[str, Any]) -> bool:
    """将实时估值数据写入 stock_valuation_daily 表。"""
    code = _strip_suffix(symbol)
    session = _session()
    try:
        session.execute(
            text("""
                INSERT INTO stock_valuation_daily
                    (symbol, trade_date, close_price, pe_ttm, pe_static, pb,
                     ps_ttm, market_cap, float_market_cap, turnover_rate,
                     volume_ratio, source)
                VALUES
                    (:sym, :trade_date, :close_price, :pe_ttm, :pe_static, :pb,
                     :ps_ttm, :market_cap, :float_market_cap, :turnover_rate,
                     :volume_ratio, :source)
                ON DUPLICATE KEY UPDATE
                    close_price      = VALUES(close_price),
                    pe_ttm           = VALUES(pe_ttm),
                    pe_static        = VALUES(pe_static),
                    pb               = VALUES(pb),
                    ps_ttm           = VALUES(ps_ttm),
                    market_cap       = VALUES(market_cap),
                    float_market_cap = VALUES(float_market_cap),
                    turnover_rate    = VALUES(turnover_rate),
                    volume_ratio     = VALUES(volume_ratio),
                    source           = VALUES(source)
            """),
            {
                "sym": code,
                "trade_date": data["trade_date"],
                "close_price": data["close_price"],
                "pe_ttm": data["pe_ttm"],
                "pe_static": data["pe_static"],
                "pb": data["pb"],
                "ps_ttm": data["ps_ttm"],
                "market_cap": data["market_cap"],
                "float_market_cap": data["float_market_cap"],
                "turnover_rate": data["turnover_rate"],
                "volume_ratio": data["volume_ratio"],
                "source": data["source"],
            },
        )
        session.commit()
        logger.info("已同步 %s 的估值数据（来源: %s）", symbol, data["source"])
        return True
    except Exception as exc:
        session.rollback()
        logger.error("同步 %s 估值数据失败: %s", symbol, exc)
        return False
    finally:
        session.close()


def sync_valuation(symbol: str) -> bool:
    """获取实时估值数据并写入 DB。

    Returns:
        True 表示写入成功，False 表示失败。
    """
    code = _strip_suffix(symbol)
    data = _fetch_live(code)
    if not data:
        logger.error("无法获取 %s 的实时估值数据，同步终止", symbol)
        return False

    return _persist_valuation(code, data)
