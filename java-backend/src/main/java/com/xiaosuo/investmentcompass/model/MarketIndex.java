package com.xiaosuo.investmentcompass.model;

import lombok.Data;

/**
 * 指数行情
 * <p>
 * 包含主要市场指数的行情信息，如上证指数、深证成指等。
 */
@Data
public class MarketIndex {

    /** 指数代码 */
    private String symbol;

    /** 指数名称 */
    private String stockName;

    /** 最新收盘价 */
    private Double close;

    /** 涨跌幅（%） */
    private Double changePct;

    /** 交易日期 */
    private String tradeDate;
}
