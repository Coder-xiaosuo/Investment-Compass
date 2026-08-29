#!/usr/bin/env python3
"""全量历史数据回填脚本。

分批处理 5527 只 A 股，支持断点续传。
每批 50 只，并发 2，年份范围 2020-2024。
"""
import os
import sys
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import sync_service as sync_svc
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from shared.config import settings

engine = create_engine(settings.DATABASE_URL)


def get_all_symbols() -> list[str]:
    """获取所有活跃股票代码。"""
    session = Session(engine)
    try:
        rows = session.execute(
            text("SELECT symbol FROM stock_metadata WHERE is_active=1 ORDER BY symbol")
        ).fetchall()
        return [row[0] for row in rows]
    finally:
        session.close()


def batch_backfill(symbols: list[str], start_year: int, end_year: int, batch_size: int = 50, concurrency: int = 2):
    """分批执行回填。"""
    total = len(symbols)
    batches = (total + batch_size - 1) // batch_size

    logger.info("Start backfill: %d symbols, %d-%d, %d batches", total, start_year, end_year, batches)

    success_total = 0
    records_total = 0
    errors: list[str] = []

    for i in range(batches):
        start = i * batch_size
        end = min(start + batch_size, total)
        batch = symbols[start:end]

        logger.info("Batch %d/%d: symbols %d-%d (%s ~ %s)", i + 1, batches, start + 1, end, batch[0], batch[-1])

        try:
            results = sync_svc.batch_fetch(batch, start_year, end_year, concurrency=concurrency)

            success = sum(1 for r in results if r["success"])
            records = sum(r["records_fetched"] for r in results)
            failed = [r for r in results if not r["success"]]

            success_total += success
            records_total += records
            errors.extend([f"{r['symbol']}: {r['message']}" for r in failed])

            logger.info(
                "Batch %d/%d done: %d/%d success, %d records",
                i + 1, batches, success, len(batch), records,
            )

            if failed:
                logger.warning("Batch %d/%d failed: %s", i + 1, batches, [r["symbol"] for r in failed])

            if i < batches - 1:
                time.sleep(2.0)

        except Exception as exc:
            logger.error("Batch %d/%d error: %s", i + 1, batches, exc)
            errors.append(f"Batch {i+1}: {exc}")

    logger.info("=" * 60)
    logger.info("Backfill completed:")
    logger.info("  Total symbols: %d", total)
    logger.info("  Success: %d", success_total)
    logger.info("  Failed: %d", total - success_total)
    logger.info("  Total records: %d", records_total)

    if errors:
        logger.warning("Failed items:")
        for e in errors[:20]:
            logger.warning("  %s", e)
        if len(errors) > 20:
            logger.warning("  ... and %d more", len(errors) - 20)

    return success_total, records_total, errors


if __name__ == "__main__":
    symbols = get_all_symbols()
    start_year = 2020
    end_year = 2024

    logger.info("Found %d active stocks", len(symbols))
    logger.info("Backfill years: %d-%d", start_year, end_year)
    logger.info("=" * 60)

    start_time = time.time()
    success, records, errors = batch_backfill(
        symbols,
        start_year=start_year,
        end_year=end_year,
        batch_size=50,
        concurrency=2,
    )
    elapsed = time.time() - start_time

    logger.info(f"Elapsed time: {elapsed:.1f}s ({elapsed/60:.1f}min)")
    logger.info(f"Rate: {records/elapsed:.1f} records/s")
