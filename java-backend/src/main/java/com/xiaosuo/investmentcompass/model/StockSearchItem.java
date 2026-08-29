package com.xiaosuo.investmentcompass.model;

import lombok.AllArgsConstructor;
import lombok.Data;

/**
 * 股票搜索结果项
 * <p>
 * 股票搜索功能的返回项，包含股票代码和名称。
 */
@Data
@AllArgsConstructor
public class StockSearchItem {

    /** 股票代码 */
    private String symbol;

    /** 股票名称 */
    private String stockName;
}
