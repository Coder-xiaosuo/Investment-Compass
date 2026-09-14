package com.xiaosuo.investmentcompass.cache;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.xiaosuo.investmentcompass.model.StockKlineBar;
import jakarta.annotation.Resource;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.List;
import java.util.function.Supplier;
import java.util.regex.Pattern;

/**
 * K 线读缓存（Redis，跨语言失效）
 * <p>
 * Python 侧写完 market_data 后会 INCR {@code kline:ver:{code}}，本类读取时把版本戳
 * 拼进数据 key：
 * <pre>
 *   kline:{timeframe}:{symbol}:{limit}:v{version}
 * </pre>
 * 版本号一变即整体失效，旧版本 key 由各自 TTL 自然回收。Python 因此无需知道
 * Java 缓存了什么（含哪些 limit、聚合结果长什么样），只需递增一个计数器。
 * <p>
 * 只缓存 limit 模式：日期区间查询的参数组合近乎无限、命中率极低，不值得缓存。
 */
@Slf4j
@Component
public class KlineCacheService {

    /** 数据 key 前缀 */
    private static final String DATA_KEY_PREFIX = "kline:";

    /** 版本号 key 前缀，与 Python 侧 kline_cache_service 保持一致 */
    private static final String VERSION_KEY_PREFIX = "kline:ver:";

    /**
     * 分钟级 K 线盘中持续变化，TTL 取短值
     */
    private static final Duration TTL_INTRADAY = Duration.ofMinutes(1);

    /**
     * 日线及以上：失效信号是主机制，TTL 仅作兜底（防 Python 侧漏发失效信号）
     */
    private static final Duration TTL_DAILY = Duration.ofMinutes(30);

    private static final TypeReference<List<StockKlineBar>> KLINE_BARS_TYPE = new TypeReference<>() {
    };

    private static final Pattern NON_DIGIT = Pattern.compile("\\D");

    @Resource
    private StringRedisTemplate redis;
    @Resource
    private ObjectMapper objectMapper;



    /**
     * 读缓存，未命中则回源并写入（Cache-Aside）
     * <p>
     * Redis 异常或版本号缺失时退化为直接回源，不影响接口可用性。
     *
     * @param symbol    股票代码（库内形式，如 600519 或 600519.SH）
     * @param timeframe K 线周期
     * @param limit     返回的 K 线数量上限
     * @param loader    缓存未命中时的回源逻辑
     * @return K 线列表
     */
    public List<StockKlineBar> getOrLoad(String symbol, String timeframe, int limit,
                                         Supplier<List<StockKlineBar>> loader) {
        List<StockKlineBar> cached = read(symbol, timeframe, limit);
        if (cached != null) {
            return cached;
        }
        List<StockKlineBar> bars = loader.get();
        write(symbol, timeframe, limit, bars);
        return bars;
    }

    /**
     * 构造数据 key，其中 symbol 用库内原始形式（区分 000001.SZ 与 000001.SH 等），
     * 版本戳则取自按 6 位代码归一化后的版本号 key。
     */
    private String dataKey(String symbol, String timeframe, int limit) {
        return DATA_KEY_PREFIX + timeframe + ":" + symbol + ":" + limit + ":v" + currentVersion(symbol);
    }

    /**
     * 读取标的最新缓存版本号
     * <p>
     * 版本号 key 不存在时按 0 处理：它只增不减且不设 TTL，因此"不存在"只能是
     * Redis 从未写入或已被整体重置——此时同为"数据 key 也一并消失"的状态，
     * 不会出现"旧版本数据仍在、版本号却归零"的错配。
     */
    private long currentVersion(String symbol) {
        String raw = redis.opsForValue().get(VERSION_KEY_PREFIX + codeOf(symbol));
        if (raw == null) {
            return 0L;
        }
        return Long.parseLong(raw);
    }

    /**
     * 取出 6 位代码：Python 侧版本号 key 用不带后缀的代码，
     * 这里必须做同样归一化才能读到同一个 key。
     */
    private String codeOf(String symbol) {
        String digits = NON_DIGIT.matcher(symbol).replaceAll("");
        return digits.length() >= 6 ? digits.substring(digits.length() - 6) : digits;
    }

    private Duration ttl(String timeframe) {
        return "1d".equals(timeframe) || "1w".equals(timeframe) || "1M".equals(timeframe)
                ? TTL_DAILY
                : TTL_INTRADAY;
    }

    private List<StockKlineBar> read(String symbol, String timeframe, int limit) {
        try {
            String json = redis.opsForValue().get(dataKey(symbol, timeframe, limit));
            if (json == null) {
                return null;
            }
            return objectMapper.readValue(json, KLINE_BARS_TYPE);
        } catch (Exception e) {
            log.warn("K 线缓存读取失败，回源数据库 [{} {} limit={}]：{}", symbol, timeframe, limit, e.getMessage());
            return null;
        }
    }

    private void write(String symbol, String timeframe, int limit, List<StockKlineBar> bars) {
        try {
            redis.opsForValue().set(
                    dataKey(symbol, timeframe, limit),
                    objectMapper.writeValueAsString(bars),
                    ttl(timeframe));
        } catch (Exception e) {
            log.warn("K 线缓存写入失败（不影响本次返回）[{} {} limit={}]：{}", symbol, timeframe, limit, e.getMessage());
        }
    }
}
