package com.aiep.aihub.domain.hr;

import java.math.BigDecimal;
import java.util.*;

/** 已验证原子判断；确定性分数可覆盖语义映射，baseScore仅保留取消超年限扣分的结果。 */
public record HrAtomicAssessment(String requirementId, Level level, BigDecimal score, BigDecimal baseScore, List<String> evidenceIds) {
    public enum Level { STRONG_MATCH, MATCH, PARTIAL_MATCH, EXPLICIT_NOT_MET, UNKNOWN, NEEDS_REVIEW, NOT_APPLICABLE }
    public HrAtomicAssessment {
        Objects.requireNonNull(requirementId); Objects.requireNonNull(level); evidenceIds=List.copyOf(evidenceIds);
        boolean known=level==Level.STRONG_MATCH||level==Level.MATCH||level==Level.PARTIAL_MATCH||level==Level.EXPLICIT_NOT_MET;
        if (evidenceIds.size()>5 || known&&evidenceIds.isEmpty()) throw new IllegalArgumentException("known assessment needs evidence");
        if (!known&&(score!=null||baseScore!=null)) throw new IllegalArgumentException("unknown score must be null");
        for(BigDecimal value:new BigDecimal[]{score,baseScore}) if(value!=null&&(value.signum()<0||value.compareTo(BigDecimal.valueOf(100))>0)) throw new IllegalArgumentException("score outside range");
        if (baseScore!=null&&score!=null&&baseScore.compareTo(score)<0) throw new IllegalArgumentException("base below score");
    }
    public BigDecimal effectiveScore() {
        if(score!=null) return score;
        return switch(level) { case STRONG_MATCH->BigDecimal.valueOf(100); case MATCH->BigDecimal.valueOf(80); case PARTIAL_MATCH->BigDecimal.valueOf(50); case EXPLICIT_NOT_MET->BigDecimal.ZERO; default->null; };
    }
}
