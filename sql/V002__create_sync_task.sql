-- ============================================================
-- V002: 同步任务表 — 支持批量历史回填的断点续传
-- ============================================================

CREATE TABLE sync_task (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    symbol          VARCHAR(20) NOT NULL COMMENT '股票代码',
    start_year      INT NOT NULL COMMENT '回填起始年份',
    end_year        INT NOT NULL COMMENT '回填结束年份',
    current_year    INT NOT NULL DEFAULT 0 COMMENT '当前已处理到的年份（断点续传）',
    status          VARCHAR(20) NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING/RUNNING/SUCCESS/FAILED/PARTIAL',
    records_fetched INT NOT NULL DEFAULT 0 COMMENT '已拉取记录数',
    retry_count     INT NOT NULL DEFAULT 0 COMMENT '重试次数',
    error_msg       TEXT NULL COMMENT '错误信息',
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_st_symbol_year (symbol, start_year, end_year),
    INDEX idx_st_status (status),
    INDEX idx_st_updated (updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='批量回填同步任务表';
