package com.xiaosuo.investmentcompass.mapper;

import com.mybatisflex.core.BaseMapper;
import com.xiaosuo.investmentcompass.model.StockMetadata;
import org.springframework.stereotype.Repository;

/**
 * 品种注册表 Mapper
 * <p>
 * 提供股票/ETF/指数品种元数据的数据库访问接口。
 */
@Repository
public interface StockMetadataMapper extends BaseMapper<StockMetadata> {

}
