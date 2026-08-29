package com.xiaosuo.investmentcompass.model;

import lombok.Data;

/**
 * WebSocket实时行情消息
 * <p>
 * 通过WebSocket推送的实时行情数据，包含最新成交价、涨跌幅、买卖盘口等信息。
 */
@Data
public class RealtimeQuoteMessage {
    /** 股票代码 */
    private String symbol;
    /** 股票名称 */
    private String name;
    /** 最新成交价 */
    private double price;
    /** 涨跌幅（%） */
    private double changePct;
    /** 涨跌额 */
    private double changeAmount;
    /** 前收盘价 */
    private double preClose;
    /** 开盘价 */
    private double open;
    /** 最高价 */
    private double high;
    /** 最低价 */
    private double low;
    /** 成交量（股） */
    private double volume;
    /** 成交额（元） */
    private double amount;
    /** 数据时间戳 */
    private long timestamp;
}
