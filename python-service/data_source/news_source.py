"""资讯数据适配层 — 封装 AkShare 新闻/快讯/研报接口，输出标准化结构。

与 akshare_source.py 的定位不同：
- akshare_source.py：K线行情数据流（订阅制/推送语义）
- news_source.py：资讯类拉取接口（按需拉取+增量同步）

所有 AkShare 调用统一走 shared.akshare_throttle 的限流 + 重试 + 缓存机制。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, date
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
pd.options.future.infer_string = False  # 修复 stock_news_em 的 pyarrow ArrowInvalid

logger = logging.getLogger(__name__)

_CN_TZ = ZoneInfo("Asia/Shanghai")


# ── 标准化输出数据结构 ──────────────────────────────────────────────────────

@dataclass
class NewsItem:
    """统一新闻条目（个股新闻 / 财联社电报 / 全球资讯 归一化输出）。"""
    source: str                     # 来源标识: 'em_news' / 'cls_telegraph' / 'em_global'
    title: str                      # 标题
    content: str                    # 正文/摘要
    publish_time: datetime          # 发布时间
    url: str = ""                   # 原文链接
    symbol: str | None = None       # 关联股票代码（None = 全市场资讯）
    source_name: str = ""           # 文章来源（如"证券时报网""财联社"）

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "title": self.title,
            "content": self.content,
            "publish_time": self.publish_time.strftime("%Y-%m-%d %H:%M:%S"),
            "url": self.url,
            "symbol": self.symbol,
            "source_name": self.source_name,
        }


@dataclass
class ResearchReport:
    """统一券商研报条目。"""
    symbol: str                     # 股票代码（6位数字）
    stock_name: str                 # 股票简称
    title: str                      # 研报标题
    institute: str                  # 机构：中信证券/国泰君安/国信证券...
    rating: str                     # 评级：买入/增持/中性/减持/卖出
    publish_date: date              # 发布日期
    pdf_url: str = ""               # 研报PDF链接
    eps_2026: float | None = None   # 2026预测EPS
    eps_2027: float | None = None   # 2027预测EPS
    eps_2028: float | None = None   # 2028预测EPS
    pe_2026: float | None = None    # 2026预测PE
    pe_2027: float | None = None    # 2027预测PE

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "stock_name": self.stock_name,
            "title": self.title,
            "institute": self.institute,
            "rating": self.rating,
            "publish_date": self.publish_date.isoformat(),
            "pdf_url": self.pdf_url,
            "eps_2026": self.eps_2026,
            "eps_2027": self.eps_2027,
            "eps_2028": self.eps_2028,
            "pe_2026": self.pe_2026,
            "pe_2027": self.pe_2027,
        }


# ── 列名候选映射（解决 AkShare 版本升级时列名变化问题） ────────────────────

def _get_val(row: "pd.Series", candidates: list[str], default: Any = "") -> Any:
    """从 DataFrame row 中按候选列名依次尝试取值，取不到返回 default。"""
    for c in candidates:
        if c in row.index:
            val = row[c]
            if val is not None and (not isinstance(val, float) or val == val):  # 非NaN
                return val
    return default


def _to_float(val: Any) -> float | None:
    """安全的 float 转换，失败返回 None。"""
    if val is None:
        return None
    try:
        s = str(val).strip()
        if not s or s in ("-", "--", "None", "nan", "NaN"):
            return None
        return float(s)
    except (ValueError, TypeError):
        return None


def _parse_datetime(date_str: str, time_str: str = "") -> datetime:
    """兼容多种格式的时间解析。"""
    date_str = str(date_str or "").strip()
    time_str = str(time_str or "").strip()
    combined = f"{date_str} {time_str}".strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d",
        "%Y%m%d %H:%M:%S",
        "%Y%m%d",
    ):
        try:
            return datetime.strptime(combined, fmt).replace(tzinfo=_CN_TZ)
        except ValueError:
            continue
    # 最后兜底：尝试 pandas 解析
    try:
        ts = pd.to_datetime(combined)
        return ts.to_pydatetime().replace(tzinfo=_CN_TZ)
    except Exception:
        logger.warning("无法解析时间: date=%s time=%s", date_str, time_str)
        return datetime.now(tz=_CN_TZ)


def _parse_date(date_str: str) -> date:
    """解析日期。"""
    dt = _parse_datetime(date_str)
    return dt.date()


def _strip_symbol_suffix(symbol: str | None) -> str:
    """'000001.SZ' / 'sz000001' / '000001' 归一化为 6 位数字。"""
    if not symbol:
        return ""
    digits = re.sub(r"\D", "", str(symbol))
    return digits[-6:] if len(digits) >= 6 else digits


def _extract_symbol_from_text(text: str) -> str | None:
    """从正文中提取 6 位股票代码（例如财联社快讯里常出现【宁德时代300750】）。

    为避免误匹配金额数字（如"300000万元""500000股"），要求6位数字
    前后紧邻中文字符或【】括号，且后面不跟"万/亿/元/股/份"等量词。
    """
    if not text:
        return None
    # 匹配：前面是中文/【/( 或行首，后面不是量词
    for m in re.finditer(r"(?<!\d)(\d{6})(?!\d)", str(text)):
        code = m.group(1)
        if code == "000000" or code.startswith(("19", "20")):
            continue
        # 检查后面是否紧跟量词 → 是则跳过（金额而非股票代码）
        after = str(text)[m.end():m.end() + 2]
        if after and after[0] in "万亿股份元%倍":
            continue
        # 检查前面是否有中文字符或括号（股票代码通常跟在公司名后）
        before_pos = max(0, m.start() - 4)
        before = str(text)[before_pos:m.start()]
        if before and re.search(r"[\u4e00-\u9fff【(]$", before):
            return code
    return None


# ── NewsSource 主类 ────────────────────────────────────────────────────────

class NewsSource:
    """资讯数据源适配器 — 封装 AkShare 资讯接口，字段归一 + 节流重试。"""

    def __init__(self) -> None:
        self._connected = False

    # ── 连接管理 ───────────────────────────────────────────────────────────

    def connect(self) -> None:
        import akshare  # noqa: F401
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    # ── 底层调用封装（统一节流+重试，复用 akshare_throttle） ────────────────

    @staticmethod
    def _call(label: str, fn, *, retries: int = 3) -> Any:
        """带节流+重试+超时的 AkShare 调用封装。"""
        from shared.akshare_throttle import throttle, run_with_timeout
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                throttle()
                # 单次拉取限时 12s，配合外层整体超时快速降级
                return run_with_timeout(fn, 12.0)
            except Exception as exc:
                last_exc = exc
                if attempt < retries - 1:
                    wait = (attempt + 1) * 2.0
                    logger.warning(
                        "NewsSource %s 重试 %d/%d %.1fs: %s",
                        label, attempt + 1, retries, wait, exc,
                    )
                    import time
                    time.sleep(wait)
                else:
                    logger.error("NewsSource %s 失败 (已重试%d): %s", label, retries, exc)
        assert last_exc is not None
        raise last_exc

    # ── 个股新闻（东方财富） ───────────────────────────────────────────────

    def get_stock_news(self, symbol: str) -> list[NewsItem]:
        """获取个股新闻列表。

        Args:
            symbol: 支持 6 位数字 / 带 sz/sh 前缀 / 带 .SZ/.SH 后缀
        """
        import akshare as ak
        code = _strip_symbol_suffix(symbol)
        if not code:
            raise ValueError(f"无效的股票代码: {symbol!r}")

        df = self._call(
            f"stock_news_em({code})",
            lambda: ak.stock_news_em(symbol=code),
        )
        if df is None or df.empty:
            return []

        results: list[NewsItem] = []
        for _, row in df.iterrows():
            raw_time = _get_val(row, ["发布时间", "datetime", "time", "日期"])
            results.append(NewsItem(
                source="em_news",
                title=str(_get_val(row, ["新闻标题", "标题", "title"])),
                content=str(_get_val(row, ["新闻内容", "内容", "content", "摘要"])),
                publish_time=_parse_datetime(str(raw_time)),
                url=str(_get_val(row, ["新闻链接", "url", "链接", "原文链接"])),
                symbol=code,
                source_name=str(_get_val(row, ["文章来源", "source", "来源"])),
            ))
        return results

    # ── 财联社 7×24 快讯 ──────────────────────────────────────────────────

    def get_global_telegraph(self) -> list[NewsItem]:
        """获取财联社电报（分钟级全市场快讯）。"""
        import akshare as ak
        df = self._call("stock_info_global_cls", lambda: ak.stock_info_global_cls())
        if df is None or df.empty:
            return []

        results: list[NewsItem] = []
        for _, row in df.iterrows():
            date_s = str(_get_val(row, ["发布日期", "date", "日期"]))
            time_s = str(_get_val(row, ["发布时间", "time", "时间"]))
            content = str(_get_val(row, ["内容", "content", "正文"]))
            title = str(_get_val(row, ["标题", "title"])).strip()
            # 财联社快讯通常没有单独标题，用正文前60字作为标题
            if not title:
                title = content[:60] + ("..." if len(content) > 60 else "")
            # 快讯里可能直接 @ 某只股票
            symbol = _extract_symbol_from_text(content)
            results.append(NewsItem(
                source="cls_telegraph",
                title=title,
                content=content,
                publish_time=_parse_datetime(date_s, time_s),
                url="",
                symbol=symbol,
                source_name="财联社",
            ))
        return results

    # ── 东方财富全球财经资讯 ────────────────────────────────────────────────

    def get_global_news_em(self) -> list[NewsItem]:
        """获取东方财富全球财经资讯（宏观/行业/个股综合）。"""
        import akshare as ak
        df = self._call("stock_info_global_em", lambda: ak.stock_info_global_em())
        if df is None or df.empty:
            return []

        results: list[NewsItem] = []
        for _, row in df.iterrows():
            raw_time = _get_val(row, ["发布时间", "datetime", "时间", "日期"])
            content = str(_get_val(row, ["内容", "content", "摘要", "新闻内容"]))
            symbol = _extract_symbol_from_text(content)
            results.append(NewsItem(
                source="em_global",
                title=str(_get_val(row, ["新闻标题", "标题", "title"])),
                content=content,
                publish_time=_parse_datetime(str(raw_time)),
                url=str(_get_val(row, ["新闻链接", "url", "链接"])),
                symbol=symbol,
                source_name=str(_get_val(row, ["文章来源", "source", "来源", "东方财富"])),
            ))
        return results

    # ── 券商个股研报（东方财富） ────────────────────────────────────────────

    def get_research_reports(self, symbol: str | None = None, limit: int = 500) -> list[ResearchReport]:
        """获取券商个股研报。

        Args:
            symbol: 可选，指定只返回某只股票的研报；None 则返回全量数据后再筛选
            limit: 全量拉取时的最大条数（避免一次拉几万条撑爆内存）。
                   指定 symbol 时自动放大到 3000，确保覆盖热门股。
        """
        import akshare as ak
        fetch_limit = 3000 if symbol else limit
        df = self._call(
            f"stock_research_report_em(limit={fetch_limit})",
            lambda: ak.stock_research_report_em().head(fetch_limit),
        )
        if df is None or df.empty:
            return []

        # 如果指定了 symbol，先做 DataFrame 级过滤
        code = _strip_symbol_suffix(symbol) if symbol else ""
        if code:
            symbol_col = _get_val(
                df.iloc[0],
                ["股票代码", "代码", "symbol"],
                None,
            ) if len(df) > 0 else None
            if symbol_col is not None:
                col_name = None
                for c in ["股票代码", "代码", "symbol"]:
                    if c in df.columns:
                        col_name = c
                        break
                if col_name:
                    df = df[df[col_name].astype(str).str.contains(code, na=False)]

        results: list[ResearchReport] = []
        for _, row in df.iterrows():
            sym = _strip_symbol_suffix(str(_get_val(row, ["股票代码", "代码", "symbol"])))
            if not sym:
                continue
            if code and sym != code:
                continue
            results.append(ResearchReport(
                symbol=sym,
                stock_name=str(_get_val(row, ["股票简称", "名称", "stock_name"])),
                title=str(_get_val(row, ["报告名称", "报告标题", "标题", "title"])),
                institute=str(_get_val(row, ["机构", "作者", "institute", "机构名称"])),
                rating=str(_get_val(row, ["东财评级", "评级", "rating", "投资评级"])),
                publish_date=_parse_date(str(_get_val(row, ["日期", "发布日期", "date", "时间"]))),
                pdf_url=str(_get_val(row, ["报告PDF链接", "PDF链接", "报告链接", "pdf_url", "链接"])),
                eps_2026=_to_float(_get_val(row, ["2026-盈利预测-收益", "2026预测EPS", "预测2026每股收益"], None)),
                eps_2027=_to_float(_get_val(row, ["2027-盈利预测-收益", "2027预测EPS", "预测2027每股收益"], None)),
                eps_2028=_to_float(_get_val(row, ["2028-盈利预测-收益", "2028预测EPS", "预测2028每股收益"], None)),
                pe_2026=_to_float(_get_val(row, ["2026-盈利预测-市盈率", "预测2026PE"], None)),
                pe_2027=_to_float(_get_val(row, ["2027-盈利预测-市盈率", "预测2027PE"], None)),
            ))
        return results
