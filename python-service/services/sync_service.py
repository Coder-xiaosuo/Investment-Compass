"""Sync service — 数据同步业务逻辑（AkShare → DB）。

支持：
- sync_symbols: 增量同步最新数据
- sync_one_symbol: async 包装，在后台线程执行单只股票同步
- batch_fetch: 批量历史回填，支持断点续传 + 并发拉取
"""
from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any

from services import market_data_service as mds
from services import stock_metadata_service as sms
from services import sync_task_service as sts
from services.source_circuit_breaker import EASTMONEY, SINA, get_source_breaker

logger = logging.getLogger(__name__)

# 并发拉取的线程数（控制在 2-3 避免东财 API 限流）
_BATCH_CONCURRENCY = 2

# 每个线程内部的年份间隔（秒）
_YEAR_INTERVAL_S = 1.5

# 每个股票完成后的冷却时间（秒）
_SYMBOL_COOLDOWN_S = 1.0

# 限流锁：跨线程共享的全局节流器
_akshare_throttle_lock = threading.Lock()
_last_ak_fetch_mono: float = 0.0
_AK_MIN_INTERVAL_S = 0.9


def _strip_suffix(symbol: str) -> str:
    digits = re.sub(r"\D", "", symbol)
    return digits[-6:] if len(digits) >= 6 else digits


def _throttle_akshare() -> None:
    """跨线程共享的 AkShare 节流器，确保两次 API 调用间隔 >= 0.9s。"""
    global _last_ak_fetch_mono
    with _akshare_throttle_lock:
        now = time.monotonic()
        wait = _AK_MIN_INTERVAL_S - (now - _last_ak_fetch_mono)
        if wait > 0:
            time.sleep(wait)
        _last_ak_fetch_mono = time.monotonic()


def _fetch_with_retry(func, symbol: str, max_retries: int = 3) -> Any:
    """带重试的数据拉取，每次间隔递增。"""
    for attempt in range(max_retries):
        try:
            _throttle_akshare()
            return func()
        except Exception as exc:
            if attempt < max_retries - 1:
                wait = (attempt + 1) * 2
                logger.warning("Retry %d/%d for %s after %ds: %s", attempt + 1, max_retries, symbol, wait, exc)
                time.sleep(wait)
            else:
                raise


def _audit_after_attempt(raw_symbol: str, *, error: str | None = None) -> None:
    """拉取尝试后更新完整性台账（审计闭环）。

    无论成功、失败还是空响应，都在 kline_coverage 留下痕迹，
    使"限流导致的空洞"不再被静默吞掉（原实现只打日志、不记录，缺口成为黑洞）。

    审计是观测行为，绝不能影响数据拉取本身：内部异常仅记日志。
    """
    try:
        from services import kline_coverage_service as kcs

        kcs.reconcile_symbol(_strip_suffix(raw_symbol), error=error)
    except Exception as exc:  # pragma: no cover - 审计失败不应中断拉取
        logger.warning("审计对账失败 %s: %s", raw_symbol, exc)


# ── 增量同步（双源 + 断路器） ────────────────────────────────────────────────

def _fetch_incremental_bars(code: str, fetch_n: int, source: str) -> list:
    """按指定源拉取近 N 天日线增量（返回新→旧 KlineBar 列表）。

    Args:
        code: 6 位数字股票代码。
        fetch_n: 需要拉取的 K 线根数（用于推算日期范围）。
        source: ``eastmoney``（东财）或 ``sina``（新浪）。
    """
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=max(fetch_n * 2, 60))).strftime("%Y-%m-%d")
    if source == SINA:
        return _fetch_yearly_sina(code, start, end)
    return _fetch_yearly_eastmoney(code, start, end)


def sync_symbols(symbols: list[str]) -> tuple[int, list[str]]:
    """增量同步最新行情（东财主源，断路器熔断后整批切换新浪备源）。

    - 每只股票先查本地最新交易日，无新增则跳过。
    - 主源连续失败达阈值后熔断，本批次后续标的统一走备源。
    """
    breaker = get_source_breaker()

    total_records = 0
    errors: list[str] = []

    for raw_symbol in symbols:
        # 审计闭环：无论成功/失败/空响应，finally 都会把本次结果写入完整性台账
        audit_error: str | None = None
        try:
            code = _strip_suffix(raw_symbol)
            source = breaker.get_source()

            latest_date = mds.get_latest_market_date(raw_symbol)
            if latest_date:
                fetch_n = mds.estimate_days_since(latest_date)
                if fetch_n <= 1:
                    logger.info("No new data needed for %s (latest: %s)", raw_symbol, latest_date)
                    sms.ensure_stock_metadata(raw_symbol)
                    continue
                fetch_n = min(fetch_n + 3, 14)
                logger.info(
                    "Incremental fetch for %s: need %d bars (latest: %s, source=%s)",
                    raw_symbol, fetch_n, latest_date, source,
                )
            else:
                fetch_n = 60
                logger.info("Initial fetch for %s: need %d bars (source=%s)", raw_symbol, fetch_n, source)

            try:
                bars = _fetch_with_retry(
                    lambda c=code, n=fetch_n, s=source: _fetch_incremental_bars(c, n, s),
                    raw_symbol,
                )
            except Exception as exc:
                breaker.record_failure(source)
                raise
            breaker.record_success(source)

            if not bars:
                # 空响应极可能是限流：显式记入台账，不再静默跳过
                audit_error = f"空响应，疑似限流（source={source}）"
                logger.warning("No data for %s (source=%s)", raw_symbol, source)
                continue

            if latest_date:
                bars = [b for b in bars if mds.bar_trade_date(b) > latest_date]

            if not bars:
                logger.info("No new bars for %s after filtering", raw_symbol)
                sms.ensure_stock_metadata(raw_symbol)
                continue

            rows = mds.bars_to_rows(raw_symbol, bars)
            mds.upsert_market_data(rows)
            sms.ensure_stock_metadata(raw_symbol)
            total_records += len(bars)
            logger.info("Fetched %d bars for %s", len(bars), raw_symbol)

            time.sleep(1.0)
        except Exception as exc:
            audit_error = str(exc)
            msg = f"{raw_symbol}: {exc}"
            errors.append(msg)
            logger.warning("Fetch failed for %s: %s", raw_symbol, exc)
        finally:
            _audit_after_attempt(raw_symbol, error=audit_error)

    return total_records, errors


