package com.xiaosuo.investmentcompass.service;

import com.mybatisflex.core.query.QueryWrapper;
import com.xiaosuo.investmentcompass.cache.KlineCacheService;
import com.xiaosuo.investmentcompass.cache.StockMetadataCache;
import com.xiaosuo.investmentcompass.exception.ErrorCode;
import com.xiaosuo.investmentcompass.exception.ThrowUtils;
import com.xiaosuo.investmentcompass.mapper.MarketDataMapper;
import com.xiaosuo.investmentcompass.mapper.MonitorMapper;
import com.xiaosuo.investmentcompass.mapper.StockMetadataMapper;
import com.xiaosuo.investmentcompass.model.*;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;

import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.temporal.WeekFields;
import java.util.AbstractMap;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

/**
 * 股票数据服务
 * <p>
 * 提供股票搜索、实时行情查询、K线历史数据查询等核心数据服务。
 */
@Service
public class StockService {

    @Resource
    private StockMetadataMapper stockMetadataMapper;

    @Resource
    private MarketDataMapper marketDataMapper;

    @Resource
    private MonitorMapper monitorMapper;

    @Resource
    private IndicatorService indicatorService;

    @Resource
    private StockMetadataCache stockMetadataCache;

    @Resource
    private KlineCacheService klineCacheService;

    /**
     * 搜索股票
     * <p>
     * 基于本地缓存的整表快照做内存匹配（等价于原 symbol/stock_name 的左模糊 LIKE），
     * 避免每次请求回库全表扫描。
     *
     * @param keyword 搜索关键词
     * @param limit   返回结果数量上限
     * @return 搜索结果列表
     */
    public List<StockSearchItem> searchStocks(String keyword, Integer limit) {
        ThrowUtils.throwIf(keyword == null || keyword.isBlank(), ErrorCode.PARAMS_ERROR, "关键词不能为空");

        if (limit == null || limit <= 0) {
            limit = 10;
        }

        String lowerKeyword = keyword.toLowerCase(Locale.ROOT);

        return stockMetadataCache.getAll().stream()
                .filter(item -> containsIgnoreCase(item.getSymbol(), lowerKeyword)
                        || containsIgnoreCase(item.getStockName(), lowerKeyword))
                .limit(limit)
                .map(item -> new StockSearchItem(
                        item.getSymbol(),
                        item.getStockName()))
                .collect(Collectors.toList());
    }

    /**
     * 大小写不敏感的子串匹配（对齐 utf8mb4_0900_ai_ci 的 LIKE 行为）
     */
    private static boolean containsIgnoreCase(String value, String lowerKeyword) {
        return value != null && value.toLowerCase(Locale.ROOT).contains(lowerKeyword);
    }

    /**
     * 获取指定股票的最新行情
     * <p>
     * 查询每个股票最新的日K线数据，并计算前收盘价。
     *
     * @param symbols 股票代码列表
     * @return 最新行情列表，包含收盘价、涨跌幅、前收盘价
     */
    public List<StockQuote> getLatestQuote(List<String> symbols) {
        ThrowUtils.throwIf(symbols == null || symbols.isEmpty(), ErrorCode.PARAMS_ERROR, "股票代码不能为空");

        List<MarketData> list = marketDataMapper.selectLatestQuote(symbols);

        return list.stream()
                .map(item -> {
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
                })
                .collect(Collectors.toList());
    }

    /**
     * 补全股票代码后缀
     * <p>
     * 若 symbol 不含交易所后缀，则从本地缓存的品种快照中按前缀查找补全。
     */
    private String resolveSymbol(String symbol) {
        if (symbol.contains(".")) {
            return symbol;
        }
        String resolved = stockMetadataCache.findSymbolByPrefix(symbol);
        return resolved != null ? resolved : symbol;
    }

