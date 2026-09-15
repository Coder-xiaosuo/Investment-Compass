-- ============================================================
-- Investment-Compass — 数据库收敛基线（Schema Baseline）
--
-- 本文件由真实库直接导出（mysqldump --no-data），是**权威快照**，
-- 反映投资罗盘当前实际表结构。若与 sql/ 下迁移脚本不一致，以本文件为准。
--
-- 用途：审计 / 环境重建 / 与迁移链交叉核对。
--
-- 收敛结果：42 张表 -> 21 张
--   移除 21 张 FinAgentOS 模拟交易平台遗留表（见 V016 迁移）。
--   保留 16 张业务表 + 4 张 LangGraph checkpoint 表 + 1 张 data_quality_issue。
--
-- 数据来源：由 FinAgentOS 项目备份迁移而来（docker-compose.mysql.yml 挂载
--          docker-entrypoint-initdb.d 导入），其中携带了大量与投资罗盘无关的
--          trading 平台表，本次一并收敛。
--
-- 已知的脚本-现实偏差（供审计注意，未在本轮修正）：
--   1. watchlist 表实际含 symbol_name 列，但 V003/V006 均未定义该列
--      （由备份 dumps 带入）——说明 sql/ 迁移链已与真实库脱节。
--   2. V006__create_watchlist.sql 与 V003 冲突（同名表、不同结构）。
--      因 V003 先执行且 V006 用 CREATE TABLE IF NOT EXISTS，V006 从未生效，
--      属惰性文件；本文件所记录的结构与 V003 一致（含 symbol_name 扩展）。
--   3. models.py 中 market_data / stock_metadata 的索引声明仍为 V015 之前的
--      旧列序，已于本文件 Header 说明；models.py 现已仅保留确有 ORM 需求的
--      3 个模型，不再声明这两张表。
--
-- 重放说明：本文件仅含 DDL（无数据），可直接用于空库重建。
-- ============================================================

CREATE DATABASE IF NOT EXISTS `investment_compass`
    DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

USE `investment_compass`;




