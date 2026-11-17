package com.aiep.aihub.domain.hr;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.*;
import com.aiep.aihub.domain.hr.HrFrozenConfig.Dimension;

/** 分数均为百分制；raw字段保留十进制中间精度，正式分不可得时为null。 */
public record HrScoreResult(BusinessStatus businessStatus, Band band, BigDecimal totalScore, BigDecimal referenceScore,
                            BigDecimal rawScore, BigDecimal baseScore, BigDecimal evidenceCoverage, BigDecimal rawCoverage,
                            Map<Dimension,DimensionScore> dimensions, List<HrHardConditionEvaluator.Result> hardConditions,
                            List<String> reasonCodes, String configVersion, String engineVersion, LocalDate asOfDate) {
    public enum BusinessStatus { FILTERED, REVIEW_REQUIRED, SCORED }
    public enum Band { STRONG_RECOMMEND, RECOMMEND, REVIEW, NOT_RECOMMEND }
    public record DimensionScore(BigDecimal score,BigDecimal rawScore,BigDecimal coverage,BigDecimal rawCoverage) {}
    public HrScoreResult { dimensions=Map.copyOf(dimensions); hardConditions=List.copyOf(hardConditions); reasonCodes=List.copyOf(reasonCodes); }
}