    /**
     * 获取K线历史数据（支持日期范围）
     * <p>
     * 查询指定股票在指定周期下的K线数据，按日期升序返回。
     * 日期范围优先于 limit；若同时提供 start_date/end_date 则忽略 limit。
     * 支持不带交易所后缀的股票代码（自动补全）。
     *
     * @param symbol    股票代码，可带或不带交易所后缀
     * @param timeframe K线周期（1m/5m/15m/30m/1h/4h/1d）
     * @param startDate 开始日期（可选），与 endDate 同时提供时忽略 limit
     * @param endDate   结束日期（可选），与 startDate 同时提供时忽略 limit
     * @param limit     返回的K线数量上限，默认120
     * @return K线响应数据，包含股票代码、周期和K线列表
     */
    public StockKlineResponse getKlineHistory(String symbol, String timeframe,
                                               LocalDate startDate, LocalDate endDate, Integer limit) {
        ThrowUtils.throwIf(symbol == null || symbol.isBlank(), ErrorCode.PARAMS_ERROR, "股票代码不能为空");
        ThrowUtils.throwIf(timeframe == null || timeframe.isBlank(), ErrorCode.PARAMS_ERROR, "时间周期不能为空");

        symbol = resolveSymbol(symbol);

        if (limit == null || limit <= 0) {
            limit = 120;
        }

        final String resolved = symbol;
        final int barsLimit = limit;

        List<StockKlineBar> bars;
        if (startDate != null && endDate != null) {
            // 日期区间组合近乎无限、命中率极低，直接穿透
            bars = loadBars(resolved, timeframe, startDate, endDate, barsLimit);
        } else {
            // limit 模式是热点路径，走 Cache-Aside（Redis，Python 写库后版本号递增失效）
            bars = klineCacheService.getOrLoad(resolved, timeframe, barsLimit,
                    () -> loadBars(resolved, timeframe, null, null, barsLimit));
        }

        return new StockKlineResponse(resolved, timeframe, bars);
    }

    /**
     * 从数据库加载 K 线（含周线/月线聚合）
     *
     * @param symbol    股票代码，含交易所后缀
     * @param timeframe K 线周期
     * @param startDate 开始日期，与 endDate 同时为空时按 limit 截取
     * @param endDate   结束日期
     * @param limit     返回的 K 线数量上限
     * @return 按日期升序的 K 线列表
     */
    private List<StockKlineBar> loadBars(String symbol, String timeframe,
                                          LocalDate startDate, LocalDate endDate, int limit) {
        // 判断是否走聚合（周线/月线从日线聚合）
        boolean isAggregated = "1w".equals(timeframe) || "1M".equals(timeframe);
        String queryTimeframe = isAggregated ? "1d" : timeframe;

        QueryWrapper queryWrapper = QueryWrapper.create()
                .where("symbol = ?", symbol)
                .and("timeframe = ?", queryTimeframe);

        boolean hasDateRange = startDate != null && endDate != null;
        if (hasDateRange) {
            queryWrapper.and("trade_date >= ?", startDate)
                    .and("trade_date <= ?", endDate);
        }

        queryWrapper.orderBy("trade_date", false);

        if (!hasDateRange) {
            // 聚合场景需要更多数据，weekly/monthly 从 1d 聚合，放大 limit
            queryWrapper.limit(isAggregated ? limit * 5 : limit); // 5倍数据确保足够日线用于聚合
        }

        List<MarketData> list = marketDataMapper.selectListByQuery(queryWrapper);
        Collections.reverse(list); // 转为升序（聚合需要升序数据）

        if (isAggregated) {
            if (list.isEmpty()) {
                return Collections.emptyList();
            }
            List<StockKlineBar> aggregated = "1w".equals(timeframe)
                    ? aggregateWeekly(list)
                    : aggregateMonthly(list);
            // 聚合后按 limit 裁剪（复制为独立列表，避免持有大数组的 subList 视图）
            if (aggregated.size() > limit) {
                return new ArrayList<>(aggregated.subList(aggregated.size() - limit, aggregated.size()));
            }
            return aggregated;
        }

        return list.stream()
                .map(item -> {
                    Double volumeRatio = null;
                    Double turnoverRate = null;
                    if (item.getVolume() != null && item.getAmount() != null && item.getAmount() > 0) {
                        turnoverRate = item.getAmount() / 100000000; // 简易估算
                        volumeRatio = 1.0; // 暂缺真实量比数据
                    }
                    return new StockKlineBar(
                            item.getTradeDate(),
                            item.getTsOpen(),
                            item.getOpen(),
                            item.getHigh(),
                            item.getLow(),
                            item.getClose(),
                            item.getVolume(),
                            item.getAmount(),
                            item.getPctChg(),
                            item.getClosed(),
                            volumeRatio,
                            turnoverRate);
                })
                .collect(Collectors.toList());
    }

