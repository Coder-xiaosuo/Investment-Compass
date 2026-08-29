CREATE TABLE IF NOT EXISTS watchlist (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    symbol          VARCHAR(16) NOT NULL COMMENT '股票代码',
    stock_name      VARCHAR(64) DEFAULT '' COMMENT '股票名称',
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_watchlist_symbol (symbol),
    UNIQUE INDEX uk_watchlist_symbol (symbol)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='自选股表';