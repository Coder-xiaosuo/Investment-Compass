-- ============================================================
-- V004: 数据质量问题表 — 持久化数据异常检测结果，支持后续修复与追踪
-- ============================================================
use investment_compass;

CREATE TABLE data_quality_issue (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    symbol          VARCHAR(20) NOT NULL COMMENT '股票代码',
    issue_type      VARCHAR(30) NOT NULL COMMENT '异常类型：GAP_PRICE/GAP_DATE/ZERO_VOLUME/INVERTED_HIGH_LOW/DUPLICATE_DATE/MISSING_SYMBOL',
    trade_date      DATE NULL COMMENT '异常发生日期（MISSING_SYMBOL 类型为 NULL）',
    severity        VARCHAR(10) NOT NULL DEFAULT 'MEDIUM' COMMENT '严重程度：LOW/MEDIUM/HIGH/CRITICAL',
    description     TEXT NOT NULL COMMENT '异常描述详情',
    data_before     JSON NULL COMMENT '异常前的数据快照（用于对比）',
    data_after      JSON NULL COMMENT '修复后的数据快照（修复完成后写入）',
    status          VARCHAR(20) NOT NULL DEFAULT 'OPEN' COMMENT '处理状态：OPEN/PENDING_FIX/FIXED/CONFIRMED',
    scan_time       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '检测时间',
    fix_time        DATETIME NULL COMMENT '修复时间',
    fix_by          VARCHAR(50) NULL COMMENT '修复人/方式',
    retry_count     INT NOT NULL DEFAULT 0 COMMENT '修复重试次数',
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_dqi_symbol (symbol),
    INDEX idx_dqi_issue_type (issue_type),
    INDEX idx_dqi_status (status),
    INDEX idx_dqi_severity (severity),
    INDEX idx_dqi_trade_date (trade_date),
    INDEX idx_dqi_scan_time (scan_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据质量问题表';
