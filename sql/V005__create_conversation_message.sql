-- ============================================================
-- V005: 对话与会话消息表 — 支撑分析模式下的对话管理与消息持久化
-- ============================================================
use investment_compass;

-- ------------------------------------------------------------
-- 会话表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS conversation (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    title           VARCHAR(128) DEFAULT '' COMMENT '会话标题（首条消息摘要或用户自定义）',
    user_id         BIGINT NULL COMMENT '用户ID，桌面端单机场景可固定为本地用户',
    status          TINYINT NOT NULL DEFAULT 1 COMMENT '状态：1-活跃 2-归档',
    summary         TEXT COMMENT '会话摘要（归档后保留，用于归档列表展示）',
    token_count     INT NOT NULL DEFAULT 0 COMMENT '累计Token数（估算）',
    message_count   INT NOT NULL DEFAULT 0 COMMENT '消息数量',
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_conv_user_status (user_id, status),
    INDEX idx_conv_updated_at (updated_at DESC),
    INDEX idx_conv_status_created (status, created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='对话会话表';

-- ------------------------------------------------------------
-- 消息表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS message (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    conversation_id     BIGINT NOT NULL COMMENT '所属会话ID',
    role                VARCHAR(16) NOT NULL COMMENT '角色：user/assistant/system/tool',
    content             TEXT COMMENT '消息内容（文本或JSON序列化内容）',
    content_type        VARCHAR(32) NOT NULL DEFAULT 'text' COMMENT '内容类型：text/kline_card/table_card/chart_card/tool_call/decision_card',
    card_data           JSON COMMENT '卡片类型时的结构化数据（与 content_type 配合）',
    token_count         INT NOT NULL DEFAULT 0 COMMENT '本条消息Token数（估算）',
    sequence            INT NOT NULL COMMENT '消息序号（同一会话内从1开始递增）',
    parent_id           BIGINT NULL COMMENT '引用父消息ID（工具调用链场景）',
    tool_name           VARCHAR(64) NULL COMMENT '工具名称（tool角色时）',
    tool_result         JSON NULL COMMENT '工具执行结果（tool角色时）',
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_msg_conversation_seq (conversation_id, sequence),
    INDEX idx_msg_parent (parent_id),
    INDEX idx_msg_created (created_at),
    FOREIGN KEY (conversation_id) REFERENCES conversation(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='会话消息表';
