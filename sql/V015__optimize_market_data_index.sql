-- ============================================================
-- V015: market_data 索引优化（列序修正 + 去冗余）
--
-- 背景：所有高频读都落在两个维度上——
--   ① 单标的定向读：symbol + timeframe 等值，按 trade_date 排序
--   ② 跨标的按日读：timeframe + trade_date
-- 而现有唯一键把 trade_date 放在 timeframe 之前，与①的访问模式相反，
-- 执行计划退化为"先扫该标的所有周期行，再逐行过滤 timeframe"。
-- 该成本取决于单标的行数（分钟线进来后激增），不随全表规模摊薄。
--
-- 评估与实测数据见 docs/data-platform/04-索引评估与优化方案.md
--
-- 变更后仅 3 个索引（1 聚簇 + 2 二级）：
--   PRIMARY(id)
--   uk_md_symbol_tf_date (symbol, timeframe, trade_date)  → 服务维度①
--   idx_md_tf_date       (timeframe, trade_date, symbol)  → 服务维度②
--
-- 注意：唯一键必须保持 UNIQUE —— upsert_market_data 的
--       ON DUPLICATE KEY UPDATE 依赖它实现幂等，改普通索引会导致重复写入。
--
-- 回滚见文件末尾。
-- ============================================================
use investment_compass;

-- idx_md_symbol      : 是 uk 的严格前缀列，优化器从不选择，删除
-- idx_md_fetched     : 按 SQL 指纹检索，引用 market_data.fetched_at 的语句数为 0，删除
-- idx_md_trade_date  : 被 (timeframe, trade_date, symbol) 取代
--                      （后者含 symbol 才覆盖 count(distinct symbol)，实测 924ms vs 2086ms）
ALTER TABLE market_data
    DROP INDEX uk_md_symbol_date_tf,
    DROP INDEX idx_md_symbol,
    DROP INDEX idx_md_trade_date,
    DROP INDEX idx_md_fetched,
    ADD UNIQUE KEY uk_md_symbol_tf_date (symbol, timeframe, trade_date),
    ADD INDEX idx_md_tf_date (timeframe, trade_date, symbol);

-- ============================================================
-- 配套代码修正（务必同批部署，否则以下查询会回退）：
--   1. market_data_service.get_latest_market_date  → 补 AND timeframe='1d'
--   2. market_data_service.get_realtime_quote m1   → 补 AND timeframe='1d'
--   3. market_data_service.get_realtime_quote m2   → 补 AND timeframe='1d'
--   4. market_data_service.get_kline_history       → 去 LOWER(timeframe)
--   5. technical_analysis_agent                    → 去 LOWER(timeframe)
-- （原因：列序调整后，"仅按 symbol 定位"不再享有免费排序/MinMax 优化；
--   LOWER() 包装使索引无法用于等值定位，而表 collation 为
--   utf8mb4_0900_ai_ci，timeframe='1d' 本身即匹配 '1D'，去掉语义等价）
-- ============================================================

-- ============================================================
-- 回滚脚本：
-- ALTER TABLE market_data
--     DROP INDEX uk_md_symbol_tf_date,
--     DROP INDEX idx_md_tf_date,
--     ADD UNIQUE KEY uk_md_symbol_date_tf (symbol, trade_date, timeframe),
--     ADD INDEX idx_md_symbol (symbol),
--     ADD INDEX idx_md_trade_date (trade_date),
--     ADD INDEX idx_md_fetched (fetched_at);
-- ============================================================
