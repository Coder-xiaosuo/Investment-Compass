package com.xiaosuo.investmentcompass.model;

import lombok.AllArgsConstructor;
import lombok.Data;

import java.util.List;

/**
 * K线数据响应
 * <p>
 * 封装K线历史数据的查询结果，包含股票代码、时间周期和K线列表。
 */
@Data
@AllArgsConstructor
public class StockKlineResponse {

    /** 股票代码，含交易所后缀 */
    private String symbol;

    /** K线周期（1m/5m/15m/30m/1h/4h/1d） */
    private String timeframe;

    /** K线数据列表 */
    private List<StockKlineBar> bars;
}
