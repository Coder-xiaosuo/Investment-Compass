package com.xiaosuo.investmentcompass.service;

import org.springframework.stereotype.Service;

import java.util.HashMap;
import java.util.Map;

/**
 * 技术指标计算服务
 * <p>
 * 提供纯数学计算的技术指标：MA（简单移动平均线）、EMA（指数移动平均线）、MACD。
 */
@Service
public class IndicatorService {

    /**
     * 计算简单移动平均线（MA）
     * <p>
     * 前 {@code period - 1} 个值设为 {@link Double#NaN}，
     * 从索引 {@code period - 1} 开始，计算前 {@code period} 个收盘价的平均值。
     *
     * @param closes 收盘价序列，按时间正序排列
     * @param period 移动平均周期
     * @return MA 计算结果，长度与 {@code closes} 相同
     * @throws IllegalArgumentException 如果参数无效
     */
    public double[] ma(double[] closes, int period) {
        if (closes == null || period <= 0 || period > closes.length) {
            throw new IllegalArgumentException("收盘价数据不能为空，且周期必须大于0且不超过数据长度");
        }

        double[] result = new double[closes.length];

        for (int i = 0; i < period - 1; i++) {
            result[i] = Double.NaN;
        }

        for (int i = period - 1; i < closes.length; i++) {
            double sum = 0;
            for (int j = i - period + 1; j <= i; j++) {
                sum += closes[j];
            }
            result[i] = sum / period;
        }

        return result;
    }

    /**
     * 计算指数移动平均线（EMA）
     * <p>
     * 公式：EMA_today = (close_today * k) + (EMA_yesterday * (1 - k))，其中 k = 2 / (period + 1)。
     * 第一个 EMA 值（索引 {@code period - 1}）用前 {@code period} 个收盘价的 SMA 作为初始值，
     * 前 {@code period - 1} 个值设为 {@link Double#NaN}。
     *
     * @param closes 收盘价序列，按时间正序排列
     * @param period 移动平均周期
     * @return EMA 计算结果，长度与 {@code closes} 相同
     * @throws IllegalArgumentException 如果参数无效
     */
    public double[] ema(double[] closes, int period) {
        if (closes == null || period <= 0 || period > closes.length) {
            throw new IllegalArgumentException("收盘价数据不能为空，且周期必须大于0且不超过数据长度");
        }

        double[] result = new double[closes.length];

        for (int i = 0; i < period - 1; i++) {
            result[i] = Double.NaN;
        }

        double k = 2.0 / (period + 1);

        // 第一个 EMA 值用前 period 个收盘价的 SMA 作为初始值
        double sum = 0;
        for (int i = 0; i < period; i++) {
            sum += closes[i];
        }
        result[period - 1] = sum / period;

        for (int i = period; i < closes.length; i++) {
            result[i] = closes[i] * k + result[i - 1] * (1 - k);
        }

        return result;
    }

    /**
     * 计算 MACD 指标
     * <p>
     * 参数固定为：shortPeriod=12, longPeriod=26, signalPeriod=9。
     * 返回包含 "dif"、"dea"、"macd" 三个键的 Map。
     *
     * @param closes 收盘价序列，按时间正序排列
     * @return Map，键为 "dif"、"dea"、"macd"，值为对应的双精度数组
     * @throws IllegalArgumentException 如果参数无效或数据不足以计算 MACD
     */
    public Map<String, double[]> macd(double[] closes) {
        if (closes == null || closes.length < 26) {
            throw new IllegalArgumentException("收盘价数据长度至少为26才能计算MACD");
        }

        int shortPeriod = 12;
        int longPeriod = 26;
        int signalPeriod = 9;

        double[] ema12 = ema(closes, shortPeriod);
        double[] ema26 = ema(closes, longPeriod);

        double[] dif = new double[closes.length];
        for (int i = 0; i < closes.length; i++) {
            if (Double.isNaN(ema12[i]) || Double.isNaN(ema26[i])) {
                dif[i] = Double.NaN;
            } else {
                dif[i] = ema12[i] - ema26[i];
            }
        }

        // 提取 dif 中的有效值（非 NaN），计算 DEA（EMA of DIF）
        int validCount = 0;
        for (double v : dif) {
            if (!Double.isNaN(v)) {
                validCount++;
            }
        }

        double[] validDif = new double[validCount];
        int idx = 0;
        for (double v : dif) {
            if (!Double.isNaN(v)) {
                validDif[idx++] = v;
            }
        }

        double[] validDea = ema(validDif, signalPeriod);

        // 将 DEA 映射回与 dif 相同长度的数组
        double[] dea = new double[closes.length];
        int validDeaIdx = 0;
        for (int i = 0; i < closes.length; i++) {
            if (Double.isNaN(dif[i])) {
                dea[i] = Double.NaN;
            } else {
                dea[i] = validDea[validDeaIdx++];
            }
        }

        double[] macd = new double[closes.length];
        for (int i = 0; i < closes.length; i++) {
            if (Double.isNaN(dif[i]) || Double.isNaN(dea[i])) {
                macd[i] = Double.NaN;
            } else {
                macd[i] = (dif[i] - dea[i]) * 2;
            }
        }

        Map<String, double[]> result = new HashMap<>();
        result.put("dif", dif);
        result.put("dea", dea);
        result.put("macd", macd);
        return result;
    }
}
