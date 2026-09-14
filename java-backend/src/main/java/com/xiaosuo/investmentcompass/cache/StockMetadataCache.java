package com.xiaosuo.investmentcompass.cache;

import com.github.benmanes.caffeine.cache.Caffeine;
import com.github.benmanes.caffeine.cache.LoadingCache;
import com.xiaosuo.investmentcompass.mapper.StockMetadataMapper;
import com.xiaosuo.investmentcompass.model.StockMetadata;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

/**
 * 品种注册表本地缓存
 * <p>
 * stock_metadata 数据量小（数千行）且近乎静态，整体载入内存后，
 * 搜索与代码补全不再回库做全表扫描（原 LIKE '%kw%' 无法走索引）。
 */
@Slf4j
@Component
public class StockMetadataCache {

    /** 整表快照在缓存中的唯一键 */
    private static final String SNAPSHOT_KEY = "stock_snapshot";

    private final LoadingCache<String, List<StockMetadata>> cache;

    public StockMetadataCache(StockMetadataMapper stockMetadataMapper) {
        this.cache = Caffeine.newBuilder()
                .maximumSize(1)
                .refreshAfterWrite(Duration.ofMinutes(5))
                .expireAfterWrite(Duration.ofMinutes(10))
                .build(key -> loadAll(stockMetadataMapper));
    }

    /**
     * 从数据库加载整表快照
     */
    private List<StockMetadata> loadAll(StockMetadataMapper stockMetadataMapper) {
        List<StockMetadata> list = stockMetadataMapper.selectAll();
        log.info("加载 stock_metadata 缓存，共 {} 条", list.size());
        return list;
    }

    /**
     * 获取整表快照（命中缓存，或异步/同步加载）
     *
     * @return 品种元数据列表，加载失败时为空列表
     */
    public List<StockMetadata> getAll() {
        List<StockMetadata> list = cache.get(SNAPSHOT_KEY);
        return list != null ? list : Collections.emptyList();
    }

    /**
     * 按代码前缀查找品种代码（等价于原 symbol LIKE 'code%' LIMIT 1）
     *
     * @param prefix 不带交易所后缀的代码前缀
     * @return 匹配到的完整代码，未匹配返回 null
     */
    public String findSymbolByPrefix(String prefix) {
        if (prefix == null || prefix.isEmpty()) {
            return null;
        }
        String lowerPrefix = prefix.toLowerCase(Locale.ROOT);
        return getAll().stream()
                .map(StockMetadata::getSymbol)
                .filter(symbol -> symbol != null && symbol.toLowerCase(Locale.ROOT).startsWith(lowerPrefix))
                .findFirst()
                .orElse(null);
    }
}
