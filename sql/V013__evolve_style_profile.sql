-- ============================================================
-- V013: 改造风格画像为「冷启动问卷 + HITL 反馈自进化」模式
--
-- 设计转变：
-- - 旧方案：每 3 轮对话触发 2 题问卷（用户主动答）
-- - 新方案：冷启动一次性问卷得到基线画像 + 后续 HITL 反馈时
--           LLM 推断器自动调整 6 维度 score（用户无感）
--
-- 变更：
-- 1. DROP 旧 style_quiz_answers 表（不再需要）
-- 2. DROP 旧 style_conversation_counter 表（不再需要对话计数）
-- 3. style_profiles 表添加 stable 字段（基于 evidence_count 自动判定）
-- 4. 新增 feedback_signals 表（HITL 反馈 + LLM 推断结果）
-- ============================================================
use investment_compass;

-- 1. 删除旧问卷相关表
DROP TABLE IF EXISTS style_quiz_answers;
DROP TABLE IF EXISTS style_conversation_counter;

-- 2. style_profiles 表添加 stable 列（之前没有，由 evidence_count 派生）
ALTER TABLE style_profiles
    ADD COLUMN stable TINYINT(1) NOT NULL DEFAULT 0
        COMMENT '画像是否稳定（6 维度中至少 4 个 evidence_count>=1 时为 1）'
        AFTER evidence_count;

-- 3. 新增 feedback_signals 表（HITL 反馈信号 + LLM 推断结果）
CREATE TABLE IF NOT EXISTS feedback_signals (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL DEFAULT 'default',
    thread_id VARCHAR(150) NOT NULL COMMENT 'langgraph 线程ID',
    -- Agent 建议上下文（HITL 中断时 Agent 给出的建议）
    advice_summary TEXT COMMENT 'Agent 建议摘要（如估值分/PE/建议动作）',
    advice_data JSON COMMENT 'Agent 建议完整结构（valuation_score/pe/risk_level/...）',
    -- 用户反馈
    user_action VARCHAR(16) NOT NULL COMMENT 'approve/reject/respond',
    user_response TEXT COMMENT 'respond 文本；approve/reject 时为空',
    -- LLM 推断结果（6 维度 score 调整）
    inferred_scores JSON COMMENT 'LLM 推断的 6 维度 score 调整，如 {"risk_appetite": -0.2, ...}',
    -- 应用状态
    applied TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已应用到 style_profiles 矩阵',
    applied_at DATETIME NULL COMMENT '应用时间',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_time (user_id, created_at),
    INDEX idx_thread (thread_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='HITL 反馈信号与 LLM 推断结果';
