package com.xiaosuo.investmentcompass.service;

import com.xiaosuo.investmentcompass.mapper.MonitorMapper;
import com.xiaosuo.investmentcompass.model.DataQualityIssue;
import org.springframework.stereotype.Service;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Service
public class MonitorService {

    private final MonitorMapper monitorMapper;

    public MonitorService(MonitorMapper monitorMapper) {
        this.monitorMapper = monitorMapper;
    }

    public Map<String, Object> getOverview() {
        Map<String, Object> raw = monitorMapper.selectOverview();
        Map<String, Object> result = new HashMap<>();
        result.put("totalRows", raw.get("total_rows"));
        result.put("stockCount", raw.get("stock_count"));
        result.put("minDate", raw.get("min_date") != null ? raw.get("min_date").toString() : null);
        result.put("maxDate", raw.get("max_date") != null ? raw.get("max_date").toString() : null);
        result.put("queryTime", raw.get("query_time") != null ? raw.get("query_time").toString() : null);
        return result;
    }

    public Map<String, Object> getBackfillProgress() {
        Map<String, Object> raw = monitorMapper.selectBackfillProgress();
        Map<String, Object> result = new HashMap<>();
        result.put("total", raw.get("total"));
        result.put("successCount", raw.get("success_count"));
        result.put("failedCount", raw.get("failed_count"));
        result.put("runningCount", raw.get("running_count"));
        result.put("pendingCount", raw.get("pending_count"));
        result.put("partialCount", raw.get("partial_count"));
        result.put("totalRecords", raw.get("total_records"));

        Number total = (Number) raw.get("total");
        Number successCount = (Number) raw.get("success_count");
        if (total != null && total.longValue() > 0 && successCount != null) {
            double pct = successCount.doubleValue() / total.doubleValue() * 100;
            result.put("progressPct", Math.round(pct * 100.0) / 100.0);
        } else {
            result.put("progressPct", 0.0);
        }
        return result;
    }

    public Map<String, Object> getCoverage(int limit) {
        Map<String, Object> raw = monitorMapper.selectCoverageSummary();
        Map<String, Object> result = new HashMap<>();
        result.put("totalStocks", raw.get("total_stocks"));
        result.put("coveredStocks", raw.get("covered_stocks"));

        Number total = (Number) raw.get("total_stocks");
        Number covered = (Number) raw.get("covered_stocks");
        if (total != null && total.longValue() > 0 && covered != null) {
            double pct = covered.doubleValue() / total.doubleValue() * 100;
            result.put("coveragePct", Math.round(pct * 100.0) / 100.0);
        } else {
            result.put("coveragePct", 0.0);
        }

        List<Map<String, Object>> missing = monitorMapper.selectMissingSymbols(limit);
        result.put("missingSymbols", missing);
        return result;
    }

    public List<DataQualityIssue> getQualityIssues(String status, String issueType, String symbol) {
        return monitorMapper.selectQualityIssues(status, issueType, symbol);
    }

    public boolean updateIssueStatus(Long id, String status) {
        return monitorMapper.updateIssueStatus(id, status) > 0;
    }
}
