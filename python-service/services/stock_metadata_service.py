"""Stock metadata service — 品种注册与管理。"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import text

from shared.config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_recycle=settings.DATABASE_POOL_RECYCLE,
    pool_timeout=30,
)


def _session() -> Session:
    return Session(_engine)


def _strip_suffix(symbol: str) -> str:
    digits = re.sub(r"\D", "", symbol)
    return digits[-6:] if len(digits) >= 6 else digits


def ensure_stock_metadata(symbol: str) -> None:
    session = _session()
    try:
        existing = session.execute(
            text("SELECT id FROM stock_metadata WHERE symbol = :sym"),
            {"sym": symbol},
        ).fetchone()
        if existing:
            return
        stock_name = symbol
        try:
            import akshare as ak
            code = _strip_suffix(symbol)
            df = ak.stock_individual_info_em(symbol=code)
            if df is not None and not df.empty:
                item_col = "item" if "item" in df.columns else df.columns[0]
                val_col = "value" if "value" in df.columns else df.columns[1]
                for item, val in zip(df[item_col], df[val_col], strict=False):
                    if str(item).strip() in ("股票简称", "名称"):
                        stock_name = str(val)
                        break
        except Exception:
            pass
        session.execute(
            text("""
                INSERT INTO stock_metadata (symbol, stock_name, type, source)
                VALUES (:sym, :name, 'STOCK', 'akshare')
                ON DUPLICATE KEY UPDATE stock_name = VALUES(stock_name)
            """),
            {"sym": symbol, "name": stock_name},
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def list_all_symbols() -> list[dict[str, str]]:
    """列出元数据库中全部股票（type='STOCK'，按代码排序）。"""
    session = _session()
    try:
        rows = session.execute(
            text("""
                SELECT symbol, stock_name FROM stock_metadata
                WHERE type = 'STOCK' ORDER BY symbol
            """)
        ).fetchall()
        return [{"symbol": r.symbol, "stockName": r.stock_name} for r in rows]
    finally:
        session.close()


def search_stocks(keyword: str, limit: int = 10) -> list[dict[str, str]]:
    session = _session()
    try:
        pattern = f"%{keyword}%"
        rows = session.execute(
            text("""
                SELECT symbol, stock_name FROM stock_metadata
                WHERE symbol LIKE :kw OR stock_name LIKE :kw
                LIMIT :lim
            """),
            {"kw": pattern, "lim": limit},
        ).fetchall()
        return [{"symbol": r.symbol, "stockName": r.stock_name} for r in rows]
    finally:
        session.close()


def init_metadata() -> dict[str, Any]:
    import akshare as ak

    session = _session()
    try:
        # 优先东财接口，失败后回退新浪接口
        df = None
        source_name = ""
        try:
            df = ak.stock_zh_a_spot_em()
            source_name = "东财"
        except Exception as exc:
            logger.warning("stock_zh_a_spot_em failed, fallback to sina: %s", exc)
            df = ak.stock_zh_a_spot()
            source_name = "新浪"

        if df is None or df.empty:
            return {"total_count": 0, "success_count": 0, "failed_count": 0}

        total_count = 0
        success_count = 0
        failed_count = 0
        failed_symbols: list[str] = []

        for _, row in df.iterrows():
            total_count += 1
            try:
                raw_code = str(row.get("代码", row.get("symbol", ""))).strip()
                # 新浪接口代码带前缀（如 sh600000, sz000001, bj920000），提取纯6位数字
                code_digits = re.sub(r"\D", "", raw_code)
                symbol = code_digits[-6:] if len(code_digits) >= 6 else code_digits
                if not symbol or len(symbol) != 6:
                    failed_count += 1
                    continue

                stock_name = str(row.get("名称", row.get("name", row.get("股票名称", "")))).strip()
                if not stock_name:
                    failed_count += 1
                    continue

                stock_type = "STOCK"
                if symbol in ("000300", "000016", "000905", "399001", "399006"):
                    stock_type = "INDEX"

                session.execute(
                    text("""
                        INSERT INTO stock_metadata (symbol, stock_name, type, source)
                        VALUES (:sym, :name, :type, 'akshare')
                        ON DUPLICATE KEY UPDATE
                            stock_name = VALUES(stock_name),
                            type = VALUES(type),
                            updated_at = NOW()
                    """),
                    {"sym": symbol, "name": stock_name, "type": stock_type},
                )
                success_count += 1
            except Exception as exc:
                failed_count += 1
                failed_symbols.append(f"{symbol}: {exc}")

        session.commit()
        logger.info("init_metadata via %s: %d success, %d failed", source_name, success_count, failed_count)

        result = {
            "total_count": total_count,
            "success_count": success_count,
            "failed_count": failed_count,
            "source": source_name,
        }
        if failed_symbols:
            result["failed_symbols"] = failed_symbols[:20]
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ── L2: 上市/退市日期（K线完整性审计基准）────────────────────────────────────

def _to_date(value: Any) -> Optional[date]:
    """归一化交易所列表中的日期值（兼容 date / datetime / 'YYYY-MM-DD' / 'YYYYMMDD'）。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    digits = re.sub(r"\D", "", str(value).strip())
    if len(digits) >= 8:
        try:
            return date(int(digits[0:4]), int(digits[4:6]), int(digits[6:8]))
        except ValueError:
            return None
    return None


