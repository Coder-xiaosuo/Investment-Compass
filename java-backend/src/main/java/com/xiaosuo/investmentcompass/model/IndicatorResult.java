package com.xiaosuo.investmentcompass.model;

import lombok.Data;

import java.time.LocalDate;
import java.util.List;

/**
 * 技术指标计算结果
 * <p>
 * 封装 MA、EMA、MACD 等技术指标的计算结果，用于接口返回。
 */
@Data
public class IndicatorResult {

    /** 股票代码 */
    private String symbol;

    /** 指标类型：ma / ema / macd */
    private String type;

    /** 与数据对齐的交易日列表 */
    private List<LocalDate> tradeDates;

    /** MA/EMA 的单值结果（type=ma 或 ema 时使用） */
    private List<Double> values;

    /** MACD 的 DIF 线（type=macd 时使用） */
    private List<Double> dif;

    /** MACD 的 DEA 线（type=macd 时使用） */
    private List<Double> dea;

    /** MACD 的 MACD 柱状图（type=macd 时使用） */
    private List<Double> macd;
}
