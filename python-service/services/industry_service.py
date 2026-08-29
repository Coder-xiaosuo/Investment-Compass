"""Industry classification service — 行业分类数据服务。"""
from __future__ import annotations

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


# ── 行业细分 → 粗分类映射（用于评分行业调整） ──────────────────────────────────
# 东财板块名是细粒度（白酒、半导体设备...），而 scorer 调整规则按粗分类
# （消费/医药/科技/金融/周期）模糊匹配，需要映射。匹配顺序优先。
_BOARD_TO_L2: list[tuple[tuple[str, ...], str]] = [
    (
        (
            "医药", "生物", "医疗", "制药", "中药", "疫苗", "医美", "医院", "药店",
        ),
        "医药",
    ),
    (
        (
            "白酒", "酿酒", "食品", "饮料", "家电", "零售", "旅游", "酒店", "餐饮",
            "农业", "养殖", "种植", "纺织", "服装", "商业", "贸易", "外贸",
            "免税", "美容", "教育", "家居", "轻工", "造纸", "包装", "陶瓷",
            "家具",
        ),
        "消费",
    ),
    (
        (
            "半导体", "芯片", "软件", "计算机", "电子", "通信", "人工智能",
            "云计算", "大数据", "互联网", "传媒", "游戏", "网络安全",
            "消费电子", "信息", "元器件", "光模块", "机器人", "智能",
            "仪器仪表",
        ),
        "科技",
    ),
    (
        ("银行", "证券", "保险", "金融", "信托", "期货", "多元金融"),
        "金融",
    ),
    (
        (
            "钢铁", "煤炭", "有色", "石油", "石化", "化工", "矿业", "稀土",
            "贵金属", "工业金属", "水泥", "建材", "航运", "船舶", "工程机械",
            "汽车", "重工", "电力", "公用事业", "地产", "房地产", "基建",
            "建筑", "交运", "物流",
        ),
        "周期",
    ),
]


def _l2_for_industry(industry_l1: str) -> str:
    """东财细分行业名 → 粗分类（消费/医药/科技/金融/周期），无法匹配时返回"其他"。"""
    if not industry_l1:
        return "其他"
    for keywords, l2 in _BOARD_TO_L2:
        if any(kw in industry_l1 for kw in keywords):
            return l2
    return "其他"


def get_industry(symbol: str, auto_sync: bool = True) -> dict[str, Any]:
    """Return a stock's industry classification from the DB.

    当 DB 无数据且 auto_sync=True 时，按需调用 sync_industry 拉取实时数据并
    写入 DB 后重新查询。

    Returns empty dict if not found.
    """
    code = _strip_suffix(symbol)
    if not code:
        return {}

    session = _session()
    try:
        row = session.execute(
            text("""
                SELECT symbol, stock_name, industry_l1, industry_l2, industry_l3, effective_date
                FROM stock_industry
                WHERE symbol = :sym
                ORDER BY effective_date DESC
                LIMIT 1
            """),
            {"sym": code},
        ).fetchone()

        if row is None:
            if auto_sync:
                logger.info("DB 中无 %s 的行业数据，按需同步", code)
                if sync_industry(code):
                    return get_industry(code, auto_sync=False)
            return {}

        return {
            "symbol": row.symbol,
            "stockName": row.stock_name,
            "industryL1": row.industry_l1,
            "industryL2": row.industry_l2,
            "industryL3": row.industry_l3,
            "effectiveDate": str(row.effective_date),
        }
    finally:
        session.close()


