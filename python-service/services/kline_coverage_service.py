"""K线完整性台账服务（L3）— 把"数据缺口"变成可查询的工作队列。

解决的问题：
    原回填管道把限流吞掉并标记 SUCCESS，导致表里好数据与残缺数据无法区分，
    缺口成为黑洞。本服务以「交易日历为期望基线」做对账，把
    「期望多少根 vs 实到多少根 vs 缺哪几段」显式落库，使数据可审计。

核心语义：
    expected_days = 交易日历 ∩ [effective_from, effective_to]
    actual_days   = market_data 实到行数
    missing_days  = 期望 - 实到（按交易日集合差）
    missing_ranges= 缺失交易日压缩成的连续区间（连续=日历上相邻，跨节假日会合并）

状态机：
    NOT_LISTED  上市日晚于回溯终点 → 未上市，不重试
    DELISTED    已退市 → 不再要求数据，不重试
    NO_DATA     期望为 0 → 无需数据
    FAILED      期望 > 0 但一行都没有 → 极可能是限流，需重试
    COMPLETE    覆盖率 >= 阈值
    PARTIAL     0 < 覆盖率 < 阈值 → 记录缺口，可重试
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from services import trading_calendar_service as tcs
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

STATUS_COMPLETE = "COMPLETE"
STATUS_PARTIAL = "PARTIAL"
STATUS_FAILED = "FAILED"
STATUS_NO_DATA = "NO_DATA"
STATUS_NOT_LISTED = "NOT_LISTED"
STATUS_DELISTED = "DELISTED"

# 需要（且允许）重试的状态
RETRYABLE_STATUSES = (STATUS_PARTIAL, STATUS_FAILED)

# 退避上限
_MAX_BACKOFF = timedelta(hours=6)


def _session() -> Session:
    return Session(_engine)


def _threshold() -> float:
    return float(getattr(settings, "KLINE_COVERAGE_COMPLETE_THRESHOLD", 99.0))


def _default_from() -> date:
    raw = getattr(settings, "KLINE_BACKFILL_FROM", "2020-01-01")
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return date(2020, 1, 1)


def _coerce_date(value: Any) -> Optional[date]:
    """兼容 date / datetime / 'YYYY-MM-DD'。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _backoff(attempts: int) -> timedelta:
    """指数退避：5min * 2^attempts，上限 6h。"""
    minutes = min(5 * (2 ** max(attempts, 0)), int(_MAX_BACKOFF.total_seconds() // 60))
    return timedelta(minutes=minutes)


# ── 缺口区间压缩 ──────────────────────────────────────────────────────────────

_CAL_INDEX: dict[date, int] = {}


def _calendar_index() -> dict[date, int]:
    """交易日 → 序号（用于判断两个缺失日是否在日历上相邻）。"""
    global _CAL_INDEX
    if not _CAL_INDEX:
        _CAL_INDEX = {d: i for i, d in enumerate(tcs.all_trading_days())}
    return _CAL_INDEX


def compress_ranges(missing: list[date]) -> list[list[str]]:
    """把缺失交易日压缩为连续区间。

    相邻判定基于**交易日历**而非自然日，因此跨节假日（如春节）的连续缺失
    会合并为一段，便于一次性按段重拉。

    Args:
        missing: 升序的缺失交易日列表。

    Returns:
        [[start_iso, end_iso], ...]，无缺失时返回 []。
    """
    if not missing:
        return []
    pos = _calendar_index()
    ranges: list[list[str]] = []
    start = prev = missing[0]
    for d in missing[1:]:
        if pos.get(d, -2) == pos.get(prev, -1) + 1:
            prev = d
            continue
        ranges.append([start.isoformat(), prev.isoformat()])
        start = prev = d
    ranges.append([start.isoformat(), prev.isoformat()])
    return ranges


# ── 对账 ──────────────────────────────────────────────────────────────────────

def _load_symbol_meta(session: Session, symbol: str) -> tuple[Optional[date], Optional[date]]:
    row = session.execute(
        text("SELECT list_date, delist_date FROM stock_metadata WHERE symbol = :sym"),
        {"sym": symbol},
    ).fetchone()
    if not row:
        return None, None
    return _coerce_date(row.list_date), _coerce_date(row.delist_date)


def _load_actual_dates(session: Session, symbol: str, timeframe: str) -> list[date]:
    rows = session.execute(
        text("""
            SELECT trade_date FROM market_data
            WHERE symbol = :sym AND timeframe = :tf
        """),
        {"sym": symbol, "tf": timeframe},
    ).fetchall()
    return [_coerce_date(r.trade_date) for r in rows if r.trade_date is not None]


def reconcile_symbol(
    symbol: str,
    *,
    expected_from: Optional[date] = None,
    expected_to: Optional[date] = None,
    timeframe: str = "1d",
    error: Optional[str] = None,
) -> dict[str, Any]:
    """对单个标的做完整性对账并写入台账。

    Args:
        symbol: 6 位代码。
        expected_from: 意图回溯起点，默认取配置 KLINE_BACKFILL_FROM。
        expected_to: 对账终点，默认今天（并裁剪到日历覆盖范围内）。
        timeframe: K线周期，默认 1d。
        error: 若本次对账由一次失败的拉取触发，可传入错误信息记入台账。

    Returns:
        该标的的台账行（dict）。
    """
    expected_from = expected_from or _default_from()
    cal_min, cal_max = tcs.calendar_span()
    expected_to = expected_to or date.today()
    if expected_to > cal_max:
        expected_to = cal_max
    if expected_from < cal_min:
        expected_from = cal_min

    session = _session()
    try:
        list_date, delist_date = _load_symbol_meta(session, symbol)
        actual_all = _load_actual_dates(session, symbol, timeframe)
    finally:
        session.close()

    if list_date is None:
        logger.warning("%s 无 list_date，期望基线可能偏大（请先执行 sync_list_dates）", symbol)

    effective_from = max(expected_from, list_date) if list_date else expected_from

    # 未上市
    if list_date and list_date > expected_to:
        row = _build_row(
            symbol, timeframe, expected_from, expected_to, effective_from,
            expected=[],
            actual=actual_all,
            status=STATUS_NOT_LISTED,
            error=error,
        )
    else:
        # 已退市：只要求到退市日为止
        effective_to = min(expected_to, delist_date) if delist_date else expected_to
        expected = tcs.trading_days_between(effective_from, effective_to)
        matched, missing = _diff(expected, actual_all)

        if delist_date:
            status = STATUS_DELISTED
        elif not expected:
            status = STATUS_NO_DATA
        elif not actual_all:
            status = STATUS_FAILED
        else:
            pct = 100.0 * matched / len(expected)
            status = STATUS_COMPLETE if pct >= _threshold() else STATUS_PARTIAL

        row = _build_row(
            symbol, timeframe, expected_from, expected_to, effective_from,
            expected=expected,
            actual=actual_all,
            status=status,
            error=error,
            missing=missing,
        )

    _upsert(row, error=error)
    return row


def _diff(expected: list[date], actual: list[date]) -> tuple[int, list[date]]:
    """计算 (命中数, 缺失交易日升序列表)。"""
    actual_set = set(actual)
    missing = [d for d in expected if d not in actual_set]
    return len(expected) - len(missing), missing


def _build_row(
    symbol: str,
    timeframe: str,
    expected_from: date,
    expected_to: date,
    effective_from: date,
    *,
    expected: list[date],
    actual: list[date],
    status: str,
    error: Optional[str] = None,
    missing: Optional[list[date]] = None,
) -> dict[str, Any]:
    if missing is None:
        missing = list(expected)
    ranges = compress_ranges(missing)
    expected_days = len(expected)
    actual_days = len(actual)
    missing_days = len(missing)
    matched = expected_days - missing_days
    coverage = round(100.0 * matched / expected_days, 2) if expected_days else 0.0

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "expected_from": expected_from,
        "expected_to": expected_to,
        "effective_from": effective_from,
        "expected_days": expected_days,
        "actual_days": actual_days,
        "missing_days": missing_days,
        "gap_count": len(ranges),
        "coverage_pct": coverage,
        "status": status,
        "missing_ranges": ranges,
        "last_error": (error or None),
    }


def _upsert(row: dict[str, Any], *, error: Optional[str] = None) -> None:
    """写入台账（单行原子 UPDATE，天然避免"部分缺口"的不一致）。"""
    retryable = row["status"] in RETRYABLE_STATUSES
    session = _session()
    try:
        session.execute(
            text("""
                INSERT INTO kline_coverage
                    (symbol, timeframe, expected_from, expected_to, effective_from,
                     expected_days, actual_days, missing_days, gap_count, coverage_pct,
                     status, missing_ranges, attempts, last_error, last_attempt_at, next_retry_at)
                VALUES
                    (:symbol, :timeframe, :expected_from, :expected_to, :effective_from,
                     :expected_days, :actual_days, :missing_days, :gap_count, :coverage_pct,
                     :status, CAST(:missing_ranges AS JSON), 1, :last_error, NOW(), NULL)
                ON DUPLICATE KEY UPDATE
                    expected_from  = VALUES(expected_from),
                    expected_to    = VALUES(expected_to),
                    effective_from = VALUES(effective_from),
                    expected_days  = VALUES(expected_days),
                    actual_days    = VALUES(actual_days),
                    missing_days   = VALUES(missing_days),
                    gap_count      = VALUES(gap_count),
                    coverage_pct   = VALUES(coverage_pct),
                    status         = VALUES(status),
                    missing_ranges = VALUES(missing_ranges),
                    attempts       = attempts + 1,
                    last_error     = VALUES(last_error),
                    last_attempt_at= NOW(),
                    next_retry_at  = NULL,
                    updated_at     = NOW()
            """),
            {
                **row,
                "missing_ranges": json.dumps(row["missing_ranges"], ensure_ascii=False),
            },
        )
        if retryable:
            attempts = session.execute(
                text("SELECT attempts FROM kline_coverage WHERE symbol=:s AND timeframe=:t"),
                {"s": row["symbol"], "t": row["timeframe"]},
            ).scalar() or 0
            session.execute(
                text("""
                    UPDATE kline_coverage SET next_retry_at = :nrt
                    WHERE symbol=:s AND timeframe=:t
                """),
                {
                    "nrt": datetime.now() + _backoff(int(attempts)),
                    "s": row["symbol"],
                    "t": row["timeframe"],
                },
            )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reconcile_symbols(
    symbols: Iterable[str],
    *,
    expected_from: Optional[date] = None,
    expected_to: Optional[date] = None,
    timeframe: str = "1d",
) -> dict[str, Any]:
    """批量对账，返回按状态汇总的统计。

    单个标的失败不影响其余（逐标的独立事务）。
    """
    counts: dict[str, int] = {}
    errors: list[str] = []
    total = 0
    for sym in symbols:
        total += 1
        try:
            row = reconcile_symbol(
                sym,
                expected_from=expected_from,
                expected_to=expected_to,
                timeframe=timeframe,
            )
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        except Exception as exc:
            errors.append(f"{sym}: {exc}")
            logger.warning("对账失败 %s: %s", sym, exc)
    summary = {"total": total, "by_status": counts, "errors": len(errors)}
    logger.info("批量对账完成: %s", summary)
    if errors:
        summary["error_samples"] = errors[:10]
    return summary


def reconcile_all_active(*, timeframe: str = "1d") -> dict[str, Any]:
    """对账 stock_metadata 中全部启用标的（全市场审计入口）。"""
    session = _session()
    try:
        rows = session.execute(
            text("SELECT symbol FROM stock_metadata WHERE is_active = 1 ORDER BY symbol")
        ).fetchall()
        symbols = [r.symbol for r in rows]
    finally:
        session.close()
    return reconcile_symbols(symbols, timeframe=timeframe)


# ── 读取（供 /monitor 与回填队列消费）─────────────────────────────────────────

def get_coverage(symbol: str, timeframe: str = "1d") -> Optional[dict[str, Any]]:
    """读取单个标的台账。"""
    session = _session()
    try:
        row = session.execute(
            text("SELECT * FROM kline_coverage WHERE symbol=:s AND timeframe=:t"),
            {"s": symbol, "t": timeframe},
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        session.close()


def summary(timeframe: str = "1d") -> dict[str, Any]:
    """全市场覆盖分布（审计总览）。"""
    session = _session()
    try:
        rows = session.execute(
            text("""
                SELECT status, COUNT(*) c, SUM(missing_days) miss
                FROM kline_coverage WHERE timeframe = :tf
                GROUP BY status
            """),
            {"tf": timeframe},
        ).fetchall()
        by_status = {r.status: int(r.c) for r in rows}
        total_missing = int(sum(int(r.miss or 0) for r in rows))
        return {
            "by_status": by_status,
            "total_symbols": sum(by_status.values()),
            "total_missing_days": total_missing,
            "threshold_pct": _threshold(),
        }
    finally:
        session.close()


def retry_queue(limit: int = 100, timeframe: str = "1d") -> list[dict[str, Any]]:
    """回填工作队列：缺得最多、且到达重试时间的标的优先。

    只取标量列排序，不解析 JSON（missing_ranges 按需再读）。
    """
    session = _session()
    try:
        rows = session.execute(
            text("""
                SELECT symbol, status, expected_days, actual_days, missing_days,
                       gap_count, coverage_pct, attempts, next_retry_at, missing_ranges
                FROM kline_coverage
                WHERE timeframe = :tf
                  AND status IN ('PARTIAL','FAILED')
                  AND (next_retry_at IS NULL OR next_retry_at <= NOW())
                ORDER BY missing_days DESC
                LIMIT :lim
            """),
            {"tf": timeframe, "lim": limit},
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        session.close()


def worst_offenders(limit: int = 20, timeframe: str = "1d") -> list[dict[str, Any]]:
    """缺口最大的标的（排障用）。"""
    session = _session()
    try:
        rows = session.execute(
            text("""
                SELECT symbol, status, expected_days, actual_days, missing_days,
                       coverage_pct, gap_count
                FROM kline_coverage
                WHERE timeframe = :tf AND missing_days > 0
                ORDER BY missing_days DESC
                LIMIT :lim
            """),
            {"tf": timeframe, "lim": limit},
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        session.close()


def _row_to_dict(row: Any) -> dict[str, Any]:
    d = dict(row._mapping)
    for k in ("expected_from", "expected_to", "effective_from"):
        if d.get(k) is not None:
            d[k] = str(d[k])
    for k in ("last_attempt_at", "next_retry_at", "created_at", "updated_at"):
        if d.get(k) is not None:
            d[k] = str(d[k])
    mr = d.get("missing_ranges")
    if isinstance(mr, str):
        try:
            d["missing_ranges"] = json.loads(mr)
        except Exception:
            pass
    if d.get("coverage_pct") is not None:
        d["coverage_pct"] = float(d["coverage_pct"])
    return d
