-- ============================================================
-- V007: 基本面数据表 — 支撑价值投资评分 + 行业分类
-- ============================================================
use investment_compass;

-- ============================================================
-- 1. 行业分类表
-- 来源：申万一级/二级行业分类（通过 akshare 或东方财富获取）
-- 说明：股票与行业的关系可能随时间变化，用 effective_date 跟踪
-- ============================================================
CREATE TABLE IF NOT EXISTS stock_industry (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    symbol          VARCHAR(20) NOT NULL COMMENT '股票代码（纯6位数字）',
    stock_name      VARCHAR(100) NOT NULL COMMENT '股票名称',
    industry_l1     VARCHAR(50) NOT NULL COMMENT '申万一级行业',
    industry_l2     VARCHAR(50) NULL COMMENT '申万二级行业',
    industry_l3     VARCHAR(50) NULL COMMENT '申万三级行业',
    source          VARCHAR(30) NOT NULL DEFAULT 'akshare' COMMENT '数据来源',
    effective_date  DATE NOT NULL COMMENT '生效日期',
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_si_symbol_date (symbol, effective_date),
    INDEX idx_si_industry_l1 (industry_l1),
    INDEX idx_si_industry_l2 (industry_l2)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业分类表（申万）';

-- ============================================================
-- 2. 财务指标表
-- 来源：akshare stock_financial_abstract（利润表+盈利能力+成长能力等）
-- 说明：按报告期存储，每只股票每个报告期一条记录
--      report_type: Q1(一季报) / Q2(中报) / Q3(三季报) / Q4(年报)
-- ============================================================
CREATE TABLE IF NOT EXISTS stock_financial (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    symbol              VARCHAR(20) NOT NULL COMMENT '股票代码（纯6位数字）',
    report_date         DATE NOT NULL COMMENT '报告期截止日（如 2026-03-31）',
    report_type         VARCHAR(4) NOT NULL COMMENT 'Q1/Q2/Q3/Q4',

    -- -- 盈利能力 -- --
    roe                 DECIMAL(8,4) NULL COMMENT '净资产收益率(%)',
    roa                 DECIMAL(8,4) NULL COMMENT '总资产报酬率(%)',
    gross_margin        DECIMAL(8,4) NULL COMMENT '毛利率(%)',
    net_margin          DECIMAL(8,4) NULL COMMENT '销售净利率(%)',
    operating_margin    DECIMAL(8,4) NULL COMMENT '营业利润率(%)',

    -- -- 规模数据 -- --
    revenue             DECIMAL(20,2) NULL COMMENT '营业总收入（元）',
    net_profit          DECIMAL(20,2) NULL COMMENT '归母净利润（元）',
    total_assets        DECIMAL(20,2) NULL COMMENT '总资产（元）',
    total_equity        DECIMAL(20,2) NULL COMMENT '股东权益合计/净资产（元）',
    cash_flow_op        DECIMAL(20,2) NULL COMMENT '经营现金流量净额（元）',

    -- -- 成长能力 -- --
    revenue_growth      DECIMAL(8,4) NULL COMMENT '营业总收入增长率(%)（同比）',
    profit_growth       DECIMAL(8,4) NULL COMMENT '归母净利润增长率(%)（同比）',

    -- -- 财务健康 -- --
    debt_ratio          DECIMAL(8,4) NULL COMMENT '资产负债率(%)',
    current_ratio       DECIMAL(8,4) NULL COMMENT '流动比率',
    quick_ratio         DECIMAL(8,4) NULL COMMENT '速动比率',

    -- -- 每股指标 -- --
    eps                 DECIMAL(10,4) NULL COMMENT '基本每股收益（元）',
    bvps                DECIMAL(10,4) NULL COMMENT '每股净资产（元）',
    cfps                DECIMAL(10,4) NULL COMMENT '每股经营现金流（元）',

    -- -- 收益质量 -- --
    cash_ratio          DECIMAL(8,4) NULL COMMENT '经营现金流/归母净利润',
    cost_ratio          DECIMAL(8,4) NULL COMMENT '期间费用率(%)',

    -- -- 原始数据备份（JSON，保留 akfinance 返回的所有原始指标） -- --
    raw_data            JSON NULL COMMENT '原始数据备份',

    source              VARCHAR(30) NOT NULL DEFAULT 'akshare' COMMENT '数据来源',
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uk_sf_symbol_report (symbol, report_date),
    INDEX idx_sf_symbol (symbol),
    INDEX idx_sf_report_date (report_date),
    INDEX idx_sf_roe (roe),
    INDEX idx_sf_net_margin (net_margin),
    INDEX idx_sf_revenue_growth (revenue_growth),
    INDEX idx_sf_debt_ratio (debt_ratio)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='财务指标表（按报告期，核心指标列化）';

-- ============================================================
-- 3. 每日估值快照表
-- 来源：akshare stock_zh_a_spot_em（东方财富实时行情）
-- 说明：每日闭市后获取，用于 PE/PB/换手率等估值指标
-- ============================================================
CREATE TABLE IF NOT EXISTS stock_valuation_daily (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    symbol              VARCHAR(20) NOT NULL COMMENT '股票代码（纯6位数字）',
    trade_date          DATE NOT NULL COMMENT '交易日',
    close_price         DECIMAL(10,3) NULL COMMENT '收盘价',
    pe_ttm              DECIMAL(10,4) NULL COMMENT '市盈率(TTM)',
    pe_static           DECIMAL(10,4) NULL COMMENT '市盈率(静态)',
    pb                  DECIMAL(10,4) NULL COMMENT '市净率',
    ps_ttm              DECIMAL(10,4) NULL COMMENT '市销率(TTM)',
    market_cap          DECIMAL(20,2) NULL COMMENT '总市值（元）',
    float_market_cap    DECIMAL(20,2) NULL COMMENT '流通市值（元）',
    turnover_rate       DECIMAL(8,4) NULL COMMENT '换手率(%)',
    volume_ratio        DECIMAL(8,4) NULL COMMENT '量比',

    source              VARCHAR(30) NOT NULL DEFAULT 'akshare' COMMENT '数据来源',
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uk_svd_symbol_date (symbol, trade_date),
    INDEX idx_svd_trade_date (trade_date),
    INDEX idx_svd_pe (pe_ttm),
    INDEX idx_svd_pb (pb)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='每日估值快照表（PE/PB/市值）';
