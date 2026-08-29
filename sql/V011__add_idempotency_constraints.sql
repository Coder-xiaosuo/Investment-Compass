-- ============================================================
-- V011: 幂等性约束
--   · decision_cards.trace_id 唯一 —— 稳定幂等键，同一次决策
--     重复落库 / 报告重放均收敛到同一行
--   · message(conversation_id, sequence) 唯一 —— 同一会话内消息
--     序号唯一，防止重放或并发重复插入
-- ============================================================
use investment_compass;

-- decision_cards：trace_id 作为决策唯一标识（由 TA 子 Agent 一次生成贯穿全程）
ALTER TABLE decision_cards ADD UNIQUE INDEX uq_dc_trace (trace_id);

-- message：同一会话内 sequence 唯一（配合代码侧 INSERT ... ON DUPLICATE KEY UPDATE）
ALTER TABLE message ADD UNIQUE INDEX uq_msg_conv_seq (conversation_id, sequence);
