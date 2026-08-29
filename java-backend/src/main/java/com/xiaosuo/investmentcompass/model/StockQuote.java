package com.xiaosuo.investmentcompass.model;

import lombok.AllArgsConstructor;
import lombok.Data;

import java.time.LocalDate;

/**
 * 股票实时行情
 * <p>
 * 包含股票最新收盘价、涨跌幅和前一交易日收盘价。
 */
@Data
@AllArgsConstructor
public class StockQuote {

    /** 股票代码 */
    private String symbol;

    /** 交易日期 */
    private LocalDate tradeDate;

    /** 最新收盘价 */
    private Double close;

    /** 涨跌幅（%） */
    private Double changePct;

    /** 前收盘价 */
    private Double preClose;
}
