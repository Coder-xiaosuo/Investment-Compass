package com.xiaosuo.investmentcompass.model;

import com.mybatisflex.annotation.Column;
import com.mybatisflex.annotation.Id;
import com.mybatisflex.annotation.KeyType;
import com.mybatisflex.annotation.Table;
import lombok.Data;

import java.util.Date;

/**
 * 自选股实体
 * <p>
 * 对应数据库 watchlist 表，记录用户关注的自选股信息。
 * 支持分组管理和自定义排序。
 */
@Data
@Table("watchlist")
public class Watchlist {

    /** 主键ID */
    @Id(keyType = KeyType.Auto)
    private Long id;

    /** 股票代码 */
    private String symbol;

    /** 股票名称 */
    private String symbolName;

    /** 分组名称 */
    private String groupName;

    /** 排序值，升序排列 */
    private Integer sortOrder;

    /** 备注 */
    private String note;

    /** 创建时间 */
    @Column(onInsertValue = "NOW()")
    private Date createdAt;

    /** 更新时间 */
    @Column(onInsertValue = "NOW()", onUpdateValue = "NOW()")
    private Date updatedAt;
}
