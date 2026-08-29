package com.xiaosuo.investmentcompass.model;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import lombok.AllArgsConstructor;
import lombok.Data;

import java.time.LocalDate;

/**
 * K线数据条目
 * <p>
 * 单根K线的完整数据，包含开高低收、成交量、成交额和涨跌幅。
 */
@Data
@AllArgsConstructor
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class StockKlineBar {

    /** 交易日 */
    private LocalDate tradeDate;

    /** K线开盘Unix毫秒时间戳(UTC) */
    private Long tsOpen;

    /** 开盘价 */
    private Double open;

    /** 最高价 */
    private Double high;

    /** 最低价 */
    private Double low;

    /** 收盘价 */
    private Double close;

    /** 成交量（股） */
    private Long volume;

    /** 成交额（元） */
    private Double amount;

    /** 涨跌幅（%） */
    private Double pctChg;

    /** K线是否已收盘：1=已收盘，0=正在形成 */
    private Integer closed;

    /** 量比 */
    private Double volumeRatio;

    /** 换手率（%） */
    private Double turnoverRate;
}
