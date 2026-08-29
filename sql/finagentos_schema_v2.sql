-- ============================================================
-- FinAgentOS 金融多Agent智能投资操作系统 — 数据库设计 v2.0
-- 目标数据库：PostgreSQL（生产）/ SQLite（本地开发）
-- 设计原则：
--   1. 仅保留旧系统中与八Agent架构对齐的表
--   2. 新增审计链、决策卡片、因子库、风控熔断模块
--   3. 所有写操作进入审计链（SHA256），不可篡改
--   4. 全文检索、向量检索下沉到专用存储（ChromaDB / ES）
--   5. 行情数据由AkShare直接输出Parquet，不入库
-- ============================================================

-- ============================================================
-- 模块A：用户与工作区（保留改造自旧 auth 模块）
-- 说明：三层账户模型不变，去掉 user_roles 表（合并到 users.role）
-- ============================================================

CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(50) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    role            VARCHAR(20) NOT NULL DEFAULT 'USER',
    is_active       BOOLEAN DEFAULT TRUE,
    password_changed_at TIMESTAMP NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at      TIMESTAMP NULL
);

CREATE TABLE workspaces (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    name            VARCHAR(100) NOT NULL,
    description     VARCHAR(500) DEFAULT '',
    is_default      BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at      TIMESTAMP NULL
);

CREATE TABLE sub_accounts (
    id              SERIAL PRIMARY KEY,
    workspace_id    INTEGER NOT NULL REFERENCES workspaces(id),
    name            VARCHAR(100) NOT NULL,
    initial_capital NUMERIC(15,2) DEFAULT 0.00,
    current_cash    NUMERIC(15,2) DEFAULT 0.00,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at      TIMESTAMP NULL
);

