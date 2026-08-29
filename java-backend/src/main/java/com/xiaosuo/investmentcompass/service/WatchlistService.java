package com.xiaosuo.investmentcompass.service;

import com.mybatisflex.core.query.QueryWrapper;
import com.xiaosuo.investmentcompass.exception.BusinessException;
import com.xiaosuo.investmentcompass.exception.ErrorCode;
import com.xiaosuo.investmentcompass.mapper.MarketDataMapper;
import com.xiaosuo.investmentcompass.mapper.StockMetadataMapper;
import com.xiaosuo.investmentcompass.mapper.WatchlistMapper;
import com.xiaosuo.investmentcompass.model.MarketData;
import com.xiaosuo.investmentcompass.model.StockMetadata;
import com.xiaosuo.investmentcompass.model.Watchlist;
import jakarta.annotation.Resource;
import lombok.Data;
import org.springframework.stereotype.Service;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

/**
 * 自选股管理服务
 * <p>
 * 提供自选股的列表查询、添加、删除和排序功能。
 * 列表返回时联动股票名称与最新行情（收盘价、涨跌幅、前收盘价）。
 */
@Service
public class WatchlistService {

    @Resource
    private  WatchlistMapper watchlistMapper;

    @Resource
    private  StockMetadataMapper stockMetadataMapper;

    @Resource
    private  MarketDataMapper marketDataMapper;

    /**
     * 获取所有自选股列表（含股票名称与最新行情）
     * <p>
     * 按排序字段升序返回所有自选股记录，并批量关联最新日线行情。
     *
     * @return 自选股列表（含名称与行情）
     */
    public List<WatchlistQuote> list() {
        QueryWrapper queryWrapper = QueryWrapper.create()
                .orderBy(Watchlist::getSortOrder, true);
        List<Watchlist> watchlists = watchlistMapper.selectListByQuery(queryWrapper);
        if (watchlists.isEmpty()) {
            return Collections.emptyList();
        }

        List<String> symbols = watchlists.stream()
                .map(Watchlist::getSymbol)
                .collect(Collectors.toList());
        List<MarketData> quotes = marketDataMapper.selectLatestQuote(symbols);
        Map<String, MarketData> quoteMap = quotes.stream()
                .collect(Collectors.toMap(
                        MarketData::getSymbol,
                        q -> q,
                        (a, b) -> a,
                        LinkedHashMap::new));

        return watchlists.stream()
                .map(w -> {
                    WatchlistQuote quote = new WatchlistQuote();
                    quote.setId(w.getId());
                    quote.setSymbol(w.getSymbol());
                    quote.setSymbolName(w.getSymbolName());
                    quote.setGroupName(w.getGroupName());
                    quote.setSortOrder(w.getSortOrder());
                    quote.setNote(w.getNote());
                    quote.setCreatedAt(w.getCreatedAt());
                    quote.setUpdatedAt(w.getUpdatedAt());

                    MarketData md = quoteMap.get(w.getSymbol());
                    if (md != null) {
                        quote.setClose(md.getClose());
                        quote.setChangePct(md.getPctChg());
                        quote.setTradeDate(md.getTradeDate());
                        Double close = md.getClose();
                        Double pct = md.getPctChg();
                        if (close != null && pct != null) {
                            quote.setPreClose(close / (1 + pct / 100));
                        }
                    }
                    return quote;
                })
                .collect(Collectors.toList());
    }

    /**
     * 添加自选股
     * <p>
     * 如果未指定分组名称，则默认放入"默认"分组。
     * 同一分组下不允许重复添加同一股票。
     *
     * @param symbol   股票代码
     * @param groupName 分组名称
     * @return 添加后的自选股记录
     * @throws BusinessException 如果该自选股已存在
     */
    public Watchlist add(String symbol, String groupName) {
        if (symbol == null || symbol.isBlank()) {
            throw new BusinessException(ErrorCode.PARAMS_ERROR, "股票代码不能为空");
        }
        symbol = symbol.trim();

        if (groupName == null || groupName.isBlank()) {
            groupName = "默认";
        }

        QueryWrapper queryWrapper = QueryWrapper.create()
                .eq(Watchlist::getSymbol, symbol)
                .eq(Watchlist::getGroupName, groupName);
        Watchlist existing = watchlistMapper.selectOneByQuery(queryWrapper);
        if (existing != null) {
            throw new BusinessException(ErrorCode.OPERATION_ERROR, "该自选股已存在");
        }

        // 从品种注册表补全股票名称
        String symbolName = "";
        QueryWrapper metaQw = QueryWrapper.create().where("symbol = ?", symbol).limit(1);
        StockMetadata metadata = stockMetadataMapper.selectOneByQuery(metaQw);
        if (metadata != null && metadata.getStockName() != null) {
            symbolName = metadata.getStockName();
        }

        Watchlist watchlist = new Watchlist();
        watchlist.setSymbol(symbol);
        watchlist.setSymbolName(symbolName);
        watchlist.setGroupName(groupName);
        watchlist.setSortOrder(0);
        watchlistMapper.insert(watchlist);
        return watchlist;
    }

    /**
     * 移除自选股
     *
     * @param symbol   股票代码
     * @param groupName 分组名称
     * @return 是否移除成功
     */
    public boolean remove(String symbol, String groupName) {
        QueryWrapper queryWrapper = QueryWrapper.create()
                .eq(Watchlist::getSymbol, symbol)
                .eq(Watchlist::getGroupName, groupName);
        return watchlistMapper.deleteByQuery(queryWrapper) > 0;
    }

    /**
     * 重新排序自选股
     * <p>
     * 批量更新自选股的排序值。
     *
     * @param items 排序项列表，包含自选股ID和新的排序值
     */
    public void reorder(List<ReorderItem> items) {
        for (ReorderItem item : items) {
            Watchlist watchlist = watchlistMapper.selectOneById(item.getId());
            if (watchlist != null) {
                watchlist.setSortOrder(item.getSortOrder());
                watchlistMapper.update(watchlist);
            }
        }
    }

    /**
     * 排序项
     */
    @Data
    public static class ReorderItem {
        private Long id;
        private Integer sortOrder;
    }

    /**
     * 自选股列表项（含股票名称与最新行情）
     */
    @Data
    public static class WatchlistQuote {
        private Long id;
        /** 股票代码 */
        private String symbol;
        /** 股票名称 */
        private String symbolName;
        /** 分组名称 */
        private String groupName;
        /** 排序值 */
        private Integer sortOrder;
        /** 备注 */
        private String note;
        /** 创建时间 */
        private java.util.Date createdAt;
        /** 更新时间 */
        private java.util.Date updatedAt;
        /** 最新收盘价 */
        private Double close;
        /** 涨跌幅（%） */
        private Double changePct;
        /** 前收盘价 */
        private Double preClose;
        /** 最新交易日 */
        private java.time.LocalDate tradeDate;
    }
}
