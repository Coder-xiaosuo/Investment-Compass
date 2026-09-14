"""交易日历服务 — A 股交易日历（L1 完整性审计基准）。

定位：
    日历是"应该有多少根 K 线"的唯一 ground truth。它必须来自**外部独立源**，
    绝不能从 market_data 自身推导（取所有 symbol 的 trade_date 并集）——那是循环论证：
    若限流导致全市场某段时间都缺，推导出的日历同样缺失，审计会误判为"完整"，
    而这正是要避免的黑洞。

存储形式：
    静态参考数据文件 ``data/trading_calendar.json``（随仓库 pin 住，可复现审计）。
    不建表的原因：日历只在"计算缺口"时刻被使用，且消费方仅 Python（Java 只读
    预先算好的 kline_coverage），从不参与 SQL JOIN；计算结果的期望值已落库，
    台账因此自洽，不依赖原始日历。

数据源：
    akshare ``tool_trade_date_hist_sina`` → 8797 行 / 约 0.5s / 覆盖 1990-12-19 起。

按年刷新即可（默认建议每季度或手动）。
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_SOURCE = "akshare.tool_trade_date_hist_sina"
_FORMAT_VERSION = "1.0"

_lock = threading.RLock()
_days: Optional[tuple[date, ...]] = None
_day_set: Optional[frozenset[date]] = None
_meta: dict[str, Any] = {}


def _calendar_path() -> Path:
    from shared.config import settings

    return Path(getattr(settings, "TRADING_CALENDAR_PATH", "data/trading_calendar.json"))


# ── 加载 ──────────────────────────────────────────────────────────────────────

def _parse_days(raw: list[str]) -> tuple[date, ...]:
    days = sorted({date.fromisoformat(str(d)) for d in raw if d})
    return tuple(days)


def load(*, force: bool = False) -> tuple[date, ...]:
    """加载日历（内存缓存）。文件缺失时尝试从数据源重建。

    Args:
        force: 为 True 时忽略内存缓存，强制重新读文件。

    Returns:
        升序交易日元组。

    Raises:
        RuntimeError: 日历文件缺失且无法从数据源重建。
    """
    global _days, _day_set, _meta

    with _lock:
        if _days is not None and not force:
            return _days

        path = _calendar_path()
        if not path.exists():
            logger.warning("交易日历文件不存在（%s），尝试从数据源重建", path)
            refresh_from_source()

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(f"交易日历文件读取失败: {path} ({exc})") from exc

        raw = payload.get("trading_days") or []
        if not raw:
            raise RuntimeError(f"交易日历文件内容为空: {path}")

        _days = _parse_days(raw)
        _day_set = frozenset(_days)
        _meta = {
            "source": payload.get("source", _SOURCE),
            "updated_at": payload.get("updated_at"),
            "count": len(_days),
        }
        logger.info(
            "交易日历已加载：%d 个交易日（%s ~ %s）",
            len(_days), _days[0], _days[-1],
        )
        return _days


def _ensure_loaded() -> None:
    if _days is None:
        load()


# ── 查询 ──────────────────────────────────────────────────────────────────────

def is_trading_day(day: date) -> bool:
    """判断某日是否为交易日。"""
    _ensure_loaded()
    assert _day_set is not None
    return day in _day_set


def all_trading_days() -> tuple[date, ...]:
    """全部交易日（升序）。"""
    return load()


def trading_days_between(start: date, end: date) -> list[date]:
    """区间内交易日列表（含端点，升序）。start > end 时返回空列表。"""
    if start > end:
        return []
    days = load()
    # 二分定位：日历已升序，避免全量扫描
    import bisect

    lo = bisect.bisect_left(days, start)
    hi = bisect.bisect_right(days, end)
    return list(days[lo:hi])


def count_trading_days(start: date, end: date) -> int:
    """区间内交易日数量（含端点）。"""
    return len(trading_days_between(start, end))


def calendar_span() -> tuple[date, date]:
    """日历覆盖范围 (最早, 最晚)。"""
    days = load()
    return days[0], days[-1]


def stats() -> dict[str, Any]:
    """日历元信息（供监控/排障）。"""
    days = load()
    return {
        "count": len(days),
        "min_date": days[0].isoformat(),
        "max_date": days[-1].isoformat(),
        "source": _meta.get("source", _SOURCE),
        "updated_at": _meta.get("updated_at"),
    }


def invalidate() -> None:
    """清空内存缓存（下次访问重新读文件）。"""
    global _days, _day_set, _meta
    with _lock:
        _days = None
        _day_set = None
        _meta = {}


# ── 刷新（从数据源拉取并落文件） ───────────────────────────────────────────────

def refresh_from_source() -> int:
    """从 akshare 拉取全量交易日历并写入文件。

    Returns:
        写入的交易日数量。

    Raises:
        RuntimeError: 数据源不可用或返回空。
    """
    try:
        import akshare as ak
    except Exception as exc:  # pragma: no cover - 依赖缺失
        raise RuntimeError(f"akshare 不可用，无法刷新交易日历: {exc}") from exc

    try:
        df = ak.tool_trade_date_hist_sina()
    except Exception as exc:
        raise RuntimeError(f"交易日历拉取失败: {exc}") from exc

    if df is None or df.empty:
        raise RuntimeError("交易日历拉取返回空结果")

    col = "trade_date" if "trade_date" in df.columns else df.columns[0]
    days = _parse_days([str(v) for v in df[col].tolist()])
    if not days:
        raise RuntimeError("交易日历解析后为空")

    payload = {
        "_comment": "A股交易日历 — K线完整性审计的 ground truth，不可由 market_data 自身推导",
        "version": _FORMAT_VERSION,
        "source": _SOURCE,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "min_date": days[0].isoformat(),
        "max_date": days[-1].isoformat(),
        "count": len(days),
        "trading_days": [d.isoformat() for d in days],
    }

    path = _calendar_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # 先写临时文件再原子替换，避免刷新中途失败损坏日历
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)

    invalidate()
    logger.info("交易日历已刷新并写入 %s：%d 个交易日", path, len(days))
    return len(days)
