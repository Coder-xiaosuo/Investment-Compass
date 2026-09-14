-- ============================================================
-- V014: K线数据完整性审计基础层（L1 日历 / L2 上市退市 / L3 覆盖台账）
--
-- 背景：market_data 存在系统性空洞（限流导致漏拉却被判成功），
--       且缺少判断"应该有多少根"的基准，无法审计。
--
-- L1 交易日历  → 落在 data/trading_calendar.json（静态参考数据，随仓库 pin 住），不建表
-- L2 上市/退市日期 → stock_metadata 补两列（区分"未上市"与"漏拉"）
-- L3 覆盖台账  → 新建 kline_coverage（把缺口变成可查询的工作队列）
-- ============================================================
use investment_compass;

-- ── L2: 上市/退市日期（审计基准，来自交易所列表批量接口）──────────────
ALTER TABLE stock_metadata
    ADD COLUMN list_date   DATE NULL COMMENT '上市日期（审计基准，来自交易所列表）',
    ADD COLUMN delist_date DATE NULL COMMENT '退市日期，正常退市后不再要求数据';

-- ── L3: K线完整性台账（1 行/标的/周期）────────────────────────────────
CREATE TABLE IF NOT EXISTS kline_coverage (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    symbol          VARCHAR(20) NOT NULL COMMENT '股票代码（不含后缀）',
    timeframe       VARCHAR(10) NOT NULL DEFAULT '1d' COMMENT 'K线周期',

    expected_from   DATE NOT NULL COMMENT '意图回溯起点（如 2020-01-01）',
    expected_to     DATE NOT NULL COMMENT '本次对账时点',
    effective_from  DATE NULL COMMENT '实际要求起点 = max(expected_from, list_date)',

    expected_days   INT NOT NULL DEFAULT 0 COMMENT '日历口径应有交易日数',
    actual_days     INT NOT NULL DEFAULT 0 COMMENT 'market_data 实到行数',
    missing_days    INT NOT NULL DEFAULT 0 COMMENT '缺失交易日数（标量，供排序/队列）',
    gap_count       INT NOT NULL DEFAULT 0 COMMENT '缺口段数',
    coverage_pct    DECIMAL(5,2) NOT NULL DEFAULT 0 COMMENT '覆盖率 %',

    status          VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        COMMENT 'COMPLETE/PARTIAL/FAILED/NO_DATA/NOT_LISTED/DELISTED',
    missing_ranges  JSON NULL COMMENT '缺口区间 [[from,to],...]，供按段重拉',

    attempts        INT NOT NULL DEFAULT 0 COMMENT '尝试回填次数',
    last_error      VARCHAR(500) NULL COMMENT '最近一次错误（含限流痕迹）',
    last_attempt_at DATETIME NULL COMMENT '最近一次尝试时间',
    next_retry_at   DATETIME NULL COMMENT '下次可重试时间（退避）',

    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uk_kc_symbol_tf (symbol, timeframe),
    INDEX idx_kc_status (status),
    INDEX idx_kc_retry (next_retry_at),
    INDEX idx_kc_missing (missing_days)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='K线完整性台账 — 缺口可查询化';
