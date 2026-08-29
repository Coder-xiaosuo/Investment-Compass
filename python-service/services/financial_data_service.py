"""Financial data service — 财务指标获取与管理。"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any

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


# akshare stock_financial_abstract 指标名称 → DB 列名映射
_INDICATOR_MAP: dict[str, str] = {
    "净资产收益率(ROE)": "roe",
    "总资产报酬率(ROA)": "roa",
    "毛利率": "gross_margin",
    "销售净利率": "net_margin",
    "营业利润率": "operating_margin",
    "营业总收入": "revenue",
    "归母净利润": "net_profit",
    "经营现金流量净额": "cash_flow_op",
    "营业总收入增长率": "revenue_growth",
    "归属母公司净利润增长率": "profit_growth",
    "资产负债率": "debt_ratio",
    "流动比率": "current_ratio",
    "速动比率": "quick_ratio",
    "基本每股收益": "eps",
    "每股净资产": "bvps",
    "每股现金流": "cfps",
    "经营活动净现金/归属母公司的净利润": "cash_ratio",
    "股东权益合计(净资产)": "total_equity",
    "期间费用率": "cost_ratio",
}

# 原始数据中需要保留的列名（除已映射的之外）
_RAW_KEY_COLUMNS: set[str] = {
    "净资产收益率(ROE)", "总资产报酬率(ROA)", "毛利率", "销售净利率", "营业利润率",
    "营业总收入", "归母净利润", "经营现金流量净额",
    "营业总收入增长率", "归属母公司净利润增长率",
    "资产负债率", "流动比率", "速动比率",
    "基本每股收益", "每股净资产", "每股现金流",
    "经营活动净现金/归属母公司的净利润", "股东权益合计(净资产)", "期间费用率",
    "总资产", "每股营业收入", "营业收入同比增长率",
    "营业收入环比增长率", "净利润同比增长率", "净利润环比增长率",
}


def _parse_report_type(report_date: str) -> str:
    """根据报告日期字符串（如 20260331）推断 report_type。"""
    if report_date.endswith("0331"):
        return "Q1"
    if report_date.endswith("0630"):
        return "Q2"
    if report_date.endswith("0930"):
        return "Q3"
    if report_date.endswith("1231"):
        return "Q4"
    return "Q4"


def report_available_on(report_type: str, report_date: Any) -> date:
    """计算报告在历史时点 D 是否已披露（按 A股监管披露截止日判断），防未来函数。

    规则（A股监管披露截止日）：
        Q1 → 当年 04-30
        Q2 → 当年 08-31
        Q3 → 当年 10-31
        Q4（年报）→ 次年 04-30（如 report_date=2024-12-31 → 2025-04-30）

    report_date 支持 datetime.date 或 "YYYY-MM-DD" 字符串。
    若 report_type 无法识别，则根据 report_date 的月份推断
    （3→Q1、6→Q2、9→Q3、12→Q4），推断不出则返回 report_date 本身。
    """
    if isinstance(report_date, str):
        try:
            d = date.fromisoformat(report_date)
        except ValueError:
            # 非标准日期格式，无法推断，原样返回
            return report_date
    elif isinstance(report_date, date):
        d = report_date
    else:
        return report_date

    rt = (report_type or "").upper()
    if rt == "Q1":
        return date(d.year, 4, 30)
    if rt == "Q2":
        return date(d.year, 8, 31)
    if rt == "Q3":
        return date(d.year, 10, 31)
    if rt == "Q4":
        return date(d.year + 1, 4, 30)

    # report_type 无法识别时按月份推断季度（report_date 通常为季度末）
    month = d.month
    if month == 3:
        return date(d.year, 4, 30)
    if month == 6:
        return date(d.year, 8, 31)
    if month == 9:
        return date(d.year, 10, 31)
    if month == 12:
        return date(d.year + 1, 4, 30)
    return d


def _build_raw_data(map_row: dict[str, Any]) -> dict[str, Any]:
    """从当行数据构建 raw_data JSON。"""
    raw = {}
    for indicator_name in _RAW_KEY_COLUMNS:
        if indicator_name in map_row:
            val = map_row[indicator_name]
            # 跳过 NaN
            if val is not None and (not isinstance(val, float) or val == val):
                raw[indicator_name] = val
    return raw


def _parse_financial_df(df: Any, symbol: str) -> list[dict[str, Any]]:
    """解析 akshare.stock_financial_abstract 返回的 DataFrame，生成入库记录。"""
    import pandas as pd

    # 确认必要列存在
    if "指标" not in df.columns:
        logger.error("缺少「指标」列，无法解析财务数据: %s", df.columns.tolist())
        return []

    # 取出指标名称列和所有报告日期列
    indicator_col = "指标"
    date_columns = [c for c in df.columns if c not in ("选项", "指标") and re.match(r"^\d{8}$", str(c))]
    if not date_columns:
        logger.warning("未找到报告日期列: symbol=%s", symbol)
        return []

    # 构建 indicator → value 的行查找
    # 将 指标 列设为 index
    df_indexed = df.set_index(indicator_col)

    records: list[dict[str, Any]] = []
    for date_str in sorted(date_columns, reverse=True):
        row_data: dict[str, Any] = {}
        all_raw: dict[str, Any] = {}
        has_any_value = False

        for indicator_name in df_indexed.index:
            try:
                val = df_indexed.loc[indicator_name, date_str]
            except (KeyError, TypeError):
                continue

            # 处理 NaN / NaT
            if isinstance(val, pd.Series):
                val = val.iloc[0]
            try:
                if pd.isna(val):
                    continue
            except (ValueError, TypeError):
                continue

            # 尝试转 float
            try:
                numeric_val = float(val)
            except (ValueError, TypeError):
                # 非数值跳过
                continue

            # 将原始值以 indicator_name 为 key 保留
            all_raw[indicator_name] = numeric_val

            col = _INDICATOR_MAP.get(indicator_name)
            if col is not None:
                row_data[col] = numeric_val
                has_any_value = True

        if not has_any_value:
            continue

        report_type = _parse_report_type(date_str)
        # 格式化为 YYYY-MM-DD
        formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

        record = {
            "symbol": symbol,
            "report_date": formatted_date,
            "report_type": report_type,
            "raw_data": json.dumps(all_raw, ensure_ascii=False),
        }
        record.update(row_data)
        records.append(record)

    return records


def _insert_or_update(session: Session, record: dict[str, Any]) -> None:
    """插入或更新一条财务数据记录（使用 INSERT … ON DUPLICATE KEY UPDATE）。"""
    columns = [
        "symbol", "report_date", "report_type", "roe", "roa",
        "gross_margin", "net_margin", "operating_margin",
        "revenue", "net_profit", "total_assets", "total_equity",
        "cash_flow_op", "revenue_growth", "profit_growth",
        "debt_ratio", "current_ratio", "quick_ratio",
        "eps", "bvps", "cfps", "cash_ratio", "cost_ratio",
        "raw_data", "source",
    ]
    placeholders = ", ".join(f":{c}" for c in columns)
    # UPDATE 部分（排除主键和唯一键）
    update_parts = [f"{c} = VALUES({c})" for c in columns if c not in ("symbol", "report_date")]
    update_sql = ", ".join(update_parts)

    sql = f"""
        INSERT INTO stock_financial ({', '.join(columns)})
        VALUES ({placeholders})
        ON DUPLICATE KEY UPDATE {update_sql}
    """
    params = {c: record.get(c) for c in columns}
    if params.get("source") is None:
        params["source"] = "akshare"
    session.execute(text(sql), params)


def _row_to_abstract(row) -> dict[str, Any]:
    """将 stock_financial 表的一行转换为清理后的财务摘要 dict。

    处理 Decimal → float，剔除 raw_data / id / created_at / updated_at。
    """
    result = dict(row._mapping)
    if result.get("report_date"):
        result["report_date"] = str(result["report_date"])
    cleaned: dict[str, Any] = {}
    for k, v in result.items():
        if k == "raw_data":
            continue
        if k in ("id", "created_at", "updated_at"):
            continue
        if hasattr(v, "real"):  # Decimal
            cleaned[k] = float(v) if v is not None else None
        else:
            cleaned[k] = v
    return cleaned


def _report_fresh(report_date: Any, max_age_days: int = 130) -> bool:
    """财务摘要是否新鲜：report_date 距今 <= max_age_days 自然日（约一个报告期）。

    财务数据按季度披露，缓存新鲜度窗口比行情（3 天）宽得多，避免频繁触发
    akshare 实时拉取（接口限流风险）。
    """
    try:
        from datetime import datetime

        if report_date is None:
            return False
        rd = report_date if isinstance(report_date, date) else date.fromisoformat(str(report_date))
        return (datetime.now().date() - rd).days <= max_age_days
    except Exception:
        return False


def get_financial_report(symbol: str) -> dict[str, Any]:
    """获取指定股票的最新财务数据。

    先从 DB 查询最新 4 期报表，如无数据则尝试从 akshare 拉取并写入 DB。
    """
    code = _strip_suffix(symbol)
    session = _session()
    try:
        rows = session.execute(
            text("""
                SELECT * FROM stock_financial
                WHERE symbol = :sym
                ORDER BY report_date DESC
                LIMIT 4
            """),
            {"sym": code},
        ).fetchall()

        if rows:
            result: dict[str, Any] = {"symbol": code, "reports": []}
            for row in rows:
                report = dict(row._mapping)
                if report.get("report_date"):
                    report["report_date"] = str(report["report_date"])
                # 处理 Decimal → float
                for k, v in report.items():
                    if hasattr(v, "to_dict"):  # JSON column
                        report[k] = json.loads(json.dumps(v, ensure_ascii=False, default=str))
                    elif hasattr(v, "real"):  # Decimal
                        report[k] = float(v) if v is not None else None
                    else:
                        report[k] = v
                result["reports"].append(report)
            return result

        # DB 无数据，尝试从 akshare 拉取
        logger.info("未找到缓存财务数据，尝试从 akshare 拉取: symbol=%s", code)
        return _fetch_and_save(session, code)

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_financial_abstract(symbol: str, as_of: Any = None) -> dict[str, Any]:
    """返回指定股票最新的结构化财务摘要。

    返回值示例:
        {
            "symbol": "600519",
            "report_date": "2026-03-31",
            "report_type": "Q1",
            "roe": 10.57,
            "gross_margin": 89.76,
            "net_margin": 52.31,
            "revenue": 12345678900.00,
            "net_profit": 6000000000.00,
            "debt_ratio": 18.50,
            "eps": 4.78,
            "revenue_growth": 12.34,
            "profit_growth": 15.67,
            "cash_flow_op": 8000000000.00,
            "cash_ratio": 1.33,
            ...
        }

    as_of（可选）：历史时点回溯。给定历史时点 D，返回截至 D 已披露
    （按监管披露截止日 report_available_on 判断）的最新一期报表，
    防止未来函数。as_of 支持 "YYYY-MM-DD" 字符串或 datetime.date。

    在线模式（as_of 为空）：DB 缓存新鲜（最新 report_date 距今 <= 130 天，
    覆盖一个报告期）直接返回；缺失/陈旧则实时拉取 akshare 并入库；
    实时拉取失败 → 降级返回 DB 旧缓存（保证估值可用）。
    回测模式（as_of 指定）：仅查 DB，绝不触发实时拉取（防未来函数）。
    """
    code = _strip_suffix(symbol)
    session = _session()
    try:
        if as_of is None:
            # 最新一期查询（保持原有行为）
            row = session.execute(
                text("""
                    SELECT * FROM stock_financial
                    WHERE symbol = :sym
                    ORDER BY report_date DESC
                    LIMIT 1
                """),
                {"sym": code},
            ).fetchone()

            # 新鲜度短路：最新一期报表距现在不超过一个报告期 → 视为实时
            if row and _report_fresh(row.report_date):
                return _row_to_abstract(row)

            # DB 缺失 / 陈旧 → 实时拉取并返回最新一条
            logger.info("财务摘要需更新（%s），尝试从 akshare 拉取", code)
            fetch_result = _fetch_and_save(session, code)
            reports = fetch_result.get("reports", [])
            if reports:
                # 同样清理后返回
                latest = dict(reports[0])
                for k in ("id", "created_at", "updated_at", "raw_data"):
                    latest.pop(k, None)
                return latest

            # 实时拉取失败 → 降级返回 DB 旧缓存（保证估值可用）
            if row:
                logger.warning("财务实时拉取失败 %s，降级返回 DB 缓存", code)
                return _row_to_abstract(row)

            return {"symbol": code, "error": "未获取到财务数据"}

        # as_of 分支：仅查 DB，绝不触发实时拉取
        as_of_date = as_of if isinstance(as_of, date) else date.fromisoformat(str(as_of))
        rows = session.execute(
            text("""
                SELECT * FROM stock_financial
                WHERE symbol = :sym
                ORDER BY report_date DESC
                LIMIT 100
            """),
            {"sym": code},
        ).fetchall()

        # 按披露可用日过滤，取 report_date 最新的一条（查询已按 report_date DESC 排序）
        for row in rows:
            if row.report_date is None:
                continue
            if report_available_on(row.report_type, row.report_date) <= as_of_date:
                return _row_to_abstract(row)

        return {"symbol": code, "error": "未获取到财务数据"}

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _fetch_and_save(session: Session, symbol: str) -> dict[str, Any]:
    """从 akshare 获取财务数据并写入 DB，返回最新 4 期记录。"""
    import akshare as ak

    from shared.akshare_throttle import throttle

    try:
        throttle()
        df = ak.stock_financial_abstract(symbol=symbol)
    except Exception as exc:
        logger.error("akshare 获取财务数据失败: symbol=%s, error=%s", symbol, exc)
        return {"symbol": symbol, "reports": [], "error": str(exc)}

    if df is None or df.empty:
        logger.warning("akshare 返回空数据: symbol=%s", symbol)
        return {"symbol": symbol, "reports": [], "error": "空数据"}

    records = _parse_financial_df(df, symbol)
    if not records:
        logger.warning("解析后无有效记录: symbol=%s", symbol)
        return {"symbol": symbol, "reports": [], "error": "无有效记录"}

    for rec in records:
        try:
            _insert_or_update(session, rec)
        except Exception as exc:
            logger.warning("写入 DB 失败: symbol=%s, date=%s, error=%s", symbol, rec.get("report_date"), exc)

    session.commit()
    logger.info("财务数据写入成功: symbol=%s, count=%d", symbol, len(records))

    # 返回最新 4 期
    inserted = session.execute(
        text("""
            SELECT * FROM stock_financial
            WHERE symbol = :sym
            ORDER BY report_date DESC
            LIMIT 4
        """),
        {"sym": symbol},
    ).fetchall()

    result: dict[str, Any] = {"symbol": symbol, "reports": []}
    for row in inserted:
        report = dict(row._mapping)
        if report.get("report_date"):
            report["report_date"] = str(report["report_date"])
        for k, v in report.items():
            if hasattr(v, "to_dict"):
                report[k] = json.loads(json.dumps(v, ensure_ascii=False, default=str))
            elif hasattr(v, "real"):
                report[k] = float(v) if v is not None else None
            else:
                report[k] = v
        result["reports"].append(report)

    return result
