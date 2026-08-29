package com.xiaosuo.investmentcompass.common.util;

import java.text.MessageFormat;

/**
 * 免责声明工具
 * <p>
 * 提供统一的风险提示声明文本。
 * 原位于 personality.agent 包（已废弃），移至 common.util 包。
 */
public class DisclaimerUtil {

    private static final String DISCLAIMER_TEXT = """
            ⚠️ 免责声明
            以上内容由 AI 根据公开数据分析生成，仅供学习交流参考，
            不构成任何投资建议。投资有风险，入市需谨慎。
            """;

    private static final String DISCLAIMER_FORMAT = """
            ⚠️ 免责声明
            以上内容由 AI 根据公开数据分析生成，仅供学习交流参考，
            不构成任何投资建议。投资有风险，入市需谨慎。
            {0}
            """;

    private DisclaimerUtil() {}

    public static String getDisclaimer() {
        return DISCLAIMER_TEXT.trim();
    }

    public static String getFormattedDisclaimer(Object... args) {
        return MessageFormat.format(DISCLAIMER_FORMAT.trim(), args);
    }

    /**
     * 在指定内容后追加免责声明
     *
     * @param content 原始内容
     * @return 追加了免责声明后的完整文本
     */
    public static String appendDisclaimer(String content) {
        if (content == null || content.isBlank()) {
            return DISCLAIMER_TEXT.trim();
        }
        return content + "\n\n" + DISCLAIMER_TEXT.trim();
    }
}