CREATE TABLE `agent_threads` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `conversation_id` bigint NOT NULL COMMENT '关联 conversation.id',
  `thread_id` varchar(64) NOT NULL COMMENT 'langgraph 线程ID',
  `status` varchar(20) NOT NULL DEFAULT 'ACTIVE' COMMENT 'ACTIVE/INTERRUPTED/DONE',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `thread_id` (`thread_id`),
  KEY `idx_conv` (`conversation_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='Agent 线程表（HITL 线程状态）';
CREATE TABLE `checkpoint_blobs` (
  `thread_id` varchar(150) NOT NULL,
  `checkpoint_ns` varchar(2000) NOT NULL DEFAULT '',
  `channel` varchar(150) NOT NULL,
  `version` varchar(150) NOT NULL,
  `type` varchar(150) NOT NULL,
  `blob` longblob,
  `checkpoint_ns_hash` binary(16) NOT NULL,
  PRIMARY KEY (`thread_id`,`checkpoint_ns_hash`,`channel`,`version`),
  KEY `checkpoint_blobs_thread_id_idx` (`thread_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
CREATE TABLE `checkpoint_migrations` (
  `v` int NOT NULL,
  PRIMARY KEY (`v`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
CREATE TABLE `checkpoint_writes` (
  `thread_id` varchar(150) NOT NULL,
  `checkpoint_ns` varchar(2000) NOT NULL DEFAULT '',
  `checkpoint_id` varchar(150) NOT NULL,
  `task_id` varchar(150) NOT NULL,
  `idx` int NOT NULL,
  `channel` varchar(150) NOT NULL,
  `type` varchar(150) DEFAULT NULL,
  `blob` longblob NOT NULL,
  `checkpoint_ns_hash` binary(16) NOT NULL,
  `task_path` varchar(2000) NOT NULL DEFAULT '',
  PRIMARY KEY (`thread_id`,`checkpoint_ns_hash`,`checkpoint_id`,`task_id`,`idx`),
  KEY `checkpoint_writes_thread_id_idx` (`thread_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
CREATE TABLE `checkpoints` (
  `thread_id` varchar(150) NOT NULL,
  `checkpoint_ns` varchar(2000) NOT NULL DEFAULT '',
  `checkpoint_id` varchar(150) NOT NULL,
  `parent_checkpoint_id` varchar(150) DEFAULT NULL,
  `type` varchar(150) DEFAULT NULL,
  `checkpoint` json NOT NULL,
  `metadata` json NOT NULL DEFAULT (_utf8mb4'{}'),
  `checkpoint_ns_hash` binary(16) NOT NULL,
  PRIMARY KEY (`thread_id`,`checkpoint_ns_hash`,`checkpoint_id`),
  KEY `checkpoints_thread_id_idx` (`thread_id`),
  KEY `checkpoints_checkpoint_id_idx` (`checkpoint_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
CREATE TABLE `conversation` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `title` varchar(128) DEFAULT '' COMMENT '会话标题（首条消息摘要或用户自定义）',
  `user_id` bigint DEFAULT NULL COMMENT '用户ID，桌面端单机场景可固定为本地用户',
  `status` tinyint NOT NULL DEFAULT '1' COMMENT '状态：1-活跃 2-归档',
  `kind` varchar(16) NOT NULL DEFAULT 'analysis',
  `summary` text COMMENT '会话摘要（归档后保留，用于归档列表展示）',
  `token_count` int NOT NULL DEFAULT '0' COMMENT '累计Token数（估算）',
  `message_count` int NOT NULL DEFAULT '0' COMMENT '消息数量',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `thread_id` varchar(64) DEFAULT NULL,
  `context_tokens` int NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  KEY `idx_conv_user_status` (`user_id`,`status`),
  KEY `idx_conv_updated_at` (`updated_at` DESC),
  KEY `idx_conv_status_created` (`status`,`created_at` DESC),
  KEY `idx_kind` (`kind`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='对话会话表';
CREATE TABLE `data_quality_issue` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `symbol` varchar(20) NOT NULL COMMENT '股票代码',
  `issue_type` varchar(30) NOT NULL COMMENT '异常类型：GAP_PRICE/GAP_DATE/ZERO_VOLUME/INVERTED_HIGH_LOW/DUPLICATE_DATE/MISSING_SYMBOL',
  `trade_date` date DEFAULT NULL COMMENT '异常发生日期（MISSING_SYMBOL 类型为 NULL）',
  `severity` varchar(10) NOT NULL DEFAULT 'MEDIUM' COMMENT '严重程度：LOW/MEDIUM/HIGH/CRITICAL',
  `description` text NOT NULL COMMENT '异常描述详情',
  `data_before` json DEFAULT NULL COMMENT '异常前的数据快照（用于对比）',
  `data_after` json DEFAULT NULL COMMENT '修复后的数据快照（修复完成后写入）',
  `status` varchar(20) NOT NULL DEFAULT 'OPEN' COMMENT '处理状态：OPEN/PENDING_FIX/FIXED/CONFIRMED',
  `scan_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '检测时间',
  `fix_time` datetime DEFAULT NULL COMMENT '修复时间',
  `fix_by` varchar(50) DEFAULT NULL COMMENT '修复人/方式',
  `retry_count` int NOT NULL DEFAULT '0' COMMENT '修复重试次数',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_dqi_symbol` (`symbol`),
  KEY `idx_dqi_issue_type` (`issue_type`),
  KEY `idx_dqi_status` (`status`),
  KEY `idx_dqi_severity` (`severity`),
  KEY `idx_dqi_trade_date` (`trade_date`),
  KEY `idx_dqi_scan_time` (`scan_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='数据质量问题表';
CREATE TABLE `decision_cards` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `trace_id` varchar(36) NOT NULL COMMENT '全局TraceID',
  `agent_id` bigint NOT NULL,
  `symbol` varchar(20) NOT NULL,
  `stock_name` varchar(50) DEFAULT NULL COMMENT '标的名称',
  `action` varchar(10) NOT NULL COMMENT 'BUY/SELL/HOLD',
  `confidence` decimal(4,3) DEFAULT NULL COMMENT '置信度0-1',
  `current_price` decimal(10,2) DEFAULT NULL,
  `suggested_position` decimal(5,2) DEFAULT NULL COMMENT '建议仓位%',
  `stop_loss_price` decimal(10,2) DEFAULT NULL,
  `take_profit_price` decimal(10,2) DEFAULT NULL,
  `reasoning` text COMMENT '核心理由',
  `data_sources` json DEFAULT NULL COMMENT '数据来源列表',
  `audit_hash` varchar(64) DEFAULT NULL,
  `status` varchar(10) NOT NULL DEFAULT 'PENDING',
  `market_cycle` varchar(50) NOT NULL DEFAULT '' COMMENT '市场周期定位，如 震荡市中后期',
  `sector` varchar(50) NOT NULL DEFAULT '' COMMENT '行业板块，如 白酒',
  `pattern` varchar(100) NOT NULL DEFAULT '' COMMENT '主形态，如 缩量回踩60日均线',
  `review_outcome` json DEFAULT NULL COMMENT '复盘结果 {verdict: HIT/MISS, actual_trend, profit_ratio, review_horizon_days, reviewed_at}',
  `executed_at` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_dc_trace` (`trace_id`),
  KEY `idx_dc_agent` (`agent_id`),
  KEY `idx_dc_symbol` (`symbol`),
  KEY `idx_dc_status` (`status`),
  KEY `idx_dc_cycle` (`market_cycle`),
  KEY `idx_dc_sector` (`sector`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='决策卡片表';
CREATE TABLE `feedback_signals` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'default',
  `thread_id` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'langgraph 线程ID',
  `advice_summary` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT 'Agent 建议摘要（如估值分/PE/建议动作）',
  `advice_data` json DEFAULT NULL COMMENT 'Agent 建议完整结构（valuation_score/pe/risk_level/...）',
  `user_action` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'approve/reject/respond',
  `user_response` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT 'respond 文本；approve/reject 时为空',
  `inferred_scores` json DEFAULT NULL COMMENT 'LLM 推断的 6 维度 score 调整，如 {"risk_appetite": -0.2, ...}',
  `applied` tinyint(1) NOT NULL DEFAULT '0' COMMENT '是否已应用到 style_profiles 矩阵',
  `applied_at` datetime DEFAULT NULL COMMENT '应用时间',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_user_time` (`user_id`,`created_at`),
  KEY `idx_thread` (`thread_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='HITL 反馈信号与 LLM 推断结果';
CREATE TABLE `kline_coverage` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `symbol` varchar(20) NOT NULL COMMENT '股票代码（不含后缀）',
  `timeframe` varchar(10) NOT NULL DEFAULT '1d' COMMENT 'K线周期',
  `expected_from` date NOT NULL COMMENT '意图回溯起点（如 2020-01-01）',
  `expected_to` date NOT NULL COMMENT '本次对账时点',
  `effective_from` date DEFAULT NULL COMMENT '实际要求起点 = max(expected_from, list_date)',
  `expected_days` int NOT NULL DEFAULT '0' COMMENT '日历口径应有交易日数',
  `actual_days` int NOT NULL DEFAULT '0' COMMENT 'market_data 实到行数',
  `missing_days` int NOT NULL DEFAULT '0' COMMENT '缺失交易日数（标量，供排序/队列）',
  `gap_count` int NOT NULL DEFAULT '0' COMMENT '缺口段数',
  `coverage_pct` decimal(5,2) NOT NULL DEFAULT '0.00' COMMENT '覆盖率 %',
  `status` varchar(20) NOT NULL DEFAULT 'PENDING' COMMENT 'COMPLETE/PARTIAL/FAILED/NO_DATA/NOT_LISTED/DELISTED',
  `missing_ranges` json DEFAULT NULL COMMENT '缺口区间 [[from,to],...]，供按段重拉',
  `attempts` int NOT NULL DEFAULT '0' COMMENT '尝试回填次数',
  `last_error` varchar(500) DEFAULT NULL COMMENT '最近一次错误（含限流痕迹）',
  `last_attempt_at` datetime DEFAULT NULL COMMENT '最近一次尝试时间',
  `next_retry_at` datetime DEFAULT NULL COMMENT '下次可重试时间（退避）',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_kc_symbol_tf` (`symbol`,`timeframe`),
  KEY `idx_kc_status` (`status`),
  KEY `idx_kc_retry` (`next_retry_at`),
  KEY `idx_kc_missing` (`missing_days`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='K线完整性台账 — 缺口可查询化';
CREATE TABLE `market_data` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `symbol` varchar(20) NOT NULL COMMENT '股票代码，含交易所后缀',
  `trade_date` date NOT NULL COMMENT '交易日（A股市场日期）',
  `timeframe` varchar(10) NOT NULL DEFAULT '1d' COMMENT 'K线周期：1m/5m/15m/30m/1h/4h/1d',
  `ts_open` bigint NOT NULL COMMENT 'K线开盘Unix毫秒时间戳(UTC)',
  `open` decimal(10,3) NOT NULL COMMENT '开盘价',
  `high` decimal(10,3) NOT NULL COMMENT '最高价',
  `low` decimal(10,3) NOT NULL COMMENT '最低价',
  `close` decimal(10,3) NOT NULL COMMENT '收盘价/最新价',
  `volume` bigint NOT NULL DEFAULT '0' COMMENT '成交量（股）',
  `amount` decimal(15,2) NOT NULL DEFAULT '0.00' COMMENT '成交额（元）',
  `pct_chg` decimal(8,4) DEFAULT NULL COMMENT '涨跌幅（%），正值上涨，负值下跌',
  `closed` tinyint(1) NOT NULL DEFAULT '1' COMMENT 'K线是否已收盘：1=已收盘，0=正在形成',
  `fetched_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_md_symbol_tf_date` (`symbol`,`timeframe`,`trade_date`),
  KEY `idx_md_tf_date` (`timeframe`,`trade_date`,`symbol`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='K线行情数据表（与KlineBar模型对齐）';
CREATE TABLE `message` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `conversation_id` bigint NOT NULL COMMENT '所属会话ID',
  `role` varchar(16) NOT NULL COMMENT '角色：user/assistant/system/tool',
  `content` text COMMENT '消息内容（文本或JSON序列化内容）',
  `content_type` varchar(32) NOT NULL DEFAULT 'text' COMMENT '内容类型：text/kline_card/table_card/chart_card/tool_call/decision_card',
  `card_data` json DEFAULT NULL COMMENT '卡片类型时的结构化数据（与 content_type 配合）',
  `token_count` int NOT NULL DEFAULT '0' COMMENT '本条消息Token数（估算）',
  `sequence` int NOT NULL COMMENT '消息序号（同一会话内从1开始递增）',
  `parent_id` bigint DEFAULT NULL COMMENT '引用父消息ID（工具调用链场景）',
  `tool_name` varchar(64) DEFAULT NULL COMMENT '工具名称（tool角色时）',
  `tool_result` json DEFAULT NULL COMMENT '工具执行结果（tool角色时）',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_msg_conversation_seq` (`conversation_id`,`sequence`),
  KEY `idx_msg_parent` (`parent_id`),
  KEY `idx_msg_created` (`created_at`),
  CONSTRAINT `message_ibfk_1` FOREIGN KEY (`conversation_id`) REFERENCES `conversation` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='会话消息表';
CREATE TABLE `research_reports` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `symbol` varchar(20) NOT NULL,
  `stock_name` varchar(100) DEFAULT NULL,
  `title` varchar(512) NOT NULL,
  `institute` varchar(64) DEFAULT NULL,
  `analyst` varchar(64) DEFAULT NULL,
  `rating` varchar(20) DEFAULT NULL,
  `target_price` decimal(10,3) DEFAULT NULL,
  `eps_2025` decimal(10,4) DEFAULT NULL,
  `eps_2026` decimal(10,4) DEFAULT NULL,
  `eps_2027` decimal(10,4) DEFAULT NULL,
  `eps_2028` decimal(10,4) DEFAULT NULL,
  `pe_2025` decimal(10,3) DEFAULT NULL,
  `pe_2026` decimal(10,3) DEFAULT NULL,
  `pe_2027` decimal(10,3) DEFAULT NULL,
  `publish_date` datetime NOT NULL,
  `pdf_url` varchar(1024) DEFAULT NULL,
  `fetched_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_rr_symbol_ins_date_title` (`symbol`,`institute`,`publish_date`,`title`(190)),
  KEY `idx_rr_rating` (`rating`),
  KEY `idx_rr_symbol_date` (`symbol`,`publish_date`),
  KEY `ix_research_reports_symbol` (`symbol`),
  KEY `ix_research_reports_institute` (`institute`),
  KEY `ix_research_reports_rating` (`rating`),
  KEY `ix_research_reports_publish_date` (`publish_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='券商个股研报';
CREATE TABLE `stock_financial` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `symbol` varchar(20) NOT NULL COMMENT '股票代码（纯6位数字）',
  `report_date` date NOT NULL COMMENT '报告期截止日（如 2026-03-31）',
  `report_type` varchar(4) NOT NULL COMMENT 'Q1/Q2/Q3/Q4',
  `roe` decimal(12,4) DEFAULT NULL,
  `roa` decimal(12,4) DEFAULT NULL,
  `gross_margin` decimal(12,4) DEFAULT NULL,
  `net_margin` decimal(12,4) DEFAULT NULL,
  `operating_margin` decimal(12,4) DEFAULT NULL,
  `revenue` decimal(20,2) DEFAULT NULL COMMENT '营业总收入（元）',
  `net_profit` decimal(20,2) DEFAULT NULL COMMENT '归母净利润（元）',
  `total_assets` decimal(20,2) DEFAULT NULL COMMENT '总资产（元）',
  `total_equity` decimal(20,2) DEFAULT NULL COMMENT '股东权益合计/净资产（元）',
  `cash_flow_op` decimal(20,2) DEFAULT NULL COMMENT '经营现金流量净额（元）',
  `revenue_growth` decimal(12,4) DEFAULT NULL,
  `profit_growth` decimal(12,4) DEFAULT NULL,
  `debt_ratio` decimal(12,4) DEFAULT NULL,
  `current_ratio` decimal(12,4) DEFAULT NULL,
  `quick_ratio` decimal(12,4) DEFAULT NULL,
  `eps` decimal(12,4) DEFAULT NULL,
  `bvps` decimal(12,4) DEFAULT NULL,
  `cfps` decimal(12,4) DEFAULT NULL,
  `cash_ratio` decimal(12,4) DEFAULT NULL,
  `cost_ratio` decimal(12,4) DEFAULT NULL,
  `raw_data` json DEFAULT NULL COMMENT '原始数据备份',
  `source` varchar(30) NOT NULL DEFAULT 'akshare' COMMENT '数据来源',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_sf_symbol_report` (`symbol`,`report_date`),
  KEY `idx_sf_symbol` (`symbol`),
  KEY `idx_sf_report_date` (`report_date`),
  KEY `idx_sf_roe` (`roe`),
  KEY `idx_sf_net_margin` (`net_margin`),
  KEY `idx_sf_revenue_growth` (`revenue_growth`),
  KEY `idx_sf_debt_ratio` (`debt_ratio`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='财务指标表（按报告期，核心指标列化）';
CREATE TABLE `stock_industry` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `symbol` varchar(20) NOT NULL COMMENT '股票代码（纯6位数字）',
  `stock_name` varchar(100) NOT NULL COMMENT '股票名称',
  `industry_l1` varchar(50) NOT NULL COMMENT '申万一级行业',
  `industry_l2` varchar(50) DEFAULT NULL COMMENT '申万二级行业',
  `industry_l3` varchar(50) DEFAULT NULL COMMENT '申万三级行业',
  `source` varchar(30) NOT NULL DEFAULT 'akshare' COMMENT '数据来源',
  `effective_date` date NOT NULL COMMENT '生效日期',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_si_symbol_date` (`symbol`,`effective_date`),
  KEY `idx_si_industry_l1` (`industry_l1`),
  KEY `idx_si_industry_l2` (`industry_l2`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='行业分类表（申万）';
CREATE TABLE `stock_metadata` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `symbol` varchar(20) NOT NULL COMMENT '股票代码，含交易所后缀，如 000001.SZ / 600519.SH',
  `stock_name` varchar(100) NOT NULL COMMENT '股票名称',
  `type` varchar(20) NOT NULL DEFAULT 'STOCK' COMMENT '资产类型：STOCK / ETF / INDEX',
  `source` varchar(30) NOT NULL DEFAULT 'akshare' COMMENT '数据来源：akshare / eastmoney / manual',
  `is_active` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否启用跟踪',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `list_date` date DEFAULT NULL COMMENT '上市日期（审计基准，来自交易所列表）',
  `delist_date` date DEFAULT NULL COMMENT '退市日期，正常退市后不再要求数据',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_sm_symbol` (`symbol`),
  KEY `idx_sm_type` (`type`),
  KEY `idx_sm_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='品种注册表（股票/ETF/指数）';
CREATE TABLE `stock_news` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `source` varchar(20) NOT NULL,
  `symbol` varchar(20) DEFAULT NULL,
  `title` varchar(512) NOT NULL,
  `content` text,
  `publish_time` datetime NOT NULL,
  `url` varchar(1024) DEFAULT NULL,
  `source_name` varchar(64) DEFAULT NULL,
  `fetched_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_news_source_time_title` (`source`,`publish_time`,`title`(190)),
  KEY `idx_news_symbol_time` (`symbol`,`publish_time`),
  KEY `ix_stock_news_source` (`source`),
  KEY `ix_stock_news_symbol` (`symbol`),
  KEY `ix_stock_news_publish_time` (`publish_time`),
  KEY `ix_stock_news_fetched_at` (`fetched_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='财经新闻/快讯';
CREATE TABLE `stock_valuation_daily` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `symbol` varchar(20) NOT NULL COMMENT '股票代码（纯6位数字）',
  `trade_date` date NOT NULL COMMENT '交易日',
  `close_price` decimal(10,3) DEFAULT NULL COMMENT '收盘价',
  `pe_ttm` decimal(10,4) DEFAULT NULL COMMENT '市盈率(TTM)',
  `pe_static` decimal(10,4) DEFAULT NULL COMMENT '市盈率(静态)',
  `pb` decimal(10,4) DEFAULT NULL COMMENT '市净率',
  `ps_ttm` decimal(10,4) DEFAULT NULL COMMENT '市销率(TTM)',
  `market_cap` decimal(20,2) DEFAULT NULL COMMENT '总市值（元）',
  `float_market_cap` decimal(20,2) DEFAULT NULL COMMENT '流通市值（元）',
  `turnover_rate` decimal(8,4) DEFAULT NULL COMMENT '换手率(%)',
  `volume_ratio` decimal(8,4) DEFAULT NULL COMMENT '量比',
  `source` varchar(30) NOT NULL DEFAULT 'akshare' COMMENT '数据来源',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_svd_symbol_date` (`symbol`,`trade_date`),
  KEY `idx_svd_trade_date` (`trade_date`),
  KEY `idx_svd_pe` (`pe_ttm`),
  KEY `idx_svd_pb` (`pb`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='每日估值快照表（PE/PB/市值）';
CREATE TABLE `style_profiles` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'default',
  `dimension` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '维度: risk_appetite/time_horizon/decision_basis/trading_style/concentration/emotion_pref',
  `score` float NOT NULL DEFAULT '0' COMMENT '当前得分 [-1.0, +1.0]',
  `evidence_count` int NOT NULL DEFAULT '0' COMMENT '累计答题证据数',
  `stable` tinyint(1) NOT NULL DEFAULT '0' COMMENT '画像是否稳定（6 维度中至少 4 个 evidence_count>=1 时为 1）',
  `matched_style_id` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '匹配的标签ID（如 ra_2）',
  `matched_style_label` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '匹配的标签名称（如 稳健型）',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_user_dim` (`user_id`,`dimension`),
  KEY `idx_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户投资风格画像矩阵';
CREATE TABLE `sync_task` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `symbol` varchar(20) NOT NULL COMMENT '股票代码',
  `start_year` int NOT NULL COMMENT '回填起始年份',
  `end_year` int NOT NULL COMMENT '回填结束年份',
  `current_year` int NOT NULL DEFAULT '0' COMMENT '当前已处理到的年份（断点续传）',
  `status` varchar(20) NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING/RUNNING/SUCCESS/FAILED/PARTIAL',
  `records_fetched` int NOT NULL DEFAULT '0' COMMENT '已拉取记录数',
  `retry_count` int NOT NULL DEFAULT '0' COMMENT '重试次数',
  `error_msg` text COMMENT '错误信息',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_st_symbol_year` (`symbol`,`start_year`,`end_year`),
  KEY `idx_st_status` (`status`),
  KEY `idx_st_updated` (`updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='批量回填同步任务表';
CREATE TABLE `watchlist` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `symbol` varchar(20) NOT NULL COMMENT '股票代码',
  `symbol_name` varchar(50) NOT NULL DEFAULT '' COMMENT '股票名称',
  `group_name` varchar(50) NOT NULL DEFAULT '默认' COMMENT '分组名称',
  `sort_order` int NOT NULL DEFAULT '0' COMMENT '排序',
  `note` varchar(200) DEFAULT '' COMMENT '备注',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_watch_symbol_group` (`symbol`,`group_name`),
  KEY `idx_watch_group` (`group_name`),
  KEY `idx_watch_sort` (`sort_order`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='自选股表';


