-- ============================================================
-- V017: agent_threads.status 增加 CANCELLED 取值
-- 说明：
--   客户端断连（abort / 网络中断）导致本轮分析未跑完时，线程标记为
--   CANCELLED，与 HITL 的 INTERRUPTED 语义严格区分：
--     ACTIVE      - 运行中
--     INTERRUPTED - HITL 中断，等待用户决策（可作为 resume 目标）
--     DONE        - 正常完成
--     CANCELLED   - 客户端断连，本轮未完成（不可 resume）
--   仅更新列注释，status 仍为 VARCHAR(20)，无需变更列定义。
-- ============================================================
use investment_compass;

ALTER TABLE agent_threads
    MODIFY COLUMN status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
    COMMENT 'ACTIVE/INTERRUPTED/DONE/CANCELLED';
