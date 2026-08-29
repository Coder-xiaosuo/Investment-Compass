"""Stock metadata service — 品种注册与管理。"""
from __future__ import annotations

import logging
import re
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
