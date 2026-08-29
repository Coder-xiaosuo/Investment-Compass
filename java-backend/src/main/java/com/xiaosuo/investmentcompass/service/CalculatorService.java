package com.xiaosuo.investmentcompass.service;

import com.xiaosuo.investmentcompass.model.StockQuote;
import org.springframework.stereotype.Service;

import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

/**
 * 计算器服务
 * <p>
 * 提供技术指标计算和数据排序等基础计算功能。
 */
@Service
public class CalculatorService {

    /**
     * 计算移动平均线（MA）
     * <p>
     * 对收盘价序列计算指定周期的简单移动平均。
     * 前 period-1 个位置返回 NaN（数据不足）。
     *
     * @param closes 收盘价序列，按时间正序排列
     * @param period 移动平均周期
     * @return 移动平均计算结果，长度与 closes 相同
     * @throws IllegalArgumentException 如果参数无效
     */
    public double[] ma(List<Double> closes, int period) {
        if (closes == null || period <= 0 || period > closes.size()) {
            throw new IllegalArgumentException("收盘价数据不能为空，且周期必须大于0且不超过数据长度");
        }

        double[] result = new double[closes.size()];

        for (int i = 0; i < period - 1; i++) {
            result[i] = Double.NaN;
        }

        for (int i = period - 1; i < closes.size(); i++) {
            double sum = 0;
            for (int j = i - period + 1; j <= i; j++) {
                sum += closes.get(j);
            }
            result[i] = sum / period;
        }

        return result;
    }

    /**
     * 按涨跌幅排序
     * <p>
     * 对股票行情列表按涨跌幅进行升序或降序排序，返回前 limit 条。
     *
     * @param quotes   股票行情列表
     * @param limit    返回数量上限
     * @param ascending true=升序（跌幅榜），false=降序（涨幅榜）
     * @return 排序后的行情列表
     */
    public List<StockQuote> rankingByChange(List<StockQuote> quotes, int limit, boolean ascending) {
        if (quotes == null || quotes.isEmpty()) {
            return List.of();
        }

        return quotes.stream()
                .sorted(ascending
                        ? Comparator.comparingDouble((StockQuote q) -> q.getChangePct() != null ? q.getChangePct() : 0.0)
                        : Comparator.comparingDouble((StockQuote q) -> q.getChangePct() != null ? q.getChangePct() : 0.0).reversed())
                .limit(limit)
                .collect(Collectors.toList());
    }
}
