"""Style Profiler v2.0 演示脚本

模拟真实场景：
1. 冷启动：12 题问卷初始化画像
2. HITL 反馈自进化：6 轮 Agent 建议 → 用户反馈 → LLM 推断 → 画像演化
3. 输出最终六边形雷达图

无 LLM 时也能跑：infer_feedback_scores 失败返回全 0，画像保持冷启动基线。
"""
import sys
from pathlib import Path

# 添加项目根目录到 path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.style_profiler import (
    cold_start_init,
    observe_feedback,
    get_radar_profile,
    render_ascii_radar,
)


USER_ID = "zhang_v3"
THREAD_ID = "demo-thread-v3"


# ── 1. 冷启动问卷：12 题作答（中性平衡型，便于观察后续演化）──────────────
COLD_START_ANSWERS = [
    {"question_id": "q01", "selected_label": "C"},  # 持仓跌 20% → 持有不动（中性）
    {"question_id": "q02", "selected_label": "C"},  # 选股偏好 → 成长与估值平衡
    {"question_id": "q03", "selected_label": "B"},  # 持仓周期 → 中线 1-3 个月
    {"question_id": "q04", "selected_label": "B"},  # 看盘频率 → 每日看盘
    {"question_id": "q05", "selected_label": "B"},  # 止损纪律 → 灵活止损
    {"question_id": "q06", "selected_label": "B"},  # 风险承受 → 5-10% 回撤可接受
    {"question_id": "q07", "selected_label": "C"},  # 仓位偏好 → 3-5 只（中等）
    {"question_id": "q08", "selected_label": "C"},  # 板块偏好 → 均衡配置
    {"question_id": "q09", "selected_label": "C"},  # 决策依据 → 技术面+基本面
    {"question_id": "q10", "selected_label": "C"},  # 买卖时机 → 突破后买入（右侧）
    {"question_id": "q11", "selected_label": "C"},  # 信息源 → 都看
    {"question_id": "q12", "selected_label": "C"},  # 操作频率 → 季度调仓
]


# ── 2. HITL 反馈场景：6 轮 Agent 建议 → 用户反馈 ─────────────────────────
# 设计目标：让每个维度都有明显演化轨迹，便于验证推断器准确性
#
# Round 1 approve 中性建议 → 全 0 或微调（accept 弱信号）
# Round 2 reject 高估值成长股 → risk - / decision 基本面 +
# Round 3 reject 短线打板题材 → emotion - / risk -
# Round 4 respond 只看技术面不看财报 → decision 技术面 -
# Round 5 respond 集中持仓 2-3 只 → concentration +
# Round 6 approve 长线持有价值股 → time_horizon + / emotion +
HITL_SCENARIOS = [
    {
        # Round 1：中性建议，approve
        # 预期推断：全 0 或极微调
        "advice_summary": "估值分 55, PE=20, 建议进入技术分析（蓝筹股）",
        "advice_data": {"valuation_score": 55, "pe": 20, "stock": "600519", "action": "进入技术分析"},
        "user_action": "approve",
        "user_response": "继续分析",
    },
    {
        # Round 2：高估值成长股，reject
        # 预期推断：risk_appetite - / decision_basis 基本面方向 / trading_style 左侧
        "advice_summary": "估值分 92, PE=120, 建议进入技术分析（新能源成长股）",
        "advice_data": {"valuation_score": 92, "pe": 120, "stock": "300750", "action": "进入技术分析"},
        "user_action": "reject",
        "user_response": "PE 120 倍估值太高了，等回到 60 倍再考虑",
    },
    {
        # Round 3：短线题材打板，reject
        # 预期推断：emotion_pref 题材 - / risk_appetite - / time_horizon 短线方向
        "advice_summary": "估值分 30, 换手率 35%, 建议进入技术分析（题材打板股）",
        "advice_data": {"valuation_score": 30, "pe": None, "stock": "002XXX", "action": "进入技术分析"},
        "user_action": "reject",
        "user_response": "不追题材打板，这种短线炒作风险太大，我从不参与",
    },
    {
        # Round 4：respond 表达只看技术面
        # 预期推断：decision_basis 技术面方向（-1）/ time_horizon 短线
        "advice_summary": "估值分 60, PE=25, 建议进入技术分析（白马股）",
        "advice_data": {"valuation_score": 60, "pe": 25, "stock": "000858", "action": "进入技术分析"},
        "user_action": "respond",
        "user_response": "财报我不看，只看 K 线和量能，给我画个图分析下技术面就行",
    },
    {
        # Round 5：respond 表达集中持仓偏好
        # 预期推断：concentration 集中方向（+1）
        "advice_summary": "估值分 50, PE=18, 建议分散配置 5 只股票",
        "advice_data": {"valuation_score": 50, "pe": 18, "stock": "MULTI", "action": "分散配置"},
        "user_action": "respond",
        "user_response": "5 只太多了，我只买 2-3 只重仓持有，集中火力",
    },
    {
        # Round 6：approve 长线价值
        # 预期推断：time_horizon 长线方向（+1）/ emotion_pref 价值方向
        "advice_summary": "估值分 35, PE=8, 建议长线持有 3 年（银行股）",
        "advice_data": {"valuation_score": 35, "pe": 8, "stock": "601398", "action": "长线持有 3 年"},
        "user_action": "approve",
        "user_response": "好，长期持有这只银行股，吃分红",
    },
]


