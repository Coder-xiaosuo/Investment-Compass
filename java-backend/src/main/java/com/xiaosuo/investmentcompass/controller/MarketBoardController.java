package com.xiaosuo.investmentcompass.controller;

import com.xiaosuo.investmentcompass.common.BaseResponse;
import com.xiaosuo.investmentcompass.common.ResultUtils;
import com.xiaosuo.investmentcompass.model.MarketIndex;
import com.xiaosuo.investmentcompass.model.StockQuote;
import com.xiaosuo.investmentcompass.service.MarketBoardService;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * 大盘行情看板接口控制器
 * <p>
 * 提供大盘指数行情和个股涨跌幅排名查询接口。
 */
@RestController
@RequestMapping("/market")
public class MarketBoardController {

    private final MarketBoardService marketBoardService;

    public MarketBoardController(MarketBoardService marketBoardService) {
        this.marketBoardService = marketBoardService;
    }

    /**
     * 获取主要指数行情
     * <p>
     * 返回上证指数、深证成指、创业板指、科创50等主要指数的实时行情数据。
     *
     * @return 指数行情列表
     */
    @GetMapping("/indices")
    public BaseResponse<List<MarketIndex>> getIndices() {
        List<MarketIndex> indices = marketBoardService.getIndices();
        return ResultUtils.success(indices);
    }

    /**
     * 获取涨跌幅排名
     *
     * @param type  排名类型：top_gainers（涨幅榜）/ top_losers（跌幅榜）
     * @param limit 返回数量限制，默认20条
     * @return 涨跌幅排名列表
     */
    @GetMapping("/ranking")
    public BaseResponse<List<StockQuote>> getRanking(
            @RequestParam(defaultValue = "top_gainers") String type,
            @RequestParam(defaultValue = "20") int limit) {
        List<StockQuote> ranking = marketBoardService.getRanking(type, limit);
        return ResultUtils.success(ranking);
    }
}
