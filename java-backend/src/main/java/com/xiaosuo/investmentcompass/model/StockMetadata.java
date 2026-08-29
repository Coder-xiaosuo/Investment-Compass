package com.xiaosuo.investmentcompass.model;

import com.mybatisflex.annotation.Id;
import com.mybatisflex.annotation.Table;
import lombok.Data;

/**
 * 品种注册表实体
 * <p>
 * 对应数据库 stock_metadata 表，注册需要跟踪的股票/ETF/指数品种信息。
 */
@Data
@Table("stock_metadata")
public class StockMetadata {

    /** 主键ID */
    @Id
    private Integer id;

    /** 股票代码，含交易所后缀，如 000001.SZ / 600519.SH */
    private String symbol;

    /** 股票名称 */
    private String stockName;

    /** 是否启用跟踪：1=启用，0=停用 */
    private Integer isActive;
}
