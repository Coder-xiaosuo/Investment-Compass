"""规则门控系统：对股票进行价值估值前的硬性条件检查。"""

import logging

logger = logging.getLogger(__name__)


def check_gates(symbol: str, financial_data: dict) -> dict:
    """
    Check all gate conditions for a stock.

    Args:
        symbol: Stock code (6 digits)
        financial_data: Financial data dict, expected to contain:
            - roe: float or None
            - debt_ratio: float or None
            - report_date: str (e.g. "2026-03-31")
            - Any other financial fields

    Returns:
        dict with:
            - passed: bool
            - blocked: bool
            - reason: str or None (why blocked)
            - warnings: list[str] (non-blocking warnings)
    """
    logger.debug("Checking gates for symbol: %s", symbol)

    # ── Gate 1: Empty / None financial data ──────────────────────────────────
    if not financial_data:
        logger.info("Gate blocked: %s - 财务数据缺失", symbol)
        return {
            "passed": False,
            "blocked": True,
            "reason": "财务数据缺失，无法评估",
            "warnings": [],
        }

    roe = financial_data.get("roe")
    debt_ratio = financial_data.get("debt_ratio")

    # ── Gate 2: ST / *ST stock or missing ROE (data quality issue) ───────────
    if symbol.startswith("ST") or symbol.startswith("*ST") or roe is None:
        logger.info("Gate blocked: %s - 风险警示股或数据不足", symbol)
        return {
            "passed": False,
            "blocked": True,
            "reason": "该标的为风险警示股或数据不足，建议回避",
            "warnings": [],
        }

    # ── Gate 3: Negative ROE ─────────────────────────────────────────────────
    if roe < 0:
        logger.info("Gate blocked: %s - ROE为负 (%.2f%%)", symbol, roe)
        return {
            "passed": False,
            "blocked": True,
            "reason": "净资产收益率为负，盈利能力不足，建议回避",
            "warnings": [],
        }

    # ── Gate 4: Debt ratio too high (> 90) ──────────────────────────────────
    if debt_ratio is not None and debt_ratio > 90:
        logger.info("Gate blocked: %s - 资产负债率过高 (%.2f%%)", symbol, debt_ratio)
        return {
            "passed": False,
            "blocked": True,
            "reason": "资产负债率超过 90%，财务风险过高，建议回避",
            "warnings": [],
        }

    # ── Warnings (non-blocking) ──────────────────────────────────────────────
    warnings: list[str] = []

    # Warning A: Data quality issue
    report_date = financial_data.get("report_date")
    if roe is None or not report_date:
        warnings.append("财务数据不完整，评分可能不可靠")

    # Warning B: Revenue and profit both declining
    revenue_growth = financial_data.get("revenue_growth")
    profit_growth = financial_data.get("profit_growth")
    if (
        revenue_growth is not None
        and profit_growth is not None
        and revenue_growth < 0
        and profit_growth < 0
    ):
        warnings.append("营收和利润连续下滑，趋势向下")

    # Warning C: Debt ratio elevated (> 70 %)
    if debt_ratio is not None and debt_ratio > 70:
        warnings.append("资产负债率偏高（>70%）")

    logger.debug(
        "Gates passed for %s with %d warning(s)", symbol, len(warnings)
    )
    return {
        "passed": True,
        "blocked": False,
        "reason": None,
        "warnings": warnings,
    }
