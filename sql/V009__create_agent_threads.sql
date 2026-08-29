-- ============================================================
-- V009: Agent 线程表 — HITL（人工干预）线程状态管理
-- 说明：
--   1) agent_threads 关联 conversation.id，记录 langgraph 线程 ID
--      （thread_id）与线程状态，供 HITL 中断/恢复时定位线程
--   2) status: ACTIVE-运行中 / INTERRUPTED-中断等待用户决策 / DONE-完成
-- ============================================================
use investment_compass;

CREATE TABLE IF NOT EXISTS agent_threads (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    conversation_id BIGINT NOT NULL COMMENT '关联 conversation.id',
    thread_id VARCHAR(64) NOT NULL UNIQUE COMMENT 'langgraph 线程ID',
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' COMMENT 'ACTIVE/INTERRUPTED/DONE',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_conv (conversation_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Agent 线程表（HITL 线程状态）';