    /**
     * 将日线数据聚合成周线
     * <p>
     * 按 ISO 周（周一开始）分组，计算每周的开高低收、成交量、成交额和涨跌幅。
     */
    private List<StockKlineBar> aggregateWeekly(List<MarketData> dailyBars) {
        if (dailyBars == null || dailyBars.isEmpty()) return Collections.emptyList();

        WeekFields weekFields = WeekFields.of(DayOfWeek.MONDAY, 1);

        Map<AbstractMap.SimpleEntry<Integer, Integer>, List<MarketData>> grouped = dailyBars.stream()
                .collect(Collectors.groupingBy(
                        bar -> {
                            int year = bar.getTradeDate().get(weekFields.weekBasedYear());
                            int week = bar.getTradeDate().get(weekFields.weekOfWeekBasedYear());
                            return new AbstractMap.SimpleEntry<>(year, week);
                        },
                        LinkedHashMap::new,
                        Collectors.toList()
                ));

        List<StockKlineBar> result = new ArrayList<>();
        for (Map.Entry<AbstractMap.SimpleEntry<Integer, Integer>, List<MarketData>> entry : grouped.entrySet()) {
            List<MarketData> group = entry.getValue();
            MarketData first = group.get(0);
            MarketData last = group.get(group.size() - 1);

            double open = first.getOpen();
            double high = group.stream().mapToDouble(b -> b.getHigh()).max().orElse(0);
            double low = group.stream().mapToDouble(b -> b.getLow()).min().orElse(0);
            double close = last.getClose();
            long volume = group.stream().mapToLong(b -> b.getVolume() != null ? b.getVolume() : 0L).sum();
            double amount = group.stream().mapToDouble(b -> b.getAmount() != null ? b.getAmount() : 0.0).sum();
            double pctChg = first.getOpen() != null && first.getOpen() != 0
                    ? ((close / first.getOpen()) - 1) * 100
                    : 0.0;

            result.add(new StockKlineBar(
                    last.getTradeDate(),
                    first.getTsOpen(),
                    open,
                    high,
                    low,
                    close,
                    volume,
                    amount,
                    pctChg,
                    1,  // closed
                    null, // volumeRatio
                    null  // turnoverRate
            ));
        }
        return result;
    }

    /**
     * 将日线数据聚合成月线
     * <p>
     * 按 YearMonth 分组，计算每月的开高低收、成交量、成交额和涨跌幅。
     */
    private List<StockKlineBar> aggregateMonthly(List<MarketData> dailyBars) {
        if (dailyBars == null || dailyBars.isEmpty()) return Collections.emptyList();

        Map<YearMonth, List<MarketData>> grouped = dailyBars.stream()
                .collect(Collectors.groupingBy(
                        bar -> YearMonth.from(bar.getTradeDate()),
                        LinkedHashMap::new,
                        Collectors.toList()
                ));

        List<StockKlineBar> result = new ArrayList<>();
        for (Map.Entry<YearMonth, List<MarketData>> entry : grouped.entrySet()) {
            List<MarketData> group = entry.getValue();
            MarketData first = group.get(0);
            MarketData last = group.get(group.size() - 1);

            double open = first.getOpen();
            double high = group.stream().mapToDouble(b -> b.getHigh()).max().orElse(0);
            double low = group.stream().mapToDouble(b -> b.getLow()).min().orElse(0);
            double close = last.getClose();
            long volume = group.stream().mapToLong(b -> b.getVolume() != null ? b.getVolume() : 0L).sum();
            double amount = group.stream().mapToDouble(b -> b.getAmount() != null ? b.getAmount() : 0.0).sum();
            double pctChg = first.getOpen() != null && first.getOpen() != 0
                    ? ((close / first.getOpen()) - 1) * 100
                    : 0.0;

            result.add(new StockKlineBar(
                    last.getTradeDate(),
                    first.getTsOpen(),
                    open,
                    high,
                    low,
                    close,
                    volume,
                    amount,
                    pctChg,
                    1,
                    null,
                    null
            ));
        }
        return result;
    }

    /**
     * 获取K线历史数据（仅 limit 模式，向后兼容）
     */
    public StockKlineResponse getKlineHistory(String symbol, String timeframe, Integer limit) {
        return getKlineHistory(symbol, timeframe, null, null, limit);
    }

