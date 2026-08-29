package com.xiaosuo.investmentcompass.mapper;

import com.mybatisflex.core.BaseMapper;
import com.xiaosuo.investmentcompass.model.Watchlist;
import org.springframework.stereotype.Repository;

/**
 * 自选表 Mapper
 * <p>
 * 提供自选股记录的数据库访问接口。
 */
@Repository
public interface WatchlistMapper extends BaseMapper<Watchlist> {
}