def sync_industry(symbol: str) -> bool:
    """Try to fetch industry info from AkShare and store it in DB.

    Returns True on success, False on failure.
    """
    code = _strip_suffix(symbol)
    if not code:
        logger.warning("sync_industry: invalid symbol %r", symbol)
        return False

    import akshare as ak
    from shared.akshare_throttle import with_retry

    @with_retry(max_retries=2)
    def _fetch_individual_info(code: str):
        return ak.stock_individual_info_em(symbol=code)

    @with_retry(max_retries=2)
    def _fetch_spot():
        return ak.stock_zh_a_spot()

    stock_name = ""
    industry_l1 = ""
    industry_l2: str | None = None
    industry_l3: str | None = None
    source = "akshare"
    today = date.today()

    # ── Primary: stock_individual_info_em ──────────────────────────────────
    try:
        df = _fetch_individual_info(code)
        if df is not None and not df.empty:
            item_col = "item" if "item" in df.columns else df.columns[0]
            val_col = "value" if "value" in df.columns else df.columns[1]
            for item, val in zip(df[item_col], df[val_col], strict=False):
                item_str = str(item).strip()
                if item_str in ("股票简称", "名称"):
                    stock_name = str(val).strip()
                elif item_str == "行业":
                    industry_l1 = str(val).strip()
    except Exception as exc:
        logger.warning("sync_industry stock_individual_info_em failed for %s: %s", code, exc)

    # ── Fallback: list industry boards (informational) ────────────────────
    if not industry_l1:
        try:
            df_board = ak.stock_board_industry_name_em()
            if df_board is not None and not df_board.empty:
                logger.info("sync_industry: got %d industry boards from EM", len(df_board))
        except Exception as exc:
            logger.warning("sync_industry stock_board_industry_name_em failed: %s", exc)

    # ── Get stock_name if still missing ────────────────────────────────────
    if not stock_name:
        try:
            df_spot = _fetch_spot()
            if df_spot is not None and not df_spot.empty:
                raw_code_col = "代码" if "代码" in df_spot.columns else "symbol"
                name_col = "名称" if "名称" in df_spot.columns else "name"
                row_spot = df_spot[df_spot[raw_code_col].astype(str).str.contains(code)]
                if not row_spot.empty:
                    stock_name = str(row_spot.iloc[0][name_col]).strip()
        except Exception as exc:
            logger.warning("sync_industry stock_zh_a_spot failed for %s: %s", code, exc)

    if not stock_name:
        logger.warning("sync_industry: could not determine stock name for %s", code)
        return False

    if not industry_l1:
        logger.warning("sync_industry: could not determine industry for %s", code)
        return False

    # 细分行业 → 粗分类（供评分行业调整使用）
    industry_l2 = _l2_for_industry(industry_l1)

    # ── Insert into DB ─────────────────────────────────────────────────────
    session = _session()
    try:
        session.execute(
            text("""
                INSERT INTO stock_industry (symbol, stock_name, industry_l1, industry_l2, industry_l3, source, effective_date)
                VALUES (:sym, :name, :l1, :l2, :l3, :src, :eff)
                ON DUPLICATE KEY UPDATE
                    stock_name = VALUES(stock_name),
                    industry_l1 = VALUES(industry_l1),
                    industry_l2 = VALUES(industry_l2),
                    industry_l3 = VALUES(industry_l3),
                    source = VALUES(source)
            """),
            {
                "sym": code,
                "name": stock_name,
                "l1": industry_l1,
                "l2": industry_l2,
                "l3": industry_l3,
                "src": source,
                "eff": today,
            },
        )
        session.commit()
        logger.info("sync_industry: %s (%s) -> %s", code, stock_name, industry_l1)
        return True
    except Exception as exc:
        session.rollback()
        logger.error("sync_industry DB insert failed for %s: %s", code, exc)
        return False
    finally:
        session.close()


