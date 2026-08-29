# ============================================================
# FinAgentOS — SQLAlchemy ORM Models
# 支持 MySQL + PostgreSQL + SQLite 三数据库
# 应用层只需改 DATABASE_URL 环境变量
# ============================================================
# MySQL:  mysql+pymysql://user:pass@host:3306/finagentos
# PG:     postgresql+psycopg2://user:pass@host:5432/finagentos
# SQLite: sqlite:///data/finagentos.db
# ============================================================

from datetime import datetime
from sqlalchemy import (
    Column, BigInteger, String, Integer, Numeric, Text, DateTime,
    Boolean, JSON, Index, ForeignKey, UniqueConstraint, create_engine
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = 'users'
    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    username        = Column(String(50), nullable=False, unique=True)
    password_hash   = Column(String(255), nullable=False)
    role            = Column(String(20), default='USER')
    is_active       = Column(Boolean, default=True)
    password_changed_at = Column(DateTime, nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at      = Column(DateTime, nullable=True)
    workspaces      = relationship('Workspace', back_populates='user')


class Workspace(Base):
    __tablename__ = 'workspaces'
    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id         = Column(BigInteger, ForeignKey('users.id'), nullable=False)
    name            = Column(String(100), nullable=False)
    description     = Column(String(500), default='')
    is_default      = Column(Boolean, default=False)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at      = Column(DateTime, nullable=True)
    user            = relationship('User', back_populates='workspaces')
    sub_accounts    = relationship('SubAccount', back_populates='workspace')
    agents          = relationship('Agent', back_populates='workspace')


class SubAccount(Base):
    __tablename__ = 'sub_accounts'
    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id    = Column(BigInteger, ForeignKey('workspaces.id'), nullable=False)
    name            = Column(String(100), nullable=False)
    initial_capital = Column(Numeric(15, 2), default=0.00)
    current_cash    = Column(Numeric(15, 2), default=0.00)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at      = Column(DateTime, nullable=True)
    workspace       = relationship('Workspace', back_populates='sub_accounts')


class RefreshToken(Base):
    __tablename__ = 'refresh_tokens'
    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id         = Column(BigInteger, nullable=False)
    token           = Column(String(500), nullable=False)
    expires_at      = Column(DateTime, nullable=False)
    created_at      = Column(DateTime, default=datetime.utcnow)


class Agent(Base):
    __tablename__ = 'agents'
    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    agent_type      = Column(String(30), nullable=False)
    name            = Column(String(200), nullable=False)
    workspace_id    = Column(BigInteger, ForeignKey('workspaces.id'), nullable=False)
    sub_account_id  = Column(BigInteger, nullable=True)
    llm_config      = Column(JSON, default=dict)
    status          = Column(String(20), default='ACTIVE')
    metadata_       = Column('metadata', JSON, default=dict)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at      = Column(DateTime, nullable=True)
    workspace       = relationship('Workspace', back_populates='agents')
    orders          = relationship('Order', back_populates='agent')
    positions       = relationship('Position', back_populates='agent')
    decision_logs   = relationship('DecisionLog', back_populates='agent')
    __table_args__ = (Index('idx_agents_workspace', 'workspace_id'), Index('idx_agents_type', 'agent_type'))


class Order(Base):
    __tablename__ = 'orders'
    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    agent_id        = Column(BigInteger, ForeignKey('agents.id'), nullable=False)
    trace_id        = Column(String(36), nullable=False, index=True)
    symbol          = Column(String(20), nullable=False)
    symbol_name     = Column(String(50), nullable=True)
    direction       = Column(String(4), nullable=False)
    order_type      = Column(String(6), default='MARKET')
    price           = Column(Numeric(10, 3), nullable=True)
    quantity        = Column(Integer, nullable=False)
    status          = Column(String(10), default='PENDING', index=True)
    fill_price      = Column(Numeric(10, 3), nullable=True)
    reject_reason   = Column(String(200), nullable=True)
    audit_hash      = Column(String(64), nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    agent           = relationship('Agent', back_populates='orders')
    __table_args__ = (Index('idx_orders_agent', 'agent_id'),)


class Position(Base):
    __tablename__ = 'positions'
    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    agent_id        = Column(BigInteger, ForeignKey('agents.id'), nullable=False)
    symbol          = Column(String(20), nullable=False)
    symbol_name     = Column(String(50), nullable=True)
    quantity        = Column(Integer, default=0)
    avg_cost        = Column(Numeric(10, 3), default=0)
    current_price   = Column(Numeric(10, 3), nullable=True)
    market_value    = Column(Numeric(15, 2), nullable=True)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    agent           = relationship('Agent', back_populates='positions')
    __table_args__ = (UniqueConstraint('agent_id', 'symbol', name='uk_pos_agent_symbol'),)


class NavSnapshot(Base):
    __tablename__ = 'nav_snapshots'
    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    agent_id        = Column(BigInteger, nullable=False)
    snapshot_date   = Column(DateTime, nullable=False)
    total_asset     = Column(Numeric(15, 2), nullable=False)
    daily_return    = Column(Numeric(8, 6), nullable=True)
    cumulative_return = Column(Numeric(8, 6), nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint('agent_id', 'snapshot_date', name='uk_nav_agent_date'),)


class Watchlist(Base):
    __tablename__ = 'watchlists'
    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    agent_id        = Column(BigInteger, nullable=False)
    symbol          = Column(String(20), nullable=False)
    symbol_name     = Column(String(50), nullable=False)
    added_at        = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint('agent_id', 'symbol', name='uk_wl_agent_symbol'),)


class StopLossOrder(Base):
    __tablename__ = 'stop_loss_orders'
    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    agent_id        = Column(BigInteger, nullable=False)
    trace_id        = Column(String(36), nullable=False)
    symbol          = Column(String(20), nullable=False)
    symbol_name     = Column(String(50), nullable=True)
    trigger_price   = Column(Numeric(10, 3), nullable=False)
    quantity        = Column(Integer, nullable=False)
    status          = Column(String(10), default='ACTIVE')
    triggered_at    = Column(DateTime, nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (Index('idx_slo_agent', 'agent_id', 'status'),)


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


class AuditChain(Base):
    __tablename__ = 'audit_chain'
    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    trace_id        = Column(String(36), nullable=False, index=True)
    agent_type      = Column(String(30), nullable=False)
    agent_id        = Column(BigInteger, nullable=True)
    action_type     = Column(String(50), nullable=False)
    payload         = Column(JSON, nullable=False)
    previous_hash   = Column(String(64), nullable=False)
    current_hash    = Column(String(64), nullable=False, index=True)
    created_at      = Column(DateTime, default=datetime.utcnow)


class CircuitBreakerEvent(Base):
    __tablename__ = 'circuit_breaker_events'
    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    trace_id        = Column(String(36), nullable=False)
    agent_id        = Column(BigInteger, nullable=False)
    trigger_reason  = Column(String(100), nullable=False)
    threshold_value = Column(Numeric(10, 4), nullable=True)
    current_value   = Column(Numeric(10, 4), nullable=True)
    action_taken    = Column(String(100), nullable=False)
    resolved_at     = Column(DateTime, nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (Index('idx_cbe_agent', 'agent_id'), Index('idx_cbe_trace', 'trace_id'))


class FactorLibrary(Base):
    __tablename__ = 'factor_library'
    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    factor_name     = Column(String(100), nullable=False, unique=True)
    formula         = Column(Text, nullable=False)
    source          = Column(String(100), nullable=True)
    category        = Column(String(50), nullable=True)
    ic_mean         = Column(Numeric(8, 6), nullable=True)
    ic_ir           = Column(Numeric(8, 6), nullable=True)
    oos_ic          = Column(Numeric(8, 6), nullable=True)
    is_active       = Column(Boolean, default=False)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    ic_records      = relationship('FactorICRecord', back_populates='factor')


class FactorICRecord(Base):
    __tablename__ = 'factor_ic_records'
    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    factor_id       = Column(BigInteger, ForeignKey('factor_library.id'), nullable=False)
    test_date       = Column(DateTime, nullable=False)
    ic_value        = Column(Numeric(8, 6), nullable=True)
    rank_ic         = Column(Numeric(8, 6), nullable=True)
    is_oos          = Column(Boolean, default=False)
    created_at      = Column(DateTime, default=datetime.utcnow)
    factor          = relationship('FactorLibrary', back_populates='ic_records')
    __table_args__ = (Index('idx_fir_factor', 'factor_id'), Index('idx_fir_date', 'test_date'))


class SkillExport(Base):
    __tablename__ = 'skill_exports'
    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    skill_id        = Column(String(100), nullable=False, unique=True)
    name            = Column(String(200), nullable=False)
    agent_id        = Column(BigInteger, nullable=True)
    version         = Column(String(20), nullable=False)
    strategy_type   = Column(String(50), nullable=True)
    perf_summary    = Column(JSON, default=dict)
    file_path       = Column(String(500), nullable=True)
    export_count    = Column(Integer, default=0)
    last_exported_at = Column(DateTime, nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)


class DecisionLog(Base):
    __tablename__ = 'decision_logs'
    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    trace_id        = Column(String(36), nullable=False)
    agent_id        = Column(BigInteger, ForeignKey('agents.id'), nullable=False)
    agent_type      = Column(String(30), nullable=False)
    input_summary   = Column(JSON, default=dict)
    output_summary  = Column(JSON, default=dict)
    confidence      = Column(Numeric(4, 3), nullable=True)
    latency_ms      = Column(Integer, nullable=True)
    status          = Column(String(20), default='SUCCESS')
    error_message   = Column(Text, nullable=True)
    token_cost      = Column(Integer, default=0)
    audit_hash      = Column(String(64), nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    agent           = relationship('Agent', back_populates='decision_logs')
    __table_args__ = (
        Index('idx_dl_trace', 'trace_id'), Index('idx_dl_agent', 'agent_id'),
        Index('idx_dl_type', 'agent_type'), Index('idx_dl_created', 'created_at'),
    )


class SystemAlert(Base):
    __tablename__ = 'system_alerts'
    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    alert_type      = Column(String(30), nullable=False)
    severity        = Column(String(10), nullable=False)
    source          = Column(String(100), nullable=True)
    message         = Column(Text, nullable=True)
    details         = Column(JSON, default=dict)
    is_resolved     = Column(Boolean, default=False)
    created_at      = Column(DateTime, default=datetime.utcnow)
    resolved_at     = Column(DateTime, nullable=True)
    __table_args__ = (
        Index('idx_sa_type', 'alert_type'), Index('idx_sa_severity', 'severity'),
        Index('idx_sa_resolved', 'is_resolved'),
    )


class DataSourceStatus(Base):
    __tablename__ = 'data_source_status'
    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    source_name     = Column(String(50), nullable=False, unique=True)
    status          = Column(String(10), default='ONLINE')
    latency_ms      = Column(Integer, default=0)
    last_success_at = Column(DateTime, nullable=True)
    last_error_at   = Column(DateTime, nullable=True)
    error_count     = Column(Integer, default=0)
    check_count     = Column(Integer, default=0)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TaskRun(Base):
    __tablename__ = 'task_runs'
    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id          = Column(String(36), nullable=False, unique=True)
    task_type       = Column(String(30), nullable=False)
    trigger_type    = Column(String(10), default='SCHEDULED')
    status          = Column(String(10), default='RUNNING')
    agent_type      = Column(String(30), nullable=True)
    input_params    = Column(JSON, default=dict)
    output_summary  = Column(JSON, default=dict)
    error_message   = Column(Text, nullable=True)
    audit_hash      = Column(String(64), nullable=True)
    started_at      = Column(DateTime, nullable=True)
    completed_at    = Column(DateTime, nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (
        Index('idx_tr_type', 'task_type'), Index('idx_tr_status', 'status'),
        Index('idx_tr_created', 'created_at'),
    )


class StockMetadata(Base):
    __tablename__ = 'stock_metadata'
    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    symbol          = Column(String(20), nullable=False, unique=True)
    stock_name      = Column(String(100), nullable=False)
    type            = Column(String(20), default='STOCK')
    source          = Column(String(30), default='akshare')
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (
        Index('idx_sm_type', 'type'), Index('idx_sm_active', 'is_active'),
    )


class MarketData(Base):
    __tablename__ = 'market_data'
    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    symbol          = Column(String(20), nullable=False)
    trade_date      = Column(DateTime, nullable=False)
    timeframe       = Column(String(10), default='1d')
    ts_open         = Column(BigInteger, nullable=False)
    open            = Column(Numeric(10, 3), nullable=False)
    high            = Column(Numeric(10, 3), nullable=False)
    low             = Column(Numeric(10, 3), nullable=False)
    close           = Column(Numeric(10, 3), nullable=False)
    volume          = Column(BigInteger, default=0)
    amount          = Column(Numeric(15, 2), default=0.00)
    pct_chg         = Column(Numeric(8, 4), nullable=True)
    closed          = Column(Boolean, default=True)
    fetched_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint('symbol', 'trade_date', 'timeframe', name='uk_md_symbol_date_tf'),
        Index('idx_md_symbol', 'symbol'),
        Index('idx_md_trade_date', 'trade_date'),
        Index('idx_md_fetched', 'fetched_at'),
    )


class Conversation(Base):
    __tablename__ = 'conversation'
    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    title           = Column(String(128), default='新会话')
    user_id         = Column(BigInteger, nullable=True)
    status          = Column(Integer, default=1)
    summary         = Column(Text, nullable=True)
    token_count     = Column(Integer, default=0)
    message_count   = Column(Integer, default=0)
    context_tokens  = Column(Integer, default=0)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (
        Index('idx_conv_user_status', 'user_id', 'status'),
        Index('idx_conv_updated_at', 'updated_at'),
        Index('idx_conv_status_created', 'status', 'created_at'),
    )


class Message(Base):
    __tablename__ = 'message'
    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id = Column(BigInteger, nullable=False)
    role            = Column(String(16), nullable=False)
    content         = Column(Text, nullable=True)
    content_type    = Column(String(32), default='text')
    card_data       = Column(JSON, nullable=True)
    token_count     = Column(Integer, default=0)
    sequence        = Column(Integer, nullable=False)
    parent_id       = Column(BigInteger, nullable=True)
    tool_name       = Column(String(64), nullable=True)
    tool_result     = Column(JSON, nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint('conversation_id', 'sequence', name='uq_msg_conv_seq'),
        Index('idx_msg_parent', 'parent_id'),
        Index('idx_msg_created', 'created_at'),
    )


class AgentThread(Base):
    """Agent 线程表（HITL 线程状态）——对应 sql/V009__create_agent_threads.sql。"""
    __tablename__ = 'agent_threads'
    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id = Column(BigInteger, nullable=False)
    thread_id       = Column(String(64), nullable=False, unique=True)
    status          = Column(String(20), default='ACTIVE')
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (
        Index('idx_conv', 'conversation_id'),
    )


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
