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
     * 用 JOIN 替代原先的 {@code (symbol, trade_date) IN (子查询)} 写法。
     * 原写法的 tuple IN 子查询会被物化成派生表，导致对外层 market_data 做全表扫描
     * （实测 320 万行规模下 2.2s），且无法通过任何索引改善；改为 JOIN 后可直接
     * 用 (symbol, timeframe, trade_date) 做单行索引定位（同规模下 0.2ms）。
     * <p>
     * 同时显式限定 {@code m.timeframe = '1d'}：原写法外层未限定周期，若某标的
     * 在"最新日线交易日"上还存在其它周期行，会返回多行造成同标的重负。
     *
     * @param symbols 股票代码列表
     * @return 最新行情数据列表，按 symbol 升序
     */
    @Select({"<script>",
            "SELECT m.symbol, m.trade_date AS tradeDate, m.timeframe, m.ts_open AS tsOpen,",
            "       m.open, m.high, m.low, m.close, m.volume, m.amount, m.pct_chg AS pctChg, m.closed",
            "FROM market_data m",
            "JOIN (",
            "  SELECT symbol, MAX(trade_date) AS max_trade_date",
            "  FROM market_data",
            "  WHERE timeframe = '1d'",
            "  AND symbol IN",
            "  <foreach collection='symbols' item='s' open='(' separator=',' close=')'>#{s}</foreach>",
            "  GROUP BY symbol",
            ") latest",
            "  ON m.symbol = latest.symbol",
            "  AND m.timeframe = '1d'",
            "  AND m.trade_date = latest.max_trade_date",
            "ORDER BY m.symbol ASC",
            "</script>"})
    List<MarketData> selectLatestQuote(@Param("symbols") List<String> symbols);

}
