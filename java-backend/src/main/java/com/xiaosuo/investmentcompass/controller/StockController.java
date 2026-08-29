package com.xiaosuo.investmentcompass.controller;

import com.xiaosuo.investmentcompass.common.BaseResponse;
import com.xiaosuo.investmentcompass.common.ResultUtils;
import com.xiaosuo.investmentcompass.model.*;
import com.xiaosuo.investmentcompass.service.StockService;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDate;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

/**
 * 股票数据接口控制器
 * <p>
 * 提供股票搜索、实时行情和K线历史数据查询接口。
 */
@RestController
@RequestMapping("/stock")
public class StockController {

    private final StockService stockService;

    public StockController(StockService stockService) {
        this.stockService = stockService;
    }

    /**
     * 搜索股票
     *
     * @param keyword 搜索关键词（股票代码或名称）
     * @param limit   返回数量限制，默认10条
     * @return 股票搜索结果列表
     */
    @GetMapping("/search")
    public BaseResponse<List<StockSearchItem>> searchStocks(
            @RequestParam String keyword,
            @RequestParam(defaultValue = "10") Integer limit) {
        List<StockSearchItem> result = stockService.searchStocks(keyword, limit);
        return ResultUtils.success(result);
    }

    /**
     * 获取股票实时行情
     *
     * @param symbols 股票代码列表，多个代码用逗号分隔，如 "000001.SZ,600519.SH"
     * @return 实时行情列表
     */
    @GetMapping("/quote")
    public BaseResponse<List<StockQuote>> getQuote(
            @RequestParam String symbols) {
        List<String> symbolList = Arrays.stream(symbols.split(","))
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .collect(Collectors.toList());
        List<StockQuote> result = stockService.getLatestQuote(symbolList);
        return ResultUtils.success(result);
    }

    /**
     * 获取K线历史数据
     * <p>
     * 支持不带交易所后缀的股票代码（自动补全）。
     * 日期范围优先于 limit；同时提供 start_date/end_date 时忽略 limit。
     *
     * @param symbol    股票代码，可带或不带交易所后缀，如 000001.SZ 或 000001
     * @param timeframe K线周期，默认"1d"，支持：1m/5m/15m/30m/1h/4h/1d
     * @param startDate 开始日期（可选），格式 YYYY-MM-DD
     * @param endDate   结束日期（可选），格式 YYYY-MM-DD
     * @param limit     返回K线数量，默认120条
     * @return K线历史数据响应
     */
    @GetMapping("/kline")
    public BaseResponse<StockKlineResponse> getKline(
            @RequestParam String symbol,
            @RequestParam(defaultValue = "1d") String timeframe,
            @RequestParam(required = false) @DateTimeFormat(pattern = "yyyy-MM-dd") LocalDate startDate,
            @RequestParam(required = false) @DateTimeFormat(pattern = "yyyy-MM-dd") LocalDate endDate,
            @RequestParam(defaultValue = "120") Integer limit) {
        StockKlineResponse result = stockService.getKlineHistory(symbol, timeframe, startDate, endDate, limit);
        return ResultUtils.success(result);
    }

    /**
     * 获取股票详情
     *
     * @param symbol 股票代码
     * @return 股票详情
     */
    @GetMapping("/detail/{symbol}")
    public BaseResponse<StockDetail> getStockDetail(@PathVariable String symbol) {
        StockDetail detail = stockService.getStockDetail(symbol);
        return ResultUtils.success(detail);
    }

    /**
     * 获取股票技术指标
     *
     * @param symbol 股票代码
     * @param type   指标类型
     * @param period 指标周期
     * @param limit  返回数量限制，默认120条
     * @return 技术指标结果
     */
    @GetMapping("/indicators/{symbol}")
    public BaseResponse<IndicatorResult> getIndicators(
            @PathVariable String symbol,
            @RequestParam String type,
            @RequestParam(required = false) Integer period,
            @RequestParam(defaultValue = "120") Integer limit) {
        IndicatorResult result = stockService.getIndicators(symbol, type, period, limit);
        return ResultUtils.success(result);
    }
}