def _fetch_exchange_list_dates() -> dict[str, date]:
    """批量拉取沪深北交易所列表 → {6位代码: 上市日期}。

    三次调用（沪 1701 / 深 2901 / 北 343 行）合计约 16s，覆盖全市场，
    用于区分"未上市"与"漏拉"。
    """
    import akshare as ak

    result: dict[str, date] = {}

    def _put(raw_code: Any, raw_date: Any) -> None:
        digits = re.sub(r"\D", "", str(raw_code or ""))
        code = digits[-6:] if len(digits) >= 6 else digits
        if len(code) != 6:
            return
        d = _to_date(raw_date)
        if d:
            result[code] = d

    fetchers = [
        # 沪市需分别拉主板A股与科创板：默认调用只返回主板（1701 行），
        # 会漏掉 616 只 688xxx，导致它们被误判为"无上市日期"而进审计黑洞
        ("stock_info_sh_name_code(主板A股)",
         ("证券代码", "上市日期"),
         lambda: ak.stock_info_sh_name_code(symbol="主板A股")),
        ("stock_info_sh_name_code(科创板)",
         ("证券代码", "上市日期"),
         lambda: ak.stock_info_sh_name_code(symbol="科创板")),
        ("stock_info_sz_name_code",
         ("A股代码", "A股上市日期"),
         lambda: ak.stock_info_sz_name_code(symbol="A股列表")),
        ("stock_info_bj_name_code",
         ("证券代码", "上市日期"),
         lambda: ak.stock_info_bj_name_code()),
    ]
    for name, (code_col, date_col), fn in fetchers:
        try:
            df = fn()
            if df is None or df.empty:
                logger.warning("交易所列表 %s 返回空", name)
                continue
            for _, row in df.iterrows():
                _put(row.get(code_col), row.get(date_col))
            logger.info("交易所列表 %s: %d 条", name, len(df))
        except Exception as exc:
            logger.warning("交易所列表 %s 拉取失败: %s", name, exc)

    return result


def sync_list_dates() -> dict[str, Any]:
    """同步上市日期到 stock_metadata.list_date（L2 审计基准）。

    仅写 list_date。delist_date 需退市数据源，接口只返回在市标的，
    故不由此推断（避免臆造），保留 NULL 待接入退市源。

    Returns:
        统计信息，含 fetched / updated / not_in_exchange（在市列表未找到的 STOCK）。
    """
    list_dates = _fetch_exchange_list_dates()
    if not list_dates:
        raise RuntimeError("交易所列表全部拉取失败，未更新 list_date")

    session = _session()
    try:
        params = [{"sym": sym, "d": d} for sym, d in list_dates.items()]
        session.execute(
            text("""
                UPDATE stock_metadata
                SET list_date = :d
                WHERE symbol = :sym AND (list_date IS NULL OR list_date <> :d)
            """),
            params,
        )
        session.commit()

        updated = session.execute(
            text("SELECT COUNT(*) FROM stock_metadata WHERE list_date IS NOT NULL")
        ).scalar() or 0

        not_in_exchange = session.execute(
            text("""
                SELECT COUNT(*) FROM stock_metadata
                WHERE type = 'STOCK' AND list_date IS NULL
            """)
        ).scalar() or 0

        result = {
            "fetched": len(list_dates),
            "with_list_date": int(updated),
            "stock_without_list_date": int(not_in_exchange),
        }
        logger.info(
            "上市日期同步完成：交易所返回 %d 条，库内已有 list_date %d 只，STOCK 中缺失 %d 只",
            result["fetched"], result["with_list_date"], result["stock_without_list_date"],
        )
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
