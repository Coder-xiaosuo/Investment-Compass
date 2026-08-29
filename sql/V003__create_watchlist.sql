-- ============================================================
-- V003: 自选股表 — 用户关注股票的分组管理
-- ============================================================
use investment_compass;

CREATE TABLE IF NOT EXISTS watchlist (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    symbol      VARCHAR(20) NOT NULL COMMENT '股票代码',
    group_name  VARCHAR(50) NOT NULL DEFAULT '默认' COMMENT '分组名称',
    sort_order  INT NOT NULL DEFAULT 0 COMMENT '排序',
    note        VARCHAR(200) DEFAULT '' COMMENT '备注',
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_watch_symbol_group (symbol, group_name),
    INDEX idx_watch_group (group_name),
    INDEX idx_watch_sort (sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='自选股表';
