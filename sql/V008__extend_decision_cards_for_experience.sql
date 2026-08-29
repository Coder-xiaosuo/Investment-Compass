-- ============================================================
-- V008: 决策卡片表扩展 — 经验检索标签 + 复盘结果 + 废弃旧经验表
-- 说明：
--   1) decision_cards 作为"全量决策事实层"（投资分析 merge_node 落库点）
--      新增 market_cycle/sector/pattern 供复盘提升器组装 ExperienceEntry
--      新增 review_outcome 存储复盘结果（复盘引擎回填）
--   2) 废弃 experience_entries（老 MySQLFTS 备选后端设计，从未启用）
-- ============================================================
use investment_compass;

-- ------------------------------------------------------------
-- 1. 扩展 decision_cards（空表，增量加列）
-- ------------------------------------------------------------
ALTER TABLE decision_cards
    ADD COLUMN stock_name     VARCHAR(50)  NULL COMMENT '标的名称' AFTER symbol,
    ADD COLUMN market_cycle   VARCHAR(50)  NOT NULL DEFAULT '' COMMENT '市场周期定位，如 震荡市中后期' AFTER status,
    ADD COLUMN sector         VARCHAR(50)  NOT NULL DEFAULT '' COMMENT '行业板块，如 白酒' AFTER market_cycle,
    ADD COLUMN pattern        VARCHAR(100) NOT NULL DEFAULT '' COMMENT '主形态，如 缩量回踩60日均线' AFTER sector,
    ADD COLUMN review_outcome JSON         NULL COMMENT '复盘结果 {verdict: HIT/MISS, actual_trend, profit_ratio, review_horizon_days, reviewed_at}' AFTER pattern,
    ADD INDEX idx_dc_cycle (market_cycle),
    ADD INDEX idx_dc_sector (sector);

-- ------------------------------------------------------------
-- 2. 废弃旧经验表（老 MySQLFTS 备选后端，从未启用；存在则删除）
-- ------------------------------------------------------------
DROP TABLE IF EXISTS experience_entries;
