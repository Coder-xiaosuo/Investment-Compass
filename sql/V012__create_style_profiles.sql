-- ============================================================
-- V012: 投资风格画像表（替代旧 preference_signals 方案）
--
-- 新方案：6 维度雷达图 + 30 风格标签 + 12 道情景问卷题
--
-- 表1: style_profiles       — 用户当前画像矩阵（每用户 6 行，每维度 1 行）
-- 表2: style_quiz_answers   — 问卷作答历史（用于审计/重算）
-- 表3: style_conversation_counter — 对话轮次计数器（每用户 1 行）
-- ============================================================
use investment_compass;

-- 表1: 用户风格画像矩阵（每用户每维度 1 行）
CREATE TABLE IF NOT EXISTS style_profiles (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL DEFAULT 'default',
    dimension VARCHAR(32) NOT NULL COMMENT '维度: risk_appetite/time_horizon/decision_basis/trading_style/concentration/emotion_pref',
    score FLOAT NOT NULL DEFAULT 0 COMMENT '当前得分 [-1.0, +1.0]',
    evidence_count INT NOT NULL DEFAULT 0 COMMENT '累计答题证据数',
    matched_style_id VARCHAR(16) NOT NULL DEFAULT '' COMMENT '匹配的标签ID（如 ra_2）',
    matched_style_label VARCHAR(32) NOT NULL DEFAULT '' COMMENT '匹配的标签名称（如 稳健型）',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_dim (user_id, dimension),
    INDEX idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户投资风格画像矩阵';

-- 表2: 问卷作答历史
CREATE TABLE IF NOT EXISTS style_quiz_answers (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL DEFAULT 'default',
    quiz_id VARCHAR(64) NOT NULL COMMENT '本次问卷会话ID（如 quiz_20260810_1）',
    question_id VARCHAR(16) NOT NULL COMMENT '题库题目ID（如 q01）',
    question_text TEXT COMMENT '题干快照（便于审计）',
    selected_label VARCHAR(8) NOT NULL COMMENT '用户选项 A/B/C',
    selected_text TEXT COMMENT '选项文案快照',
    scores_json JSON COMMENT '本次作答对各维度的得分调整',
    answered_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_quiz (user_id, quiz_id),
    INDEX idx_user_question (user_id, question_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='风格问卷作答历史';

-- 表3: 对话轮次计数器（用于触发问卷）
CREATE TABLE IF NOT EXISTS style_conversation_counter (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL DEFAULT 'default',
    conversation_count INT NOT NULL DEFAULT 0 COMMENT '累计对话轮次',
    quiz_completed_count INT NOT NULL DEFAULT 0 COMMENT '已完成的问卷次数（每次2题）',
    stable TINYINT(1) NOT NULL DEFAULT 0 COMMENT '画像是否稳定（6次问卷后置1，不再主动问卷）',
    last_quiz_at DATETIME NULL COMMENT '上次问卷时间',
    last_conversation_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='对话轮次与问卷进度计数器';
