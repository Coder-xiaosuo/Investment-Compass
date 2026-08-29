#!/usr/bin/env python3
"""历史估值数据回填脚本 — 用 akshare 乐咕乐股接口回填每日 PE/PB/总市值。

akshare 的 stock_a_indicator_lg(symbol) 返回个股历史逐日估值指标
（date, pe, pe_ttm, pb, ps, dv_ratio, dv_ttm, total_mv），本脚本将其
幂等回填到 stock_valuation_daily 表（唯一键 uk_svd_symbol_date，
重复执行不产生重复行），供回测引擎使用历史 PE/PB。

Usage::

    # 回填贵州茅台历史估值
    python scripts/backfill_valuation_history.py --symbol 600519

    # 只解析打印，不写库
    python scripts/backfill_valuation_history.py --symbol 600519 --dry-run
"""

from __future__ import annotations

import argparse
import datetime
import logging
import os
import re
import sys

# 保证包根目录可导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.config import _engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# 单次事务内批量提交的行数
BATCH_SIZE = 200

# 数据来源标记
SOURCE = "akshare_lg"

# INSERT ... ON DUPLICATE KEY UPDATE（唯一键 uk_svd_symbol_date，天然幂等）
_INSERT_SQL = """
    INSERT INTO stock_valuation_daily
        (symbol, trade_date, close_price, pe_ttm, pe_static, pb, ps_ttm,
         market_cap, float_market_cap, turnover_rate, volume_ratio, source)
    VALUES
        (:symbol, :trade_date, NULL, :pe_ttm, NULL, :pb, NULL,
         :market_cap, NULL, NULL, NULL, :source)
    ON DUPLICATE KEY UPDATE
        pe_ttm = VALUES(pe_ttm), pb = VALUES(pb),
        market_cap = VALUES(market_cap), source = VALUES(source)
"""


def _strip_suffix(symbol: str) -> str:
    """把入参统一转成纯数字，取后 6 位（兼容带前缀/后缀的代码）。"""
    digits = re.sub(r"\D", "", symbol)
    return digits[-6:] if len(digits) >= 6 else digits


def _normalize_date(val) -> str | None:
    """把日期列值统一成 YYYY-MM-DD 字符串。"""
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (ValueError, TypeError):
        pass
    if isinstance(val, (datetime.datetime, datetime.date)):
        return val.strftime("%Y-%m-%d")
    # 兼容 "2024-01-02 00:00:00" / "2024/01/02" 等字符串格式
    s = str(val).strip().split(" ")[0].replace("/", "-")
    return s or None


def _safe_float(val) -> float | None:
    """安全转 float：NaN/空值/非数值返回 None。"""
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (ValueError, TypeError):
        pass
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


# 接口列名别名表（列名统一小写并去除空格后匹配）：标准列名 -> 可能的接口列名
# 兼容乐咕乐股（stock_a_indicator_lg）英文列与东方财富（stock_value_em）中文列
_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "trade_date": ("date", "trade_date", "数据日期", "日期"),
    "pe_ttm": ("pe_ttm", "pe(ttm)", "市盈率(ttm)", "市盈率-动态", "市盈率"),
    "pb": ("pb", "市净率"),
    "market_cap": ("total_mv", "market_cap", "总市值"),
}


def _find_column(df: pd.DataFrame, *aliases: str) -> str | None:
    """按别名表查找列（列名已小写化）：先精确匹配，再做包含匹配。"""
    cols = list(df.columns)
    for a in aliases:
        if a in cols:
            return a
    for a in aliases:
        for col in cols:
            if a in col:
                return col
    return None


def _fetch_indicator_df(symbol: str) -> pd.DataFrame:
    """拉取历史逐日估值指标（带全局限流）。

    优先使用乐咕乐股接口 stock_a_indicator_lg（任务指定接口）；
    新版 akshare 已移除该接口，自动回退到东方财富 stock_value_em
    （同样返回历史每日 PE(TTM)/市净率/总市值）。
    """
    import akshare as ak

    from shared.akshare_throttle import throttle

    if hasattr(ak, "stock_a_indicator_lg"):
        throttle()
        return ak.stock_a_indicator_lg(symbol=symbol)
    if hasattr(ak, "stock_value_em"):
        logger.info("当前 akshare 无 stock_a_indicator_lg，回退使用 stock_value_em")
        throttle()
        return ak.stock_value_em(symbol=symbol)
    raise AttributeError(
        "当前 akshare 版本缺少 stock_a_indicator_lg / stock_value_em 接口"
    )


