-- ============================================================
-- V016: 清理 FinAgentOS 遗留表（21 张）
--
-- 背景：本库由 FinAgentOS 项目的备份迁移而来（见 docker-compose.mysql.yml 的
--       docker-entrypoint-initdb.d 挂载）。FinAgentOS 是「模拟交易平台」，
--       与 Investment-Compass（行情数据分析）是两套不同产品——其 sql/
--       finagentos_schema_v2.sql 明确把 market_data / stock_metadata 标为
--       「废弃，AkShare + Parquet 存储」，而这两张恰是本项目的核心表。
--
-- 这 21 张表在投资罗盘侧完全未使用，取证结论：
--   1. 全部 0 行
--   2. Python 侧仅出现在 shared/models.py 的 ORM 声明，services/ / agents/ /
--      main.py 零引用（无 ORM 实例化，无 SQL 语句）
--   3. Java 侧零引用
--   4. 全库唯一外键为 message -> conversation，与这 21 张无关，删除无依赖顺序问题
--   5. Base.metadata.create_all() 仅在测试脚本中调用，生产启动不会重建
--
-- 保留的 20 张表（均有活跃读写，逐一验证）：
--   market_data / stock_metadata / kline_coverage / sync_task / stock_financial /
--   stock_industry / stock_valuation_daily / stock_news / research_reports /
--   conversation / message / agent_threads / decision_cards / watchlist /
--   style_profiles / feedback_signals / checkpoints / checkpoint_blobs /
--   checkpoint_writes / checkpoint_migrations
--   注：checkpoint* 4 张为 LangGraph MySQL checkpointer（HITL 线程状态），在用。
--
-- 磁盘影响：这 21 张合计约 992 KB，占全库 1.0%，收益主要在运维认知成本
--           （表数 42 -> 21），而非空间。
--
-- 评估与取证详见 docs/data-platform/06-数据库瘦身审计报告.md
-- ============================================================
use investment_compass;

-- 模块A 用户与工作区（4 张）
DROP TABLE IF EXISTS refresh_tokens;
DROP TABLE IF EXISTS sub_accounts;
DROP TABLE IF EXISTS workspaces;
DROP TABLE IF EXISTS users;

-- 模块B Agent 注册（1 张）
DROP TABLE IF EXISTS agents;

-- 模块C 模拟交易（7 张，含 v2.1 引入的 _v2 变体）
DROP TABLE IF EXISTS stop_loss_orders;
DROP TABLE IF EXISTS watchlists_v2;
DROP TABLE IF EXISTS watchlists;
DROP TABLE IF EXISTS nav_snapshots;
DROP TABLE IF EXISTS positions_v2;
DROP TABLE IF EXISTS positions;
DROP TABLE IF EXISTS orders;

-- 模块E/F 审计链与风控熔断（2 张）
DROP TABLE IF EXISTS circuit_breaker_events;
DROP TABLE IF EXISTS audit_chain;

-- 模块G 因子库与策略进化（3 张）
DROP TABLE IF EXISTS skill_exports;
DROP TABLE IF EXISTS factor_ic_records;
DROP TABLE IF EXISTS factor_library;

-- 模块H 决策日志（1 张）
DROP TABLE IF EXISTS decision_logs;

-- 模块I 系统监控（2 张）
DROP TABLE IF EXISTS data_source_status;
DROP TABLE IF EXISTS system_alerts;

-- 模块J 任务调度记录（1 张）
DROP TABLE IF EXISTS task_runs;

-- ============================================================
-- 回滚说明：这 21 张表的结构可由以下两个文件完整恢复（已随本次清理从
-- sql/ 移除以避免误导入，如需恢复请查 git 历史）：
--   sql/finagentos_mysql_schema.sql   （MySQL 版，26 张）
--   sql/finagentos_schema_v2.sql      （PostgreSQL/SQLite 版，20 张）
-- 数据无需恢复——删除时全部为 0 行。
-- ============================================================