CREATE TABLE refresh_tokens (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    token           VARCHAR(500) NOT NULL,
    expires_at      TIMESTAMP NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 模块B：Agent 注册与配置（改造自 sim_agent）
-- 说明：旧 sim_agent 绑定 personality + skill，新 agents 绑定 agent_type + llm_config
-- 旧表废弃字段：personality_id, type(INTERNAL/EXTERNAL), skill_id, skill_version
-- 新增字段：agent_type(8类), llm_config, trace_prefix
-- ============================================================

CREATE TABLE agents (
    id              SERIAL PRIMARY KEY,
    agent_type      VARCHAR(30) NOT NULL,
    name            VARCHAR(200) NOT NULL,
    workspace_id    INTEGER NOT NULL REFERENCES workspaces(id),
    sub_account_id  INTEGER REFERENCES sub_accounts(id),
    llm_config      JSONB DEFAULT '{}',
    status          VARCHAR(20) DEFAULT 'ACTIVE',
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at      TIMESTAMP NULL
);
CREATE INDEX idx_agents_workspace ON agents(workspace_id);
CREATE INDEX idx_agents_type ON agents(agent_type);

-- ============================================================
-- 模块C：模拟交易（改造自 sim_order / sim_position / sim_nav_snapshot 等）
-- 说明：所有交易表增加 trace_id 和 audit_hash 用于审计追踪
-- 旧表废弃字段：sim_order.slippage, simulated_delay_ms, sim_agent.risk_limits
-- ============================================================

CREATE TABLE orders (
    id              SERIAL PRIMARY KEY,
    agent_id        INTEGER NOT NULL REFERENCES agents(id),
    trace_id        VARCHAR(36) NOT NULL,
    symbol          VARCHAR(20) NOT NULL,
    symbol_name     VARCHAR(50),
    direction       VARCHAR(4) NOT NULL CHECK (direction IN ('BUY','SELL')),
    order_type      VARCHAR(6) NOT NULL DEFAULT 'MARKET',
    price           NUMERIC(10,3),
    quantity        INTEGER NOT NULL,
    status          VARCHAR(10) NOT NULL DEFAULT 'PENDING',
    fill_price      NUMERIC(10,3),
    reject_reason   VARCHAR(200),
    audit_hash      VARCHAR(64),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_orders_agent ON orders(agent_id);
CREATE INDEX idx_orders_trace ON orders(trace_id);
CREATE INDEX idx_orders_status ON orders(status);

CREATE TABLE positions (
    id              SERIAL PRIMARY KEY,
    agent_id        INTEGER NOT NULL REFERENCES agents(id),
    symbol          VARCHAR(20) NOT NULL,
    symbol_name     VARCHAR(50),
    quantity        INTEGER NOT NULL DEFAULT 0,
    avg_cost        NUMERIC(10,3) NOT NULL DEFAULT 0,
    current_price   NUMERIC(10,3),
    market_value    NUMERIC(15,2),
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (agent_id, symbol)
);

CREATE TABLE nav_snapshots (
    id              SERIAL PRIMARY KEY,
    agent_id        INTEGER NOT NULL REFERENCES agents(id),
    snapshot_date   DATE NOT NULL,
    total_asset     NUMERIC(15,2) NOT NULL,
    daily_return    NUMERIC(8,6),
    cumulative_return NUMERIC(8,6),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (agent_id, snapshot_date)
);

CREATE TABLE watchlists (
    id              SERIAL PRIMARY KEY,
    agent_id        INTEGER NOT NULL REFERENCES agents(id),
    symbol          VARCHAR(20) NOT NULL,
    symbol_name     VARCHAR(50) NOT NULL,
    added_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (agent_id, symbol)
);

CREATE TABLE stop_loss_orders (
    id              SERIAL PRIMARY KEY,
    agent_id        INTEGER NOT NULL REFERENCES agents(id),
    trace_id        VARCHAR(36) NOT NULL,
    symbol          VARCHAR(20) NOT NULL,
    symbol_name     VARCHAR(50),
    trigger_price   NUMERIC(10,3) NOT NULL,
    quantity        INTEGER NOT NULL,
    status          VARCHAR(10) NOT NULL DEFAULT 'ACTIVE',
    triggered_at    TIMESTAMP NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_slo_agent ON stop_loss_orders(agent_id, status);

-- ============================================================
-- 模块D：决策卡片（新系统核心输出物）
-- 说明：PA分析Agent的输出，用户确认后转为订单
-- ============================================================

CREATE TABLE decision_cards (
    id                  SERIAL PRIMARY KEY,
    trace_id            VARCHAR(36) NOT NULL,
    agent_id            INTEGER NOT NULL REFERENCES agents(id),
    symbol              VARCHAR(20) NOT NULL,
    stock_name          VARCHAR(50),
    action              VARCHAR(10) NOT NULL,
    confidence          NUMERIC(4,3),
    current_price       NUMERIC(10,2),
    suggested_position  NUMERIC(5,2),
    stop_loss_price     NUMERIC(10,2),
    take_profit_price   NUMERIC(10,2),
    reasoning           TEXT,
    data_sources        JSONB DEFAULT '[]',
    audit_hash          VARCHAR(64),
    status              VARCHAR(10) NOT NULL DEFAULT 'PENDING',
    market_cycle        VARCHAR(50) NOT NULL DEFAULT '',
    sector              VARCHAR(50) NOT NULL DEFAULT '',
    pattern             VARCHAR(100) NOT NULL DEFAULT '',
    review_outcome      JSONB,
    executed_at         TIMESTAMP NULL,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_dc_trace ON decision_cards(trace_id);
CREATE INDEX idx_dc_agent ON decision_cards(agent_id);
CREATE INDEX idx_dc_symbol ON decision_cards(symbol);
CREATE INDEX idx_dc_status ON decision_cards(status);
CREATE INDEX idx_dc_cycle ON decision_cards(market_cycle);
CREATE INDEX idx_dc_sector ON decision_cards(sector);

-- ============================================================
-- 模块E：防篡改审计链（全新）
-- 说明：链式SHA256哈希，每条记录指向前一条的哈希
--       verifyChain(traceId) 遍历验证完整性
-- ============================================================

CREATE TABLE audit_chain (
    id              SERIAL PRIMARY KEY,
    trace_id        VARCHAR(36) NOT NULL,
    agent_type      VARCHAR(30) NOT NULL,
    agent_id        INTEGER REFERENCES agents(id),
    action_type     VARCHAR(50) NOT NULL,
    payload         JSONB NOT NULL,
    previous_hash   VARCHAR(64) NOT NULL,
    current_hash    VARCHAR(64) NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_ac_trace ON audit_chain(trace_id);
CREATE INDEX idx_ac_hash ON audit_chain(current_hash);
CREATE INDEX idx_ac_prev ON audit_chain(previous_hash);

-- 审计链起点标记
INSERT INTO audit_chain (trace_id, agent_type, agent_id, action_type, payload, previous_hash, current_hash)
VALUES ('GENESIS', 'SYSTEM', NULL, 'GENESIS', '{}'::jsonb, '0', 'GENESIS');

-- ============================================================
-- 模块F：风控熔断（全新）
-- 说明：审计/风控Agent的触发记录，亏超5%强制停机
-- ============================================================

CREATE TABLE circuit_breaker_events (
    id              SERIAL PRIMARY KEY,
    trace_id        VARCHAR(36) NOT NULL,
    agent_id        INTEGER NOT NULL REFERENCES agents(id),
    trigger_reason  VARCHAR(100) NOT NULL,
    threshold_value NUMERIC(10,4),
    current_value   NUMERIC(10,4),
    action_taken    VARCHAR(100) NOT NULL,
    resolved_at     TIMESTAMP NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_cbe_agent ON circuit_breaker_events(agent_id);
CREATE INDEX idx_cbe_trace ON circuit_breaker_events(trace_id);

-- ============================================================
-- 模块G：因子库与策略进化（全新）
-- 说明：因子狩猎Agent的输出，IC测试后入库
--       有效策略自动蒸馏为SKILL.md
-- ============================================================

CREATE TABLE factor_library (
    id              SERIAL PRIMARY KEY,
    factor_name     VARCHAR(100) NOT NULL UNIQUE,
    formula         TEXT NOT NULL,
    source          VARCHAR(100),
    category        VARCHAR(50),
    ic_mean         NUMERIC(8,6),
    ic_ir           NUMERIC(8,6),
    oos_ic          NUMERIC(8,6),
    is_active       BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_fl_category ON factor_library(category);
CREATE INDEX idx_fl_active ON factor_library(is_active);

CREATE TABLE factor_ic_records (
    id              SERIAL PRIMARY KEY,
    factor_id       INTEGER NOT NULL REFERENCES factor_library(id),
    test_date       DATE NOT NULL,
    ic_value        NUMERIC(8,6),
    rank_ic         NUMERIC(8,6),
    is_oos          BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_fir_factor ON factor_ic_records(factor_id);
CREATE INDEX idx_fir_date ON factor_ic_records(test_date);

CREATE TABLE skill_exports (
    id              SERIAL PRIMARY KEY,
    skill_id        VARCHAR(100) NOT NULL UNIQUE,
    name            VARCHAR(200) NOT NULL,
    agent_id        INTEGER REFERENCES agents(id),
    version         VARCHAR(20) NOT NULL,
    strategy_type   VARCHAR(50),
    perf_summary    JSONB DEFAULT '{}',
    file_path       VARCHAR(500),
    export_count    INTEGER DEFAULT 0,
    last_exported_at TIMESTAMP NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_se_skill ON skill_exports(skill_id);

-- ============================================================
-- 模块H：决策日志（改造自 agent_decision_log）
-- 说明：每个Agent的每次决策产生一条日志，含置信度和耗时
-- 旧表废弃字段：trigger_symbol, trigger_price, order_id（用trace_id代替）
-- ============================================================

CREATE TABLE decision_logs (
    id              SERIAL PRIMARY KEY,
    trace_id        VARCHAR(36) NOT NULL,
    agent_id        INTEGER NOT NULL REFERENCES agents(id),
    agent_type      VARCHAR(30) NOT NULL,
    input_summary   JSONB DEFAULT '{}',
    output_summary  JSONB DEFAULT '{}',
    confidence      NUMERIC(4,3),
    latency_ms      INTEGER,
    status          VARCHAR(20) DEFAULT 'SUCCESS',
    error_message   TEXT,
    token_cost      INTEGER DEFAULT 0,
    audit_hash      VARCHAR(64),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_dl_trace ON decision_logs(trace_id);
CREATE INDEX idx_dl_agent ON decision_logs(agent_id);
CREATE INDEX idx_dl_type ON decision_logs(agent_type);
CREATE INDEX idx_dl_created ON decision_logs(created_at);

-- ============================================================
-- 模块I：系统监控（保留改造自 system_alert）
-- 说明：增加 data_source_status 跟踪数据源健康
-- ============================================================

CREATE TABLE system_alerts (
    id              SERIAL PRIMARY KEY,
    alert_type      VARCHAR(30) NOT NULL,
    severity        VARCHAR(10) NOT NULL,
    source          VARCHAR(100),
    message         TEXT,
    details         JSONB DEFAULT '{}',
    is_resolved     BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at     TIMESTAMP NULL
);
CREATE INDEX idx_sa_type ON system_alerts(alert_type);
CREATE INDEX idx_sa_severity ON system_alerts(severity);
CREATE INDEX idx_sa_resolved ON system_alerts(is_resolved);

CREATE TABLE data_source_status (
    id              SERIAL PRIMARY KEY,
    source_name     VARCHAR(50) NOT NULL UNIQUE,
    status          VARCHAR(10) NOT NULL DEFAULT 'ONLINE',
    latency_ms      INTEGER DEFAULT 0,
    last_success_at TIMESTAMP NULL,
    last_error_at   TIMESTAMP NULL,
    error_count     INTEGER DEFAULT 0,
    check_count     INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 模块J：任务调度记录（改造自 workflow_runs）
-- 说明：Quartz调度由规划大脑Agent替代，此处只做运行记录
-- 旧表废弃字段：personality_id, feishu_push_status, node_outputs
-- ============================================================

CREATE TABLE task_runs (
    id              SERIAL PRIMARY KEY,
    run_id          VARCHAR(36) NOT NULL UNIQUE,
    task_type       VARCHAR(30) NOT NULL,
    trigger_type    VARCHAR(10) NOT NULL DEFAULT 'SCHEDULED',
    status          VARCHAR(10) NOT NULL DEFAULT 'RUNNING',
    agent_type      VARCHAR(30),
    input_params    JSONB DEFAULT '{}',
    output_summary  JSONB DEFAULT '{}',
    error_message   TEXT,
    audit_hash      VARCHAR(64),
    started_at      TIMESTAMP NULL,
    completed_at    TIMESTAMP NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_tr_type ON task_runs(task_type);
CREATE INDEX idx_tr_status ON task_runs(status);
CREATE INDEX idx_tr_created ON task_runs(created_at);

-- ============================================================
-- 数据迁移对照：旧表 → 新表
-- ============================================================
-- 旧表名                   新表名              处理方式
-- -----------------------  ------------------  ------------------------------
-- users                   users               保留，去掉 user_roles 表
-- workspaces              workspaces          保留
-- sub_accounts            sub_accounts        保留
-- refresh_tokens          refresh_tokens      保留
-- personality             废弃                人格概念替换为 Agent
-- asset_pool              废弃                └─ 改由 agents 管理
-- monitoring_indicator    废弃                 └─ 改由 agents.llm_config
-- risk_parameter          废弃                 └─ 改由 circuit_breaker 模块
-- risk_parameter_review   废弃
-- questionnaire_result    废弃
-- daily_briefing          废弃                输出物改为 decision_cards
-- weekly_briefing         废弃                └─
-- briefing_instructions   废弃
-- briefing_performance    废弃
-- dialogue_session        废弃                LangChain 管理对话状态
-- chat_message            废弃                └─
-- chat_message_archive    废弃
-- compression_metrics     废弃
-- market_data             废弃                AkShare + Parquet 存储
-- stock_metadata          废弃                └─
-- knowledge_card          废弃                ChromaDB 存储
-- sim_agent               → agents           新增 agent_type
-- sim_order               → orders           新增 trace_id + audit_hash
-- sim_position            → positions        保留
-- sim_nav_snapshot        → nav_snapshots    保留
-- sim_watchlist           → watchlists       保留
-- stop_loss_order         → stop_loss_orders 保留
-- agent_decision_log      → decision_logs    改造：用 trace_id 关联
-- workflow_runs           → task_runs        改造：泛化为任务调度
-- ai_usage_log            废弃                合并到 decision_logs
-- system_alert            → system_alerts    保留改造
-- skill_document          废弃                新: skill_exports
-- trade_record            废弃                改由 orders 跟踪
-- review_card             废弃                新系统无复盘模块
-- user_todo               废弃                新系统无待办模块
-- 新增表：
--   decision_cards        — PA分析Agent输出
--   audit_chain           — SHA256审计链
--   circuit_breaker_events— 风控熔断记录
--   factor_library        — 因子库
--   factor_ic_records     — 因子IC测试记录
--   skill_exports         — 策略导出记录
--   data_source_status    — 数据源健康
