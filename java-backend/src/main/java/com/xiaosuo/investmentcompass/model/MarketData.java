package com.xiaosuo.investmentcompass.model;

import com.mybatisflex.annotation.Id;
import com.mybatisflex.annotation.Table;
import lombok.Data;

import java.time.LocalDate;

/**
 * K线行情数据实体
 * <p>
 * 对应数据库 market_data 表，存储股票/指数的K线行情数据。
 * 字段设计与 KlineBar 模型对齐，支持多周期存储。
 */
@Data
@Table("market_data")
public class MarketData {

    /** 主键ID */
    @Id
    private Long id;

    /** 股票代码，含交易所后缀，如 000001.SZ */
    private String symbol;

    /** 交易日（A股市场日期） */
    private LocalDate tradeDate;

    /** K线周期：1m/5m/15m/30m/1h/4h/1d */
    private String timeframe;

    /** K线开盘Unix毫秒时间戳(UTC) */
    private Long tsOpen;

    /** 开盘价 */
    private Double open;

    /** 最高价 */
    private Double high;

    /** 最低价 */
    private Double low;

    /** 收盘价/最新价 */
    private Double close;

    /** 成交量（股） */
    private Long volume;

    /** 成交额（元） */
    private Double amount;

    /** 涨跌幅（%），正值上涨，负值下跌 */
    private Double pctChg;

    /** K线是否已收盘：1=已收盘，0=正在形成 */
    private Integer closed;
}
