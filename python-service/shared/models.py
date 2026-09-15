# ============================================================
# Investment-Compass — SQLAlchemy ORM Models（收敛后）
#
# 说明：本项目数据访问以原生 SQL 为主（services/ 下统一使用
#       sqlalchemy.text()），此处仅保留确有 ORM 需求的模型：
#         - DecisionCard    技术分析 Agent 的决策卡片
#         - StockNews       财经新闻/快讯
#         - ResearchReport  券商个股研报
#
# 历史：本文件原为 FinAgentOS（模拟交易平台，另一套产品）的 ORM 定义，
#       含 users/workspaces/orders/positions/audit_chain/factor_library 等
#       19 个类。这些类对应的表在 Investment-Compass 中从未使用，已于
#       V016 迁移中 DROP，相应地移除其 ORM 声明。
#       详见 docs/data-platform/06-数据库瘦身审计报告.md
#
# 注意：其余在用表（market_data / stock_metadata / conversation / message /
#       agent_threads / kline_coverage / sync_task / stock_financial /
#       stock_industry / stock_valuation_daily / watchlist /
#       style_profiles / feedback_signals / checkpoint* 等）的表结构
#       以 sql/ 下迁移脚本与真实库为准，不在此声明——如需 ORM 映射请
#       先核对 sql/ 中的最新 DDL，避免与真实库脱节。
# ============================================================

from datetime import datetime
from sqlalchemy import (
    Column, BigInteger, String, Numeric, Text, DateTime,
    JSON, Index, UniqueConstraint
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


# ============================================================
# 决策卡片（技术分析 Agent 的输出物）
# ============================================================

class DecisionCard(Base):
    __tablename__ = 'decision_cards'
    __table_args__ = (UniqueConstraint('trace_id', name='uq_dc_trace'),)
    id                  = Column(BigInteger, primary_key=True, autoincrement=True)
    trace_id            = Column(String(36), nullable=False)
    agent_id            = Column(BigInteger, nullable=False, index=True)
    symbol              = Column(String(20), nullable=False, index=True)
    stock_name          = Column(String(50), nullable=True)
    action              = Column(String(10), nullable=False)
    confidence          = Column(Numeric(4, 3), nullable=True)
    current_price       = Column(Numeric(10, 2), nullable=True)
    suggested_position  = Column(Numeric(5, 2), nullable=True)
    stop_loss_price     = Column(Numeric(10, 2), nullable=True)
    take_profit_price   = Column(Numeric(10, 2), nullable=True)
    reasoning           = Column(Text, nullable=True)
    data_sources        = Column(JSON, default=list)
    audit_hash          = Column(String(64), nullable=True)
    status              = Column(String(10), default='PENDING', index=True)
    market_cycle        = Column(String(50), nullable=False, default='')
    sector              = Column(String(50), nullable=False, default='')
    pattern             = Column(String(100), nullable=False, default='')
    review_outcome      = Column(JSON, nullable=True)
    executed_at         = Column(DateTime, nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow)


# ============================================================
# 资讯与研报
# ============================================================

class StockNews(Base):
    """财经新闻/快讯。"""
    __tablename__ = 'stock_news'
    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    source          = Column(String(20), nullable=False, index=True)   # em_news / cls_telegraph / em_global
    symbol          = Column(String(20), nullable=True, index=True)    # 关联股票代码（None=全市场）
    title           = Column(String(512), nullable=False)
    content         = Column(Text, nullable=True)
    publish_time    = Column(DateTime, nullable=False, index=True)
    url             = Column(String(1024), nullable=True)
    source_name     = Column(String(64), nullable=True)                # 文章来源（证券时报/财联社等）
    fetched_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
    __table_args__ = (
        UniqueConstraint('source', 'publish_time', 'title', name='uq_news_source_time_title'),
        Index('idx_news_symbol_time', 'symbol', 'publish_time'),
    )


class ResearchReport(Base):
    """券商个股研报。"""
    __tablename__ = 'research_reports'
    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    symbol          = Column(String(20), nullable=False, index=True)
    stock_name      = Column(String(100), nullable=True)
    title           = Column(String(512), nullable=False)
    institute       = Column(String(64), nullable=True, index=True)    # 机构
    analyst         = Column(String(64), nullable=True)                # 分析师
    rating          = Column(String(20), nullable=True, index=True)    # 买入/增持/中性/减持/卖出
    target_price    = Column(Numeric(10, 3), nullable=True)
    eps_2025        = Column(Numeric(10, 4), nullable=True)
    eps_2026        = Column(Numeric(10, 4), nullable=True)
    eps_2027        = Column(Numeric(10, 4), nullable=True)
    eps_2028        = Column(Numeric(10, 4), nullable=True)
    pe_2025         = Column(Numeric(10, 3), nullable=True)
    pe_2026         = Column(Numeric(10, 3), nullable=True)
    pe_2027         = Column(Numeric(10, 3), nullable=True)
    publish_date    = Column(DateTime, nullable=False, index=True)
    pdf_url         = Column(String(1024), nullable=True)
    fetched_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint('symbol', 'institute', 'publish_date', 'title', name='uq_rr_symbol_ins_date_title'),
        Index('idx_rr_rating', 'rating'),
        Index('idx_rr_symbol_date', 'symbol', 'publish_date'),
    )
