package com.xiaosuo.investmentcompass.model;

import lombok.Data;

import java.time.LocalDate;

/**
 * 个股详情聚合 DTO
 * <p>
 * 聚合 stock_metadata 与 market_data 最新 1d 记录，用于个股详情展示。
 * 非直接映射数据库表的实体，仅作为数据传输对象使用。
 */
@Data
public class StockDetail {

    // === 来自 stock_metadata 的字段 ===

    /** 股票代码，含交易所后缀，如 000001.SZ / 600519.SH */
    private String symbol;

    /** 股票名称 */
    private String stockName;

    /** 所属行业（预留字段，当前为 null） */
    private String industry;

    /** 上市日期（预留字段，当前为 null） */
    private LocalDate listDate;

    // === 来自 market_data 最新 1d 记录的字段 ===

    /** 最新收盘价 */
    private Double latestClose;

    /** 最新开盘价 */
    private Double latestOpen;

    /** 最新最高价 */
    private Double latestHigh;

    /** 最新最低价 */
    private Double latestLow;

    /** 最新成交量（股） */
    private Long latestVolume;

    /** 最新成交额（元） */
    private Double latestAmount;

    /** 最新涨跌幅（%） */
    private Double latestPctChg;

    /** 最新交易日 */
    private LocalDate latestTradeDate;

    // === 计算字段 ===

    /** 涨跌额 */
    private Double change;

    /** 涨跌幅百分比 */
    private Double changePercent;
}
