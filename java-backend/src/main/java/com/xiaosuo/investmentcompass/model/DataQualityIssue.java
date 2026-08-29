package com.xiaosuo.investmentcompass.model;

import com.mybatisflex.annotation.Column;
import com.mybatisflex.annotation.Id;
import com.mybatisflex.annotation.KeyType;
import com.mybatisflex.annotation.Table;
import lombok.Data;

import java.time.LocalDate;
import java.time.LocalDateTime;

@Data
@Table("data_quality_issue")
public class DataQualityIssue {

    @Id(keyType = KeyType.Auto)
    private Long id;

    private String symbol;

    private String issueType;

    private LocalDate tradeDate;

    private String severity;

    private String description;

    private String dataBefore;

    private String dataAfter;

    private String status;

    private LocalDateTime scanTime;

    private LocalDateTime fixTime;

    private String fixBy;

    private Integer retryCount;

    @Column(onInsertValue = "NOW()")
    private LocalDateTime createdAt;

    @Column(onInsertValue = "NOW()", onUpdateValue = "NOW()")
    private LocalDateTime updatedAt;
}
