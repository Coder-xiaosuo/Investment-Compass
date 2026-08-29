-- ============================================================
-- V010: 资讯数据表 — 财经新闻/快讯 + 券商研报
-- 数据来源：AkShare（东方财富 / 财联社）
-- ============================================================
use investment_compass;

-- ============================================================
-- 1. 财经新闻/快讯表
-- 来源：
--   em_news        个股新闻（东方财富 stock_news_em）
--   cls_telegraph  财联社 7x24 电报（stock_info_global_cls）
--   em_global      东方财富全球财经资讯（stock_info_global_em）
-- 幂等键：(source, publish_time, title)
-- ============================================================
CREATE TABLE IF NOT EXISTS stock_news (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    source          VARCHAR(20) NOT NULL COMMENT '来源标识: em_news / cls_telegraph / em_global',
    symbol          VARCHAR(20) NULL COMMENT '关联股票代码（NULL=全市场资讯）',
    title           VARCHAR(512) NOT NULL COMMENT '标题',
    content         TEXT NULL COMMENT '正文/摘要',
    publish_time    DATETIME NOT NULL COMMENT '发布时间',
    url             VARCHAR(1024) NULL COMMENT '原文链接',
    source_name     VARCHAR(64) NULL COMMENT '文章来源（证券时报网/财联社等）',
    fetched_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '抓取时间',
    UNIQUE KEY uq_news_source_time_title (source, publish_time, title),
    INDEX idx_news_source (source),
    INDEX idx_news_symbol (symbol),
    INDEX idx_news_publish_time (publish_time),
    INDEX idx_news_symbol_time (symbol, publish_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='财经新闻/快讯';

-- ============================================================
-- 2. 券商个股研报表
-- 来源：东方财富 stock_research_report_em
-- 幂等键：(symbol, institute, publish_date, title)
-- ============================================================
CREATE TABLE IF NOT EXISTS research_reports (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    symbol          VARCHAR(20) NOT NULL COMMENT '股票代码（6位数字）',
    stock_name      VARCHAR(100) NULL COMMENT '股票简称',
    title           VARCHAR(512) NOT NULL COMMENT '研报标题',
    institute       VARCHAR(64) NULL COMMENT '机构：中信证券/国泰君安等',
    analyst         VARCHAR(64) NULL COMMENT '分析师',
    rating          VARCHAR(20) NULL COMMENT '评级：买入/增持/中性/减持/卖出',
    target_price    DECIMAL(10,3) NULL COMMENT '目标价',
    eps_2025        DECIMAL(10,4) NULL COMMENT '2025预测EPS',
    eps_2026        DECIMAL(10,4) NULL COMMENT '2026预测EPS',
    eps_2027        DECIMAL(10,4) NULL COMMENT '2027预测EPS',
    eps_2028        DECIMAL(10,4) NULL COMMENT '2028预测EPS',
    pe_2025         DECIMAL(10,3) NULL COMMENT '2025预测PE',
    pe_2026         DECIMAL(10,3) NULL COMMENT '2026预测PE',
    pe_2027         DECIMAL(10,3) NULL COMMENT '2027预测PE',
    publish_date    DATETIME NOT NULL COMMENT '发布日期',
    pdf_url         VARCHAR(1024) NULL COMMENT '研报PDF链接',
    fetched_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '抓取时间',
    UNIQUE KEY uq_rr_symbol_ins_date_title (symbol, institute, publish_date, title),
    INDEX idx_rr_symbol (symbol),
    INDEX idx_rr_institute (institute),
    INDEX idx_rr_rating (rating),
    INDEX idx_rr_publish_date (publish_date),
    INDEX idx_rr_symbol_date (symbol, publish_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='券商个股研报';
