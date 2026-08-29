package com.xiaosuo.investmentcompass.controller;

import com.xiaosuo.investmentcompass.common.BaseResponse;
import com.xiaosuo.investmentcompass.common.ResultUtils;
import com.xiaosuo.investmentcompass.model.Watchlist;
import com.xiaosuo.investmentcompass.service.WatchlistService;
import jakarta.annotation.Resource;
import lombok.Data;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * 自选股管理接口控制器
 * <p>
 * 提供自选股的列表查询、添加、删除和排序功能。
 */
@RestController
@RequestMapping("/watchlist")
public class WatchlistController {

    @Resource
    private  WatchlistService watchlistService;

    /**
     * 获取自选股列表
     *
     * @return 自选股列表（含股票名称与最新行情），按排序字段升序排列
     */
    @GetMapping("/list")
    public BaseResponse<List<WatchlistService.WatchlistQuote>> list() {
        List<WatchlistService.WatchlistQuote> watchlistList = watchlistService.list();
        return ResultUtils.success(watchlistList);
    }

    /**
     * 添加自选股
     *
     * @param request 添加请求，包含股票代码和分组名称
     * @return 添加后的自选股记录
     */
    @PostMapping("/add")
    public BaseResponse<Watchlist> add(@RequestBody AddRequest request) {
        Watchlist watchlist = watchlistService.add(request.getSymbol(), request.getGroupName());
        return ResultUtils.success(watchlist);
    }

    /**
     * 移除自选股
     *
     * @param request 移除请求，包含股票代码和分组名称
     * @return 是否移除成功
     */
    @PostMapping("/remove")
    public BaseResponse<Boolean> remove(@RequestBody RemoveRequest request) {
        boolean result = watchlistService.remove(request.getSymbol(), request.getGroupName());
        return ResultUtils.success(result);
    }

    /**
     * 重新排序自选股
     *
     * @param request 排序请求，包含排序项列表（id + 排序值）
     */
    @PostMapping("/reorder")
    public BaseResponse<Void> reorder(@RequestBody ReorderRequest request) {
        watchlistService.reorder(request.getItems());
        return ResultUtils.success(null);
    }

    /**
     * 添加自选股请求
     */
    @Data
    private static class AddRequest {
        private String symbol;
        private String groupName;
    }

    /**
     * 移除自选股请求
     */
    @Data
    private static class RemoveRequest {
        private String symbol;
        private String groupName;
    }

    /**
     * 重排序请求
     */
    @Data
    private static class ReorderRequest {
        private List<WatchlistService.ReorderItem> items;
    }
}