def _parse_indicator_df(df: pd.DataFrame, symbol: str) -> list[dict]:
    """解析接口返回的 DataFrame，生成待入库记录列表。

    兼容列名：列名统一小写化（去除空格）后按别名表匹配
    date/trade_date、pe_ttm、pb、total_mv/总市值。
    """
    if df is None or df.empty:
        return []

    # 列名统一小写化并去除空格，方便按别名匹配（中文列名不受影响）
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "") for c in df.columns]

    date_col = _find_column(df, *_COLUMN_ALIASES["trade_date"])
    pe_ttm_col = _find_column(df, *_COLUMN_ALIASES["pe_ttm"])
    pb_col = _find_column(df, *_COLUMN_ALIASES["pb"])
    mv_col = _find_column(df, *_COLUMN_ALIASES["market_cap"])

    if date_col is None:
        raise ValueError(f"接口返回缺少日期列，实际列: {list(df.columns)}")

    records: list[dict] = []
    for _, row in df.iterrows():
        trade_date = _normalize_date(row.get(date_col))
        if not trade_date:
            continue

        pe_ttm = _safe_float(row.get(pe_ttm_col)) if pe_ttm_col else None
        pb = _safe_float(row.get(pb_col)) if pb_col else None
        market_cap = _safe_float(row.get(mv_col)) if mv_col else None

        # 三个核心数值均为空的行没有回填价值，跳过
        if pe_ttm is None and pb is None and market_cap is None:
            continue

        records.append({
            "symbol": symbol,
            "trade_date": trade_date,
            "pe_ttm": pe_ttm,
            "pb": pb,
            "market_cap": market_cap,
            "source": SOURCE,
        })
    return records


def _backfill(records: list[dict], dry_run: bool = False) -> tuple[int, int]:
    """批量写入 stock_valuation_daily，返回 (成功行数, 失败行数)。

    每 BATCH_SIZE 行提交一次；dry_run 时不执行 SQL。
    """
    session = Session(_engine)
    inserted = 0
    failed = 0
    try:
        for i in range(0, len(records), BATCH_SIZE):
            batch = records[i:i + BATCH_SIZE]
            if dry_run:
                inserted += len(batch)
                continue
            for rec in batch:
                try:
                    session.execute(text(_INSERT_SQL), rec)
                    inserted += 1
                except Exception as exc:
                    failed += 1
                    logger.warning(
                        "写入失败: symbol=%s, trade_date=%s, error=%s",
                        rec["symbol"], rec["trade_date"], exc,
                    )
            session.commit()
    except Exception as exc:
        session.rollback()
        raise
    finally:
        session.close()
    return inserted, failed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="回填个股历史每日估值（PE/PB/总市值）到 stock_valuation_daily",
    )
    parser.add_argument("--symbol", required=True, help="6 位数字股票代码，如 600519")
    parser.add_argument("--dry-run", action="store_true", help="只解析打印，不写入数据库")
    args = parser.parse_args()

    symbol = _strip_suffix(args.symbol)
    if len(symbol) != 6 or not symbol.isdigit():
        logger.error("无效股票代码: %s（需为 6 位数字）", args.symbol)
        return 2

    # 拉取 akshare 数据（网络失败打 error 日志并返回非零退出码）
    try:
        logger.info("拉取 %s 历史估值指标（乐咕乐股）...", symbol)
        df = _fetch_indicator_df(symbol)
    except Exception as exc:
        logger.error("akshare 拉取失败: symbol=%s, error=%s", symbol, exc)
        return 1

    if df is None or df.empty:
        logger.error("akshare 返回空数据: symbol=%s", symbol)
        return 1

    try:
        records = _parse_indicator_df(df, symbol)
    except Exception as exc:
        logger.error("解析接口数据失败: symbol=%s, error=%s", symbol, exc)
        return 1

    if not records:
        logger.warning("无有效记录可回填: symbol=%s", symbol)
        return 0

    logger.info("拉取 %d 行，其中 %d 行有效", len(df), len(records))

    if args.dry_run:
        # dry-run：只打印样例，不写库
        logger.info("[dry-run] 将写入 %d 行（不写库），样例：", len(records))
        for rec in records[:3]:
            logger.info(
                "  %s  pe_ttm=%s  pb=%s  market_cap=%s",
                rec["trade_date"], rec["pe_ttm"], rec["pb"], rec["market_cap"],
            )
        return 0

    try:
        inserted, failed = _backfill(records, dry_run=False)
    except Exception as exc:
        logger.error("写库失败: %s", exc)
        return 1

    logger.info(
        "回填完成: symbol=%s, 拉取=%d, 写入=%d, 失败=%d",
        symbol, len(records), inserted, failed,
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