async def sync_one_symbol(symbol: str) -> tuple[int, list[str]]:
    """async 包装：在后台线程中执行单只股票增量同步，不阻塞事件循环。

    Args:
        symbol: 股票代码（如 "000001" 或 "600519"）。

    Returns:
        (total_records, errors) 同 sync_symbols。
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, sync_symbols, [symbol])


# ── 批量历史回填（重构：断点续传 + 并发） ────────────────────────────────────

def _normalize_df_to_bars(df, time_col: str = "date") -> list:
    from shared.ashare_common import normalize_ohlcv_df, df_to_bars_asc, rows_to_kline_bars

    norm = normalize_ohlcv_df(df, time_col=time_col)
    if norm.empty:
        return []

    if "amount" in norm.columns:
        norm["amount"] = norm["amount"].fillna(0.0)

    rows_asc = df_to_bars_asc(norm, time_col=time_col)

    if "amount" in norm.columns:
        for i, (_, row) in enumerate(norm.iterrows()):
            if i < len(rows_asc):
                rows_asc[i]["amount"] = float(row.get("amount", 0.0) or 0.0)

    rows_newest = list(reversed(rows_asc))
    return rows_to_kline_bars(rows_newest, len(rows_newest))


def _fetch_yearly_eastmoney(code: str, start_date: str, end_date: str) -> list:
    import akshare as ak

    start = start_date.replace("-", "")
    end = end_date.replace("-", "")
    df = ak.stock_zh_a_hist(
        symbol=code,
        period="daily",
        start_date=start,
        end_date=end,
        adjust="qfq",
    )
    return _normalize_df_to_bars(df, time_col="日期")


def _fetch_yearly_sina(code: str, start_date: str, end_date: str) -> list:
    import akshare as ak
    from shared.ashare_common import symbol_with_sina_prefix

    sina_code = symbol_with_sina_prefix(code)
    start = start_date.replace("-", "")
    end = end_date.replace("-", "")
    df = ak.stock_zh_a_daily(
        symbol=sina_code,
        start_date=start,
        end_date=end,
        adjust="qfq",
    )
    return _normalize_df_to_bars(df, time_col="date")


def _fetch_yearly_data(code: str, start_date: str, end_date: str) -> list:
    """拉取年度历史数据，优先东财，失败回退新浪。"""
    try:
        return _fetch_yearly_eastmoney(code, start_date, end_date)
    except Exception as exc:
        logger.debug("EastMoney failed for %s (%s), fallback to Sina: %s", code, start_date, exc)
    return _fetch_yearly_sina(code, start_date, end_date)


def _process_single_symbol(raw_symbol: str, start_year: int, end_year: int) -> dict[str, Any]:
    """处理单个股票的历史回填（支持断点续传）。

    返回 { symbol, success, records_fetched, message, task_id }
    """
    code = _strip_suffix(raw_symbol)
    task_id = sts.upsert_task(raw_symbol, start_year, end_year)

    # 查询任务状态，已完成则跳过
    task = sts.get_task(task_id)
    if task and task["status"] == "SUCCESS":
        logger.info("Skip %s: already SUCCESS (%d records)", raw_symbol, task["records_fetched"])
        _audit_after_attempt(raw_symbol)
        return {
            "symbol": raw_symbol,
            "success": True,
            "records_fetched": task["records_fetched"],
            "message": f"已完成（跳过），共 {task['records_fetched']} 条",
            "task_id": task_id,
        }

    # 确定起始年份（断点续传：从 current_year + 1 开始）
    resume_year = start_year
    if task and task["status"] in ("PARTIAL", "FAILED") and task["current_year"] > 0:
        resume_year = task["current_year"] + 1
        logger.info("Resume %s from year %d (was %s at year %d)", raw_symbol, resume_year, task["status"], task["current_year"])

    sts.mark_running(task_id)

    records_fetched = task["records_fetched"] if task else 0
    first_error: str | None = None
    empty_years: list[int] = []

    try:
        for year in range(resume_year, end_year + 1):
            start_date = f"{year}-01-01"
            end_date = f"{year}-12-31"

            try:
                bars = _fetch_with_retry(
                    lambda c=code, s=start_date, e=end_date: _fetch_yearly_data(c, s, e),
                    raw_symbol,
                )
                if bars:
                    rows = mds.bars_to_rows(raw_symbol, bars)
                    mds.upsert_market_data(rows)
                    records_fetched += len(bars)
                    logger.info("[%s] year %d: %d bars", raw_symbol, year, len(bars))
                else:
                    # 空响应极可能是限流：显式记录，避免被静默跳过（原实现 if bars 直接略过）
                    empty_years.append(year)
                    logger.warning("[%s] year %d: 空响应（疑似限流）", raw_symbol, year)

                # 更新进度
                sts.update_progress(task_id, year, records_fetched)

                time.sleep(_YEAR_INTERVAL_S)
            except Exception as exc:
                logger.error("[%s] year %d failed: %s", raw_symbol, year, exc)
                if first_error is None:
                    first_error = f"year {year}: {exc}"
                # 标记部分完成，保留已成功的数据
                sts.mark_partial(task_id, year, records_fetched, str(exc))
                # 继续下一年（部分容错）
                continue

        # 所有年份处理完毕 —— 审计闭环：把本次尝试的真实结果写入台账
        audit_error = first_error
        if audit_error is None and empty_years:
            shown = empty_years[:5]
            suffix = f" 等{len(empty_years)}年" if len(empty_years) > 5 else ""
            audit_error = f"空响应年份 {shown}{suffix}（疑似限流）"
        _audit_after_attempt(raw_symbol, error=audit_error)

        if first_error:
            sts.mark_partial(task_id, end_year, records_fetched, first_error)
            return {
                "symbol": raw_symbol,
                "success": False,
                "records_fetched": records_fetched,
                "message": f"部分成功: {first_error}",
                "task_id": task_id,
            }
        else:
            sms.ensure_stock_metadata(raw_symbol)
            sts.mark_success(task_id, records_fetched)
            return {
                "symbol": raw_symbol,
                "success": True,
                "records_fetched": records_fetched,
                "message": f"成功拉取 {records_fetched} 条记录",
                "task_id": task_id,
            }
    except Exception as exc:
        logger.error("Batch fetch failed for %s: %s", raw_symbol, exc)
        sts.mark_failed(task_id, str(exc), records_fetched)
        _audit_after_attempt(raw_symbol, error=str(exc))
        return {
            "symbol": raw_symbol,
            "success": False,
            "records_fetched": records_fetched,
            "message": str(exc),
            "task_id": task_id,
        }


def batch_fetch(
    symbols: list[str],
    start_year: int,
    end_year: int,
    concurrency: int = _BATCH_CONCURRENCY,
) -> list[dict[str, Any]]:
    """批量拉取指定股票的历史日线数据（断点续传 + 并发）。

    Args:
        symbols: 股票代码列表
        start_year: 起始年份
        end_year: 结束年份
        concurrency: 并发线程数（默认 2，避免东财 API 限流）

    Returns:
        每个股票的处理结果列表
    """
    if start_year > end_year:
        raise ValueError("start_year 不能大于 end_year")

    if concurrency < 1:
        concurrency = 1
    if concurrency > 5:
        logger.warning("Concurrency %d too high, capping to 5 to avoid API rate limit", concurrency)
        concurrency = 5

    logger.info(
        "batch_fetch: %d symbols, %d-%d, concurrency=%d",
        len(symbols), start_year, end_year, concurrency,
    )

    results: list[dict[str, Any]] = []

    if concurrency == 1:
        # 串行模式（调试友好）
        for raw_symbol in symbols:
            result = _process_single_symbol(raw_symbol, start_year, end_year)
            results.append(result)
            time.sleep(_SYMBOL_COOLDOWN_S)
    else:
        # 并发模式
        with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="batch-fetch") as executor:
            future_to_symbol = {
                executor.submit(_process_single_symbol, sym, start_year, end_year): sym
                for sym in symbols
            }
            for future in as_completed(future_to_symbol):
                sym = future_to_symbol[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as exc:
                    logger.error("Unexpected error for %s: %s", sym, exc)
                    results.append({
                        "symbol": sym,
                        "success": False,
                        "records_fetched": 0,
                        "message": str(exc),
                        "task_id": None,
                    })

    # 按原始 symbols 顺序排序结果
    symbol_order = {s: i for i, s in enumerate(symbols)}
    results.sort(key=lambda r: symbol_order.get(r["symbol"], len(symbols)))

    success_count = sum(1 for r in results if r["success"])
    total_records = sum(r["records_fetched"] for r in results)
    logger.info(
        "batch_fetch done: %d/%d success, %d records",
        success_count, len(symbols), total_records,
    )

    return results
