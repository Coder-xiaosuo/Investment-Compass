package com.xiaosuo.investmentcompass.mapper;

import com.mybatisflex.core.BaseMapper;
import com.xiaosuo.investmentcompass.model.DataQualityIssue;
import com.xiaosuo.investmentcompass.model.MarketData;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Map;

@Repository
public interface MonitorMapper extends BaseMapper<DataQualityIssue> {

    @Select("SELECT " +
            "  COUNT(*) AS total_rows, " +
            "  COUNT(DISTINCT symbol) AS stock_count, " +
            "  MIN(trade_date) AS min_date, " +
            "  MAX(trade_date) AS max_date, " +
            "  NOW() AS query_time " +
            "FROM market_data " +
            "WHERE timeframe = '1d'")
    Map<String, Object> selectOverview();

    @Select("SELECT " +
            "  COUNT(*) AS total, " +
            "  SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) AS success_count, " +
            "  SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) AS failed_count, " +
            "  SUM(CASE WHEN status = 'RUNNING' THEN 1 ELSE 0 END) AS running_count, " +
            "  SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) AS pending_count, " +
            "  SUM(CASE WHEN status = 'PARTIAL' THEN 1 ELSE 0 END) AS partial_count, " +
            "  SUM(records_fetched) AS total_records " +
            "FROM sync_task")
    Map<String, Object> selectBackfillProgress();

    @Select("SELECT " +
            "  (SELECT COUNT(*) FROM stock_metadata WHERE is_active = 1) AS total_stocks, " +
            "  (SELECT COUNT(DISTINCT symbol) FROM market_data WHERE timeframe = '1d') AS covered_stocks")
    Map<String, Object> selectCoverageSummary();

    @Select({"<script>",
            "SELECT sm.symbol, sm.stock_name",
            "FROM stock_metadata sm",
            "LEFT JOIN market_data md ON md.symbol = sm.symbol AND md.timeframe = '1d'",
            "WHERE sm.is_active = 1",
            "  AND md.symbol IS NULL",
            "ORDER BY sm.symbol",
            "LIMIT #{limit}",
            "</script>"})
    List<Map<String, Object>> selectMissingSymbols(@Param("limit") int limit);

    @Select({"<script>",
            "SELECT * FROM data_quality_issue",
            "WHERE 1 = 1",
            "<if test='status != null and status != \"\"'>",
            "  AND status = #{status}",
            "</if>",
            "<if test='issueType != null and issueType != \"\"'>",
            "  AND issue_type = #{issueType}",
            "</if>",
            "<if test='symbol != null and symbol != \"\"'>",
            "  AND symbol = #{symbol}",
            "</if>",
            "ORDER BY scan_time DESC",
            "LIMIT 200",
            "</script>"})
    List<DataQualityIssue> selectQualityIssues(
            @Param("status") String status,
            @Param("issueType") String issueType,
            @Param("symbol") String symbol);

    @Update("UPDATE data_quality_issue SET status = #{status}, fix_time = NOW() WHERE id = #{id}")
    int updateIssueStatus(@Param("id") Long id, @Param("status") String status);

    @Select("SELECT * FROM market_data WHERE symbol = #{symbol} AND timeframe = '1d' ORDER BY trade_date DESC LIMIT 1")
    MarketData selectStockLatestBySymbol(@Param("symbol") String symbol);
}
