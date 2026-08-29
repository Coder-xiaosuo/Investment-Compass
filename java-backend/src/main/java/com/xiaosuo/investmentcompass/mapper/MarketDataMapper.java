package com.xiaosuo.investmentcompass.mapper;

import com.mybatisflex.core.BaseMapper;
import com.xiaosuo.investmentcompass.model.MarketData;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.springframework.stereotype.Repository;

import java.util.List;

/**
 * K线行情数据 Mapper
 * <p>
 * 提供市场行情数据的数据库访问接口，支持多品种最新行情的批量查询。
 */
@Repository
public interface MarketDataMapper extends BaseMapper<MarketData> {

    /**
     * 批量查询多个品种的最新日线行情
     * <p>
     * 使用子查询获取每个 symbol 的最新交易日数据。
     *
     * @param symbols 股票代码列表
     * @return 最新行情数据列表
     */
    @Select({"<script>",
            "SELECT symbol, trade_date AS tradeDate, timeframe, ts_open AS tsOpen,",
            "       open, high, low, close, volume, amount, pct_chg AS pctChg, closed",
            "FROM market_data",
            "WHERE (symbol, trade_date) IN (",
            "  SELECT symbol, MAX(trade_date) FROM market_data",
            "  WHERE timeframe = '1d'",
            "  AND symbol IN",
            "  <foreach collection='symbols' item='s' open='(' separator=',' close=')'>#{s}</foreach>",
            "  GROUP BY symbol",
            ") ORDER BY symbol ASC",
            "</script>"})
    List<MarketData> selectLatestQuote(@Param("symbols") List<String> symbols);

}