def main():
    print("=" * 70)
    print("  Style Profiler v2.0 演示 — 冷启动问卷 + HITL 反馈自进化")
    print("=" * 70)

    # ── 步骤 1：冷启动问卷 ────────────────────────────────────────────
    print("\n[步骤 1] 冷启动问卷：12 题作答初始化画像\n")
    print("  场景: 中性平衡型用户（多数选项选 C，便于观察后续演化）")
    print(f"  作答: {len(COLD_START_ANSWERS)} 题")
    for ans in COLD_START_ANSWERS:
        print(f"    {ans['question_id']} → {ans['selected_label']}")
    print()

    result = cold_start_init(USER_ID, COLD_START_ANSWERS)
    print(f"  冷启动结果: stable={result.get('stable', False)}")
    print(f"  各维度 score:")
    for dim, score in result.get("dimensions", {}).items():
        print(f"    {dim:<20} {score:+.2f}")

    print("\n  冷启动后画像:")
    print(render_ascii_radar(USER_ID))

    # ── 步骤 2：HITL 反馈自进化 ───────────────────────────────────────
    print("\n[步骤 2] HITL 反馈自进化：6 轮 Agent 建议 → 用户反馈\n")

    # 每轮预期（用于人工对比验证）
    expectations = [
        "全 0 或微调（approve 弱信号）",
        "risk - / decision 基本面方向 / trading 左侧",
        "emotion 题材 - / risk - / time 短线",
        "decision 技术面 - / time 短线",
        "concentration 集中 +",
        "time_horizon 长线 + / emotion 价值 +",
    ]

    for i, scenario in enumerate(HITL_SCENARIOS, 1):
        print(f"\n── Round {i} ─────────────────────────────────────────")
        print(f"  Agent 建议: {scenario['advice_summary']}")
        print(f"  用户反馈:   {scenario['user_action']} / {scenario['user_response']}")
        print(f"  预期推断:   {expectations[i-1]}")

        result = observe_feedback(
            user_id=USER_ID,
            thread_id=f"{THREAD_ID}-{i}",
            advice_summary=scenario["advice_summary"],
            advice_data=scenario["advice_data"],
            user_action=scenario["user_action"],
            user_response=scenario["user_response"],
        )

        inferred = result.get("inferred", {})
        applied = result.get("applied_dims", [])
        stable = result.get("stable", False)

        # 只展示非 0 的推断结果，便于对比
        non_zero = {k: round(v, 2) for k, v in inferred.items() if v != 0.0}
        print(f"  LLM 推断:   {non_zero if non_zero else '(全 0)'}")
        print(f"  应用维度:   {applied}")
        print(f"  画像 stable: {stable}")

        # 实时显示当前画像
        radar = get_radar_profile(USER_ID)
        print(f"  当前画像概要: {radar.summary}")

    # ── 步骤 3：最终画像 ──────────────────────────────────────────────
    print("\n[步骤 3] 最终六边形画像:\n")
    print(render_ascii_radar(USER_ID))

    # ── 步骤 4：信号审计 ─────────────────────────────────────────────
    print("\n[步骤 4] feedback_signals 信号审计:")
    try:
        from sqlalchemy import create_engine, text
        from shared.config import settings
        eng = create_engine(settings.DATABASE_URL)
        with eng.connect() as conn:
            rows = conn.execute(text(
                "SELECT user_action, advice_summary, user_response, inferred_scores, applied "
                "FROM feedback_signals WHERE user_id = :uid ORDER BY id"
            ), {"uid": USER_ID}).fetchall()
            for i, r in enumerate(rows, 1):
                print(f"  {i}. action={r[0]} | advice={r[1][:40]}...")
                print(f"     response={r[2]}")
                print(f"     inferred={r[3]}")
                print(f"     applied={r[4]}")
    except Exception as exc:
        print(f"  (审计读取失败: {exc})")

    print("\n" + "=" * 70)
    print("  演示完成")
    print("=" * 70)


if __name__ == "__main__":
    main()
