"""
股票工具函数 — 代码解析与 K 线数据获取。

替代旧的 ``agents/investment_analysis.py`` 中的对应函数，供新路径使用。
无业务逻辑依赖，纯工具函数。
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from shared.base import KlineBar, normalize_kline_bar

logger = logging.getLogger(__name__)

# ── 常见股票名称 → 代码映射（兜底） ────────────────────────────────────────────

_STOCK_NAME_MAP: dict[str, str] = {
    "贵州茅台": "600519",
    "茅台": "600519",
    "五粮液": "000858",
    "宁德时代": "300750",
    "比亚迪": "002594",
    "招商银行": "600036",
    "平安银行": "000001",
    "中信证券": "600030",
}

# ── 股票代码正则（匹配独立 6 位数字，避免误匹配日期/数量） ───────────────────

_STOCK_CODE_RE = re.compile(r"(?<!\d)\d{6}(?!\d)")

# ── K 线获取 ──────────────────────────────────────────────────────────────────

_INDICATOR_WARMUP_N = 50  # 指标预热需要多取的 K 线数


def resolve_symbol(identifier: str) -> Optional[str]:
    """解析股票标识。

    - 6 位数字代码 → 查 DB 补全交易所后缀（600519 → 600519.SH）
    - 名称 → 查映射表 + 兜底 DB
    - 其他 → 直接返回

    Args:
        identifier: 股票代码（6位数字）或名称。

    Returns:
        解析后的 symbol，失败返回 None。
    """
    identifier = (identifier or "").strip()
    if not identifier:
        return None

    if identifier.isdigit() and len(identifier) == 6:
        # 查 DB 补全交易所后缀
        try:
            from services.stock_metadata_service import search_stocks

            matches = search_stocks(identifier, limit=1)
            if matches:
                return matches[0].get("symbol")
        except Exception:
            pass
        return identifier

    # 简单名称映射
    if identifier in _STOCK_NAME_MAP:
        return _STOCK_NAME_MAP[identifier]

    # 兜底查 DB
    try:
        from services.stock_metadata_service import search_stocks

        matches = search_stocks(identifier, limit=1)
        if matches:
            return matches[0].get("symbol")
    except Exception:
        pass
    return None


def extract_stock_identifier(text: str) -> str:
    """从自然语言句子中提取股票代码或名称。

    优先级：
      1. 正则匹配 6 位数字代码（如 "帮我分析600519" → "600519"）
      2. 名称映射表子串匹配（如 "分析一下贵州茅台" → "贵州茅台"）
      3. DB 模糊匹配（完整句子兜底）
      4. 都无法提取 → 返回原句

    Args:
        text: 用户输入的自然语言句子。

    Returns:
        提取出的股票标识（代码或名称）；无法提取时返回原句。
    """
    text = (text or "").strip()
    if not text:
        return ""

    # 1. 6 位数字代码
    m = _STOCK_CODE_RE.search(text)
    if m:
        return m.group(0)

    # 2. 名称映射表子串匹配（按名称长度降序，优先匹配更长名称）
    for name in sorted(_STOCK_NAME_MAP, key=len, reverse=True):
        if name in text:
            return name

    # 3. DB 模糊匹配
    try:
        from services.stock_metadata_service import search_stocks

        matches = search_stocks(text, limit=1)
        if matches:
            return matches[0].get("symbol") or text
    except Exception:
        pass

    # 4. 兜底返回原句
    return text


def get_kline_bars(
    symbol: str,
    timeframe: str,
    n: int,
    end_date: Optional[str] = None,
) -> Optional[list[KlineBar]]:
    """获取 K 线，返回新→旧排序的 KlineBar 列表（索引 0 为最新）。

    在线模式（end_date 为空）**实时优先**：
      先通过 AkShare（东财主源）直接拉取最新 K 线并回写 DB（保证数据实时性），
      实时拉取失败（网络/限流/接口异常）才降级查 market_data 表。
    回测模式（end_date 非空）：
      仅查表（避免未来函数，禁止实时拉取）。

    Args:
        symbol: 股票代码（如 600519 或 600519.SH）。
        timeframe: 时间周期（'1d', '1w', '1h' 等）。
        n: 需要的已收盘 K 线根数（不含预热用数据）。
        end_date: 可选，历史回测时点（YYYY-MM-DD），仅取该日及之前的日线；
            为 None 时取最新数据。

    Returns:
        KlineBar 列表（索引 0 为最新），K 线数量不足时返回 None。
    """
    # 回测模式：仅查表，绝不实时拉取（避免未来函数）
    if end_date is not None:
        return _get_kline_bars_from_db(symbol, timeframe, n, end_date)

    # 在线模式：实时优先拉取，成功即返回（已回写 DB）
    # 新鲜度短路：DB 已有近 3 个自然日内的数据视为"实时"，直接查表返回，
    # 避免对已最新标的重复调用 AkShare（东财接口限流风险）。
    db_bars = _get_kline_bars_from_db(symbol, timeframe, n, None)
    if db_bars is not None and _db_fresh(db_bars):
        return db_bars

    # DB 无数据 / 陈旧 / 不足 → 实时拉取（成功回写 DB）
    live = _fetch_live_kline_bars(symbol, timeframe, n)
    if live is not None:
        return live

    # 实时拉取也失败 → 降级返回 DB 已有数据（哪怕陈旧），保证诊断可用
    return db_bars


def _db_fresh(bars: list[KlineBar], max_age_days: int = 3) -> bool:
    """判断 DB K 线是否新鲜：最新一根收盘日距今 <= max_age_days 自然日。"""
    try:
        if not bars:
            return False
        from datetime import datetime, timezone

        latest_ms = float(bars[0].ts_open)
        latest_dt = datetime.fromtimestamp(latest_ms / 1000, tz=timezone.utc)
        now_dt = datetime.now(tz=timezone.utc)
        return (now_dt - latest_dt).days <= max_age_days
    except Exception:
        return False


def _get_kline_bars_from_db(
    symbol: str,
    timeframe: str,
    n: int,
    end_date: Optional[str],
) -> Optional[list[KlineBar]]:
    """从 market_data 表读取 K 线（新→旧），数量不足 n 返回 None。"""
    try:
        from services.market_data_service import get_kline_history

        fetch_n = n + _INDICATOR_WARMUP_N
        raw = get_kline_history(
            symbol, timeframe=timeframe, end_date=end_date, limit=fetch_n
        )
        if not raw:
            return None
        if len(raw) < n:
            logger.warning(
                "Insufficient bars for %s %s: need %d, got %d",
                symbol, timeframe, n, len(raw),
            )
            return None

        # get_kline_history 返回 trade_date ASC（旧→新），需要反转
        bars: list[KlineBar] = []
        for idx, r in enumerate(reversed(raw)):
            bars.append(
                normalize_kline_bar(
                    KlineBar(
                        seq=idx + 1,
                        ts_open=int(r.get("ts_open", 0)),
                        open=float(r.get("open", 0.0)),
                        high=float(r.get("high", 0.0)),
                        low=float(r.get("low", 0.0)),
                        close=float(r.get("close", 0.0)),
                        volume=float(r.get("volume", 0)),
                        amount=float(r.get("amount", 0.0) or 0.0),
                        pct_chg=r.get("pct_chg"),
                        closed=True,
                    )
                )
            )
        return bars
    except Exception as exc:
        logger.warning("DB K 线读取失败 %s %s: %s", symbol, timeframe, exc)
        return None


def _fetch_live_kline_bars(
    symbol: str, timeframe: str, n: int
) -> Optional[list[KlineBar]]:
    """实时拉取 K 线（双源：东财主源 → 新浪备源，参考 PA_Agent 数据读取实现）。

    成功后把拉到的 bars 回写 market_data 表（增量 upsert），保持数据实时性，
    供后续查表 / 前端 K 线图 / 飞书截图复用。失败返回 None（调用方降级查表）。

    仅支持在线模式调用；回测走 DB 路径，不会走到这里。
    """
    try:
        from datetime import datetime, timedelta

        from services.market_data_service import bars_to_rows, upsert_market_data
        from services.sync_service import _fetch_yearly_data

        # 需要预热数据（指标计算），多取 50 根；日期窗口覆盖 2 倍根数（含周末/节假日）
        fetch_n = n + _INDICATOR_WARMUP_N
        now = datetime.now()
        end = now.strftime("%Y-%m-%d")
        start = (now - timedelta(days=max(fetch_n * 2, 400))).strftime("%Y-%m-%d")
        # _fetch_yearly_data：东财优先、失败回退新浪，返回 KlineBar 列表（新→旧）
        bars = _fetch_yearly_data(_strip_symbol_suffix(symbol), start, end)
        if not bars:
            logger.warning("实时 K 线拉取为空: %s %s", symbol, timeframe)
            return None
        if len(bars) < n:
            logger.warning(
                "实时 K 线不足 %s %s: need %d, got %d",
                symbol, timeframe, n, len(bars),
            )
            return None

        # 回写 DB（保实时性；失败不影响本次分析结果）
        try:
            rows = bars_to_rows(symbol, bars)
            if rows:
                upsert_market_data(rows)
        except Exception as exc:
            logger.warning("实时 K 线回写 DB 失败 %s（不影响分析）: %s", symbol, exc)

        return bars[:n]
    except Exception as exc:
        logger.warning("实时 K 线拉取失败 %s %s（降级查表）: %s", symbol, timeframe, exc)
        return None


def _strip_symbol_suffix(symbol: str) -> str:
    """去除交易所后缀：'600519.SH' / '000001.SZ' → '600519' / '000001'。"""
    import re as _re

    raw = (symbol or "").strip()
    digits = _re.sub(r"\D", "", raw)
    if len(digits) >= 6:
        return digits[-6:]
    return digits
