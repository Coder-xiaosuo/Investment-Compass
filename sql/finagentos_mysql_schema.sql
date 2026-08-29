-- ============================================================
-- FinAgentOS 金融多Agent智能投资操作系统 — 数据库设计 v2.1
-- 目标数据库：MySQL 8.0+（InnoDB + utf8mb4）
-- Changes in v2.1: 新增模块K(行情数据)、修复模块B/C表设计缺陷
-- ============================================================

-- ============================================================
-- 模块A：用户与工作区（保留改造自旧 auth 模块）
-- ============================================================
drop database investment_compass;

create database investment_compass;

use investment_compass;

CREATE TABLE users (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    username        VARCHAR(50) NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    role            VARCHAR(20) NOT NULL DEFAULT 'USER',
    is_active       TINYINT(1) DEFAULT 1,
    password_changed_at DATETIME NULL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at      DATETIME NULL,
    UNIQUE KEY uk_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';

CREATE TABLE workspaces (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id         BIGINT NOT NULL,
    name            VARCHAR(100) NOT NULL,
    description     VARCHAR(500) DEFAULT '',
    is_default      TINYINT(1) DEFAULT 0,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at      DATETIME NULL,
    INDEX idx_ws_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='工作区表';

CREATE TABLE sub_accounts (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    workspace_id    BIGINT NOT NULL,
    name            VARCHAR(100) NOT NULL,
    initial_capital DECIMAL(15,2) DEFAULT 0.00,
    current_cash    DECIMAL(15,2) DEFAULT 0.00,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at      DATETIME NULL,
    INDEX idx_sa_workspace (workspace_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='子账户表';

CREATE TABLE refresh_tokens (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id         BIGINT NOT NULL,
    token           VARCHAR(500) NOT NULL,
    expires_at      DATETIME NOT NULL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_rt_user (user_id),
    INDEX idx_rt_token (token(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='刷新令牌表';

-- ============================================================
-- 模块B：Agent 注册与配置（改造自 sim_agent）
-- agent_type: intent / planner / data_fetcher / pa_analyzer
--             / quant_executor / backtester / audit / factor_hunter
-- asset_type: STOCK / FUTURES / FOREX / CRYPTO
-- ============================================================

CREATE TABLE agents (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    agent_type      VARCHAR(30) NOT NULL COMMENT 'Agent类型：intent/planner/data_fetcher/pa_analyzer/quant_executor/backtester/audit/factor_hunter',
    name            VARCHAR(200) NOT NULL,
    workspace_id    BIGINT NOT NULL,
    sub_account_id  BIGINT NULL,
    llm_config      JSON COMMENT '模型配置：model/temperature/max_tokens',
    status          VARCHAR(20) DEFAULT 'ACTIVE',
    asset_type      VARCHAR(20) NOT NULL DEFAULT 'STOCK' COMMENT '资产类型：STOCK/FUTURES/FOREX/CRYPTO',
    metadata        JSON COMMENT '扩展属性',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at      DATETIME NULL,
    INDEX idx_agents_workspace (workspace_id),
    INDEX idx_agents_type (agent_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Agent注册表';

-- ============================================================
-- 模块C：模拟交易（改造自 sim_order / sim_position 等）
-- ============================================================

CREATE TABLE orders (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    agent_id        BIGINT NOT NULL,
    sub_account_id  BIGINT NULL COMMENT '子账户ID（归属哪个子账户）',
    trace_id        VARCHAR(36) NOT NULL COMMENT '全局TraceID，关联审计链',
    symbol          VARCHAR(20) NOT NULL,
    symbol_name     VARCHAR(50) NULL,
    direction       VARCHAR(4) NOT NULL COMMENT 'BUY/SELL',
    order_type      VARCHAR(6) NOT NULL DEFAULT 'MARKET',
    price           DECIMAL(10,3) NULL,
    quantity        INT NOT NULL COMMENT 'A股 quantity 须为 100 的整数倍（一手），由应用层校验',
    status          VARCHAR(10) NOT NULL DEFAULT 'PENDING',
    fill_price      DECIMAL(10,3) NULL,
    reject_reason   VARCHAR(200) NULL,
    audit_hash      VARCHAR(64) NULL COMMENT 'SHA256审计指纹',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_orders_agent (agent_id),
    INDEX idx_orders_trace (trace_id),
    INDEX idx_orders_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单表';

CREATE TABLE positions (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    agent_id        BIGINT NOT NULL,
    symbol          VARCHAR(20) NOT NULL,
    symbol_name     VARCHAR(50) NULL,
    quantity        INT NOT NULL DEFAULT 0,
    avg_cost        DECIMAL(10,3) NOT NULL DEFAULT 0,
    current_price   DECIMAL(10,3) NULL,
    market_value    DECIMAL(15,2) NULL,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_pos_agent_symbol (agent_id, symbol)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='持仓表';

-- positions_v2 — 持仓表（改造自 positions，v2.1 引入 sub_account_id 和 stop_loss_price）
CREATE TABLE positions_v2 (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    sub_account_id  BIGINT NOT NULL COMMENT '所属子账户',
    agent_id        BIGINT NOT NULL COMMENT '最后一次操作该持仓的Agent',
    symbol          VARCHAR(20) NOT NULL COMMENT '股票代码',
    symbol_name     VARCHAR(50) NULL COMMENT '股票名称',
    quantity        INT NOT NULL DEFAULT 0 COMMENT '持仓数量（A股一手=100股）',
    avg_cost        DECIMAL(10,3) NOT NULL DEFAULT 0 COMMENT '平均成本价',
    current_price   DECIMAL(10,3) NULL COMMENT '当前市价',
    market_value    DECIMAL(15,2) NULL COMMENT '持仓市值',
    stop_loss_price DECIMAL(10,3) NULL COMMENT '止损触发价',
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_pos_subaccount_symbol (sub_account_id, symbol),
    INDEX idx_pos_agent (agent_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='持仓V2表（按子账户 + 品种唯一）';

CREATE TABLE nav_snapshots (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    agent_id        BIGINT NOT NULL,
    snapshot_date   DATE NOT NULL,
    total_asset     DECIMAL(15,2) NOT NULL,
    daily_return    DECIMAL(8,6) NULL,
    cumulative_return DECIMAL(8,6) NULL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_nav_agent_date (agent_id, snapshot_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='净值快照表';

CREATE TABLE watchlists (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    agent_id        BIGINT NOT NULL,
    symbol          VARCHAR(20) NOT NULL,
    symbol_name     VARCHAR(50) NOT NULL,
    added_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_wl_agent_symbol (agent_id, symbol)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='自选股表';

-- watchlists_v2 — 自选股表（改造自 watchlists，v2.1 workspace_id 代替 agent_id）
CREATE TABLE watchlists_v2 (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    workspace_id    BIGINT NOT NULL COMMENT '所属工作区',
    symbol          VARCHAR(20) NOT NULL COMMENT '股票代码',
    symbol_name     VARCHAR(50) NOT NULL COMMENT '股票名称',
    added_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '添加时间',
    UNIQUE KEY uk_wl_workspace_symbol (workspace_id, symbol),
    INDEX idx_wl_workspace (workspace_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='自选股V2表（工作区级别）';

CREATE TABLE stop_loss_orders (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    agent_id        BIGINT NOT NULL,
    trace_id        VARCHAR(36) NOT NULL,
    symbol          VARCHAR(20) NOT NULL,
    symbol_name     VARCHAR(50) NULL,
    trigger_price   DECIMAL(10,3) NOT NULL,
    quantity        INT NOT NULL,
    status          VARCHAR(10) NOT NULL DEFAULT 'ACTIVE',
    triggered_at    DATETIME NULL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_slo_agent (agent_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='止损单表';

-- ============================================================
-- 模块D：决策卡片（新系统核心输出物）
-- ============================================================

CREATE TABLE decision_cards (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    trace_id            VARCHAR(36) NOT NULL COMMENT '全局TraceID',
    agent_id            BIGINT NOT NULL,
    symbol              VARCHAR(20) NOT NULL,
    action              VARCHAR(10) NOT NULL COMMENT 'BUY/SELL/HOLD',
    confidence          DECIMAL(4,3) NULL COMMENT '置信度0-1',
    current_price       DECIMAL(10,2) NULL,
    suggested_position  DECIMAL(5,2) NULL COMMENT '建议仓位%',
    stop_loss_price     DECIMAL(10,2) NULL,
    take_profit_price   DECIMAL(10,2) NULL,
    reasoning           TEXT COMMENT '核心理由',
    data_sources        JSON COMMENT '数据来源列表',
    audit_hash          VARCHAR(64) NULL,
    status              VARCHAR(10) NOT NULL DEFAULT 'PENDING',
    executed_at         DATETIME NULL,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_dc_trace (trace_id),
    INDEX idx_dc_agent (agent_id),
    INDEX idx_dc_symbol (symbol),
    INDEX idx_dc_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='决策卡片表';

-- ============================================================
-- 模块E：防篡改审计链（全新）
-- current_hash = SHA256(previous_hash || payload)
-- ============================================================

CREATE TABLE audit_chain (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    trace_id        VARCHAR(36) NOT NULL,
    agent_type      VARCHAR(30) NOT NULL,
    agent_id        BIGINT NULL,
    action_type     VARCHAR(50) NOT NULL,
    payload         JSON NOT NULL,
    previous_hash   VARCHAR(64) NOT NULL,
    current_hash    VARCHAR(64) NOT NULL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_ac_trace (trace_id),
    INDEX idx_ac_hash (current_hash),
    INDEX idx_ac_prev (previous_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='审计链（SHA256链式哈希）';

-- ============================================================
-- 模块F：风控熔断（全新）
-- ============================================================

CREATE TABLE circuit_breaker_events (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    trace_id        VARCHAR(36) NOT NULL,
    agent_id        BIGINT NOT NULL,
    trigger_reason  VARCHAR(100) NOT NULL COMMENT 'DAILY_LOSS_5PCT / MONTHLY_DRAWDOWN_10PCT / POSITION_CAP_EXCEEDED',
    threshold_value DECIMAL(10,4) NULL,
    current_value   DECIMAL(10,4) NULL,
    action_taken    VARCHAR(100) NOT NULL COMMENT 'FORCE_LIQUIDATE / FREEZE_TRADING / REQUIRE_REVIEW',
    resolved_at     DATETIME NULL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_cbe_agent (agent_id),
    INDEX idx_cbe_trace (trace_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='风控熔断事件表';

-- ============================================================
-- 模块G：因子库与策略进化（全新）
-- ============================================================

CREATE TABLE factor_library (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    factor_name     VARCHAR(100) NOT NULL,
    formula         TEXT NOT NULL COMMENT '因子计算公式',
    source          VARCHAR(100) NULL COMMENT '来源：arXiv论文ID',
    category        VARCHAR(50) NULL COMMENT 'momentum/volatility/value/quality',
    ic_mean         DECIMAL(8,6) NULL COMMENT '样本内平均IC',
    ic_ir           DECIMAL(8,6) NULL COMMENT 'IC-IR',
    oos_ic          DECIMAL(8,6) NULL COMMENT '样本外IC',
    is_active       TINYINT(1) DEFAULT 0,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_factor_name (factor_name),
    INDEX idx_fl_category (category),
    INDEX idx_fl_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='因子库';

CREATE TABLE factor_ic_records (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    factor_id       BIGINT NOT NULL,
    test_date       DATE NOT NULL,
    ic_value        DECIMAL(8,6) NULL,
    rank_ic         DECIMAL(8,6) NULL,
    is_oos          TINYINT(1) DEFAULT 0 COMMENT '样本外标记',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_fir_factor (factor_id),
    INDEX idx_fir_date (test_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='因子IC测试记录表';

CREATE TABLE skill_exports (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    skill_id        VARCHAR(100) NOT NULL,
    name            VARCHAR(200) NOT NULL,
    agent_id        BIGINT NULL,
    version         VARCHAR(20) NOT NULL,
    strategy_type   VARCHAR(50) NULL,
    perf_summary    JSON COMMENT '回测绩效摘要',
    file_path       VARCHAR(500) NULL COMMENT '导出文件路径',
    export_count    INT DEFAULT 0,
    last_exported_at DATETIME NULL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_skill_id (skill_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='策略导出记录表';

-- ============================================================
-- 模块H：决策日志（改造自 agent_decision_log）
-- ============================================================

CREATE TABLE decision_logs (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    trace_id        VARCHAR(36) NOT NULL,
    agent_id        BIGINT NOT NULL,
    agent_type      VARCHAR(30) NOT NULL,
    input_summary   JSON COMMENT '输入摘要',
    output_summary  JSON COMMENT '输出摘要',
    confidence      DECIMAL(4,3) NULL,
    latency_ms      INT NULL COMMENT '处理耗时(ms)',
    status          VARCHAR(20) DEFAULT 'SUCCESS',
    error_message   TEXT NULL,
    token_cost      INT DEFAULT 0,
    audit_hash      VARCHAR(64) NULL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_dl_trace (trace_id),
    INDEX idx_dl_agent (agent_id),
    INDEX idx_dl_type (agent_type),
    INDEX idx_dl_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='决策日志表';

-- ============================================================
-- 模块I：系统监控（保留改造自 system_alert）
-- ============================================================

CREATE TABLE system_alerts (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    alert_type      VARCHAR(30) NOT NULL COMMENT 'DATA_SOURCE / AI_SERVICE / CIRCUIT_BREAKER / SYSTEM',
    severity        VARCHAR(10) NOT NULL COMMENT 'INFO / WARNING / ERROR / CRITICAL',
    source          VARCHAR(100) NULL,
    message         TEXT NULL,
    details         JSON NULL,
    is_resolved     TINYINT(1) DEFAULT 0,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    resolved_at     DATETIME NULL,
    INDEX idx_sa_type (alert_type),
    INDEX idx_sa_severity (severity),
    INDEX idx_sa_resolved (is_resolved)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='系统告警表';

CREATE TABLE data_source_status (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    source_name     VARCHAR(50) NOT NULL,
    status          VARCHAR(10) NOT NULL DEFAULT 'ONLINE' COMMENT 'ONLINE / DEGRADED / OFFLINE',
    latency_ms      INT DEFAULT 0,
    last_success_at DATETIME NULL,
    last_error_at   DATETIME NULL,
    error_count     INT DEFAULT 0,
    check_count     INT DEFAULT 0,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_dss_name (source_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据源健康状态表';

-- ============================================================
-- 模块J：任务调度记录（改造自 workflow_runs）
-- ============================================================

CREATE TABLE task_runs (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id          VARCHAR(36) NOT NULL,
    task_type       VARCHAR(30) NOT NULL COMMENT 'FACTOR_HUNT / BACKTEST / REPORT / CIRCUIT_CHECK',
    trigger_type    VARCHAR(10) NOT NULL DEFAULT 'SCHEDULED',
    status          VARCHAR(10) NOT NULL DEFAULT 'RUNNING',
    agent_type      VARCHAR(30) NULL,
    input_params    JSON NULL,
    output_summary  JSON NULL,
    error_message   TEXT NULL,
    audit_hash      VARCHAR(64) NULL,
    started_at      DATETIME NULL,
    completed_at    DATETIME NULL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_run_id (run_id),
    INDEX idx_tr_type (task_type),
    INDEX idx_tr_status (status),
    INDEX idx_tr_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='任务运行记录表';

-- ============================================================
-- 模块K：行情数据（v2.1 新增）
-- ============================================================

CREATE TABLE stock_metadata (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    symbol          VARCHAR(20) NOT NULL COMMENT '股票代码，含交易所后缀，如 000001.SZ / 600519.SH',
    stock_name      VARCHAR(100) NOT NULL COMMENT '股票名称',
    type            VARCHAR(20) NOT NULL DEFAULT 'STOCK' COMMENT '资产类型：STOCK / ETF / INDEX',
    source          VARCHAR(30) NOT NULL DEFAULT 'akshare' COMMENT '数据来源：akshare / eastmoney / manual',
    is_active       TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用跟踪',
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_sm_symbol (symbol),
    INDEX idx_sm_type (type),
    INDEX idx_sm_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='品种注册表（股票/ETF/指数）';

CREATE TABLE market_data (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    symbol          VARCHAR(20) NOT NULL COMMENT '股票代码，含交易所后缀',
    trade_date      DATE NOT NULL COMMENT '交易日（A股市场日期）',
    timeframe       VARCHAR(10) NOT NULL DEFAULT '1d' COMMENT 'K线周期：1m/5m/15m/30m/1h/4h/1d',
    ts_open         BIGINT NOT NULL COMMENT 'K线开盘Unix毫秒时间戳(UTC)',
    open            DECIMAL(10,3) NOT NULL COMMENT '开盘价',
    high            DECIMAL(10,3) NOT NULL COMMENT '最高价',
    low             DECIMAL(10,3) NOT NULL COMMENT '最低价',
    close           DECIMAL(10,3) NOT NULL COMMENT '收盘价/最新价',
    volume          BIGINT NOT NULL DEFAULT 0 COMMENT '成交量（股）',
    amount          DECIMAL(15,2) NOT NULL DEFAULT 0.00 COMMENT '成交额（元）',
    pct_chg         DECIMAL(8,4) NULL COMMENT '涨跌幅（%），正值上涨，负值下跌',
    closed          TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'K线是否已收盘：1=已收盘，0=正在形成',
    fetched_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_md_symbol_date_tf (symbol, trade_date, timeframe),
    INDEX idx_md_symbol (symbol),
    INDEX idx_md_trade_date (trade_date),
    INDEX idx_md_fetched (fetched_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='K线行情数据表（与KlineBar模型对齐）';
