package com.xiaosuo.investmentcompass.service;

import com.mybatisflex.core.query.QueryWrapper;
import com.xiaosuo.investmentcompass.mapper.MarketDataMapper;
import com.xiaosuo.investmentcompass.mapper.StockMetadataMapper;
import com.xiaosuo.investmentcompass.model.MarketData;
import com.xiaosuo.investmentcompass.model.MarketIndex;
import com.xiaosuo.investmentcompass.model.StockMetadata;
import com.xiaosuo.investmentcompass.model.StockQuote;
import org.springframework.stereotype.Service;

import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * 大盘行情看板服务
 * <p>
 * 提供主要指数行情查询和个股涨跌幅排名服务。
 */
@Service
public class MarketBoardService {

    /** 主要指数代码列表：上证指数、深证成指、创业板指、科创50 */
    private static final List<String> INDEX_SYMBOLS = Arrays.asList("000001", "399001", "399006", "000688");

    private final MarketDataMapper marketDataMapper;

    private final StockMetadataMapper stockMetadataMapper;

    public MarketBoardService(MarketDataMapper marketDataMapper, StockMetadataMapper stockMetadataMapper) {
        this.marketDataMapper = marketDataMapper;
        this.stockMetadataMapper = stockMetadataMapper;
    }

    /**
     * 获取主要指数行情
     * <p>
     * 查询四大指数的最新日线数据，补充指数名称后返回。
     *
     * @return 指数行情列表，包含收盘价、涨跌幅和交易日期
     */
    public List<MarketIndex> getIndices() {
        List<MarketData> list = marketDataMapper.selectLatestQuote(INDEX_SYMBOLS);

        QueryWrapper metaQuery = QueryWrapper.create()
                .where("symbol IN (?, ?, ?, ?)",
                        INDEX_SYMBOLS.get(0), INDEX_SYMBOLS.get(1),
                        INDEX_SYMBOLS.get(2), INDEX_SYMBOLS.get(3));
        List<StockMetadata> metas = stockMetadataMapper.selectListByQuery(metaQuery);
        Map<String, String> nameMap = metas.stream()
                .collect(Collectors.toMap(StockMetadata::getSymbol, StockMetadata::getStockName, (a, b) -> a));

        nameMap.putIfAbsent("000001", "上证指数");
        nameMap.putIfAbsent("399001", "深证成指");
        nameMap.putIfAbsent("399006", "创业板指");
        nameMap.putIfAbsent("000688", "科创50");

        return list.stream().map(md -> {
            MarketIndex idx = new MarketIndex();
            idx.setSymbol(md.getSymbol());
            idx.setStockName(nameMap.get(md.getSymbol()));
            idx.setClose(md.getClose());
            idx.setChangePct(md.getPctChg());
            idx.setTradeDate(md.getTradeDate() != null ? md.getTradeDate().toString() : null);
            return idx;
        }).collect(Collectors.toList());
    }

    /**
     * 获取涨跌幅排名
     * <p>
     * 查询最新交易日的数据，按涨跌幅排序返回涨幅榜或跌幅榜。
     *
     * @param type  排名类型：top_gainers（涨幅榜）/ top_losers（跌幅榜）
     * @param limit 返回数量上限
     * @return 涨跌幅排名列表
     */
    public List<StockQuote> getRanking(String type, int limit) {
        boolean ascending = "top_losers".equals(type);

        QueryWrapper dateQuery = QueryWrapper.create()
                .select("trade_date")
                .from("market_data")
                .where("timeframe = ?", "1d")
                .orderBy("trade_date", false)
                .limit(1);
        MarketData latest = marketDataMapper.selectOneByQuery(dateQuery);
        if (latest == null || latest.getTradeDate() == null) {
            return List.of();
        }

        QueryWrapper rankingQuery = QueryWrapper.create()
                .select("*")
                .from("market_data")
                .where("trade_date = ?", latest.getTradeDate())
                .and("timeframe = ?", "1d")
                .and("pct_chg IS NOT NULL")
                .orderBy("pct_chg", ascending)
                .limit(limit);

        List<MarketData> list = marketDataMapper.selectListByQuery(rankingQuery);

        return list.stream().map(item -> {
            Double pct = item.getPctChg();
            Double close = item.getClose();
            Double preClose = (pct != null && close != null)
                    ? close / (1 + pct / 100)
                    : close;
            return new StockQuote(
                    item.getSymbol(),
                    item.getTradeDate(),
                    close,
                    pct,
                    preClose);
        }).collect(Collectors.toList());
    }
}