    /**
     * 获取个股详情
     * <p>
     * 聚合 stock_metadata 与 market_data 最新 1d 记录，返回个股详情。
     *
     * @param symbol 股票代码，含交易所后缀
     * @return 个股详情
     */
    public StockDetail getStockDetail(String symbol) {
        ThrowUtils.throwIf(symbol == null || symbol.isBlank(), ErrorCode.PARAMS_ERROR, "股票代码不能为空");

        QueryWrapper qw = QueryWrapper.create().where("symbol = ?", symbol);
        StockMetadata metadata = stockMetadataMapper.selectOneByQuery(qw);
        ThrowUtils.throwIf(metadata == null, ErrorCode.NOT_FOUND_ERROR, "股票不存在");

        MarketData latest = monitorMapper.selectStockLatestBySymbol(symbol);

        QueryWrapper qw2 = QueryWrapper.create()
                .where("symbol = ?", symbol)
                .and("timeframe = ?", "1d")
                .orderBy("trade_date", false)
                .limit(2);
        List<MarketData> lastTwo = marketDataMapper.selectListByQuery(qw2);

        Double change = null;
        Double changePercent = null;
        if (lastTwo != null && lastTwo.size() == 2) {
            Double latestClose = lastTwo.get(0).getClose();
            Double preClose = lastTwo.get(1).getClose();
            if (latestClose != null && preClose != null) {
                change = latestClose - preClose;
                if (preClose != 0) {
                    changePercent = (change / preClose) * 100;
                }
            }
        }

        StockDetail detail = new StockDetail();
        detail.setSymbol(metadata.getSymbol());
        detail.setStockName(metadata.getStockName());
        detail.setIndustry(null);
        detail.setListDate(null);

        if (latest != null) {
            detail.setLatestClose(latest.getClose());
            detail.setLatestOpen(latest.getOpen());
            detail.setLatestHigh(latest.getHigh());
            detail.setLatestLow(latest.getLow());
            detail.setLatestVolume(latest.getVolume());
            detail.setLatestAmount(latest.getAmount());
            detail.setLatestPctChg(latest.getPctChg());
            detail.setLatestTradeDate(latest.getTradeDate());
        }

        detail.setChange(change);
        detail.setChangePercent(changePercent);

        return detail;
    }

    /**
     * 获取技术指标
     * <p>
     * 根据 K 线数据计算指定类型的技术指标。
     *
     * @param symbol 股票代码，含交易所后缀
     * @param type   指标类型：ma / ema / macd
     * @param period 指标周期（ma/ema 时使用，为空则使用默认值）
     * @param limit  返回的 K 线数量上限
     * @return 技术指标计算结果
     */
    public IndicatorResult getIndicators(String symbol, String type, Integer period, Integer limit) {
        ThrowUtils.throwIf(symbol == null || symbol.isBlank(), ErrorCode.PARAMS_ERROR, "股票代码不能为空");
        ThrowUtils.throwIf(type == null || type.isBlank(), ErrorCode.PARAMS_ERROR, "指标类型不能为空");

        StockKlineResponse klineResponse = getKlineHistory(symbol, "1d", limit);
        List<StockKlineBar> bars = klineResponse.getBars();

        int size = bars.size();
        double[] closes = new double[size];
        List<LocalDate> tradeDates = new ArrayList<>(size);
        for (int i = 0; i < size; i++) {
            StockKlineBar bar = bars.get(i);
            Double close = bar.getClose();
            closes[i] = close != null ? close : Double.NaN;
            tradeDates.add(bar.getTradeDate());
        }

        IndicatorResult result = new IndicatorResult();
        result.setSymbol(symbol);
        result.setType(type);
        result.setTradeDates(tradeDates);

        if ("ma".equals(type)) {
            if (period == null) {
                period = 20;
            }
            double[] values = indicatorService.ma(closes, period);
            result.setValues(convertToList(values));
        } else if ("ema".equals(type)) {
            if (period == null) {
                period = 12;
            }
            double[] values = indicatorService.ema(closes, period);
            result.setValues(convertToList(values));
        } else if ("macd".equals(type)) {
            Map<String, double[]> macdMap = indicatorService.macd(closes);
            result.setDif(convertToList(macdMap.get("dif")));
            result.setDea(convertToList(macdMap.get("dea")));
            result.setMacd(convertToList(macdMap.get("macd")));
        } else {
            ThrowUtils.throwIf(true, ErrorCode.PARAMS_ERROR, "不支持的指标类型: " + type);
        }

        return result;
    }

    private List<Double> convertToList(double[] arr) {
        List<Double> list = new ArrayList<>(arr.length);
        for (double v : arr) {
            if (Double.isNaN(v)) {
                list.add(null);
            } else {
                list.add(v);
            }
        }
        return list;
    }
}
