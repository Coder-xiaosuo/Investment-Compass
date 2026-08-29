package com.xiaosuo.investmentcompass.controller;

import com.xiaosuo.investmentcompass.common.BaseResponse;
import com.xiaosuo.investmentcompass.common.ResultUtils;
import com.xiaosuo.investmentcompass.model.DataQualityIssue;
import com.xiaosuo.investmentcompass.service.MonitorService;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/monitor")
public class MonitorController {

    private final MonitorService monitorService;

    public MonitorController(MonitorService monitorService) {
        this.monitorService = monitorService;
    }

    @GetMapping("/overview")
    public BaseResponse<Map<String, Object>> overview() {
        Map<String, Object> result = monitorService.getOverview();
        return ResultUtils.success(result);
    }

    @GetMapping("/backfill-progress")
    public BaseResponse<Map<String, Object>> backfillProgress() {
        Map<String, Object> result = monitorService.getBackfillProgress();
        return ResultUtils.success(result);
    }

    @GetMapping("/coverage")
    public BaseResponse<Map<String, Object>> coverage(
            @RequestParam(defaultValue = "50") int limit) {
        Map<String, Object> result = monitorService.getCoverage(limit);
        return ResultUtils.success(result);
    }

    @GetMapping("/quality-issues")
    public BaseResponse<List<DataQualityIssue>> qualityIssues(
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String issueType,
            @RequestParam(required = false) String symbol) {
        List<DataQualityIssue> result = monitorService.getQualityIssues(status, issueType, symbol);
        return ResultUtils.success(result);
    }

    @PostMapping("/quality-issues/{id}/status")
    public BaseResponse<Boolean> updateIssueStatus(
            @PathVariable Long id,
            @RequestParam String status) {
        boolean result = monitorService.updateIssueStatus(id, status);
        return ResultUtils.success(result);
    }
}