def sync_hot_industries(top_n: int = 30, source: str = "auto") -> dict[str, Any]:
    """批量初始化热门行业板块的成分股行业分类。

    数据源：
      - ``em``   ：东财行业板块（细分，按总市值取前 top_n）
      - ``sina`` ：新浪行业板块（49 个粗分类，全量）
      - ``auto`` ：东财优先，拉取失败自动回退新浪

    流程：拉取板块列表 → 逐板块拉取成分股 → 写入 stock_industry
    （industry_l1=板块名, industry_l2=粗分类）。限流经 with_retry，断点续传跳过已初始化板块。

    Args:
        top_n: 东财模式下热门板块数量，默认 30。
        source: 数据源（auto/em/sina），默认 auto。

    Returns:
        {"source": str, "total_boards": n, "initialized_boards": n, "total_symbols": n, "errors": [...]}
    """
    import akshare as ak
    from shared.akshare_throttle import with_retry

    @with_retry(max_retries=3)
    def _fetch_boards_em():
        return ak.stock_board_industry_name_em()

    @with_retry(max_retries=3)
    def _fetch_boards_sina():
        return ak.stock_sector_spot(indicator="新浪行业")

    @with_retry(max_retries=3)
    def _fetch_cons_em(board: str):
        return ak.stock_board_industry_cons_em(symbol=board)

    @with_retry(max_retries=3)
    def _fetch_cons_sina(label: str):
        return ak.stock_sector_detail(sector=label)

    # ── 解析成分股为 (code, name) 列表（兼容两数据源列名） ──────────────────
    def _parse_cons(df, code_col: str, name_col: str) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = []
        for _, r in df.iterrows():
            code = str(r[code_col]).strip()
            name = str(r[name_col]).strip()
            if not code.isdigit() or len(code) != 6:
                continue
            items.append((code, name))
        return items

    # ── 选择数据源，构建板块任务列表 ────────────────────────────────────────
    boards: list[tuple[str, Any]] = []  # (板块名, 成分股拉取函数)
    used_source = ""

    if source in ("auto", "em"):
        try:
            df_em = _fetch_boards_em()
            df_em = df_em.sort_values("总市值", ascending=False).head(top_n)
            boards = [(n, lambda n=n: _parse_cons(_fetch_cons_em(n), "代码", "名称")) for n in df_em["板块名称"].tolist()]
            used_source = "em"
            logger.info("使用东财数据源：%d 个热门板块", len(boards))
        except Exception as exc:
            if source == "em":
                logger.error("东财板块列表拉取失败: %s", exc)
                return {"error": str(exc), "initialized_boards": 0, "total_symbols": 0, "errors": [str(exc)]}
            logger.warning("东财板块列表拉取失败，回退新浪: %s", exc)

    if not boards and source in ("auto", "sina"):
        try:
            df_sina = _fetch_boards_sina()
            boards = [
                (name, lambda label=label: _parse_cons(_fetch_cons_sina(label), "code", "name"))
                for name, label in zip(df_sina["板块"].tolist(), df_sina["label"].tolist())
            ]
            used_source = "sina"
            logger.info("使用新浪数据源：%d 个行业板块", len(boards))
        except Exception as exc:
            logger.error("新浪板块列表拉取失败: %s", exc)
            return {"error": str(exc), "initialized_boards": 0, "total_symbols": 0, "errors": [str(exc)]}

    if not boards:
        return {"error": "无可用数据源", "initialized_boards": 0, "total_symbols": 0, "errors": []}

    today = date.today()
    session = _session()
    total_symbols = 0
    initialized_boards = 0
    errors: list[str] = []

    try:
        for board, fetch_cons in boards:
            # 断点续传：板块已有数据则跳过
            existing = session.execute(
                text("SELECT COUNT(*) FROM stock_industry WHERE industry_l1 = :b"),
                {"b": board},
            ).scalar()
            if existing:
                logger.info("板块 %s 已初始化（%d 条），跳过", board, existing)
                initialized_boards += 1
                continue

            try:
                items = fetch_cons()
            except Exception as exc:
                errors.append(f"{board}: {exc}")
                logger.warning("拉取板块 %s 成分股失败: %s", board, exc)
                continue

            if not items:
                continue

            l2 = _l2_for_industry(board)
            for code, name in items:
                session.execute(
                    text("""
                        INSERT IGNORE INTO stock_industry
                            (symbol, stock_name, industry_l1, industry_l2, industry_l3, source, effective_date)
                        VALUES (:sym, :name, :l1, :l2, NULL, :src, :eff)
                    """),
                    {
                        "sym": code,
                        "name": name,
                        "l1": board,
                        "l2": l2,
                        "src": f"akshare_{used_source}",
                        "eff": today,
                    },
                )

            session.commit()
            total_symbols += len(items)
            initialized_boards += 1
            logger.info("板块 %s 初始化完成：%d 只（L2=%s）", board, len(items), l2)
    except Exception as exc:
        session.rollback()
        logger.error("批量初始化失败: %s", exc)
        errors.append(str(exc))
    finally:
        session.close()

    logger.info(
        "热门行业初始化完成（%s）：%d/%d 板块，%d 只股票，%d 个错误",
        used_source, initialized_boards, len(boards), total_symbols, len(errors),
    )
    return {
        "source": used_source,
        "total_boards": len(boards),
        "initialized_boards": initialized_boards,
        "total_symbols": total_symbols,
        "errors": errors,
    }


def get_all_industries() -> list[str]:
    """Return all unique industry_l1 names from stock_industry table."""
    session = _session()
    try:
        rows = session.execute(
            text("SELECT DISTINCT industry_l1 FROM stock_industry ORDER BY industry_l1"),
        ).fetchall()
        return [r.industry_l1 for r in rows if r.industry_l1]
    finally:
        session.close()
