package com.aiep.aihub.domain.hr;

import java.math.*;
import java.time.LocalDate;
import java.util.*;
import com.aiep.aihub.domain.hr.HrFrozenConfig.*;
import com.aiep.aihub.domain.hr.HrScoreResult.*;
import com.aiep.aihub.domain.hr.HrHardConditionEvaluator.Status;

/** hr-score/1，所有门禁仅比较HALF_UP一位后的展示值，不访问外部状态。 */
public final class HrScoreEngine {
    private static final BigDecimal HUNDRED=BigDecimal.valueOf(100);
    private static final int SCALE=18;
    public HrScoreResult score(HrFrozenConfig config,HrVerifiedFacts facts,List<HrAtomicAssessment> assessments,
                               Set<String> overriddenConditionIds,LocalDate asOfDate) {
        Objects.requireNonNull(asOfDate);
        Map<String,HrAtomicAssessment> byId=new HashMap<>();
        for(var assessment:assessments) if(byId.put(assessment.requirementId(),assessment)!=null) throw new IllegalArgumentException("duplicate assessment");
        Set<String> ids=new HashSet<>(); for(var r:config.requirements()) ids.add(r.id());
        if(!ids.equals(byId.keySet())) throw new IllegalArgumentException("assessment set must match requirements");
        List<HrHardConditionEvaluator.Result> conditions=new ArrayList<>();
        Set<String> acceptedOverrides=new HashSet<>();
        for(var condition:facts.hardConditions()) {
            if(condition.status()==Status.OVERRIDDEN) throw new IllegalArgumentException("override must reference original failure");
            if(!overriddenConditionIds.contains(condition.id())) { conditions.add(condition);continue; }
            if(!condition.overrideAllowed()||condition.status()!=Status.FAIL) throw new IllegalArgumentException("invalid override");
            acceptedOverrides.add(condition.id());
            conditions.add(new HrHardConditionEvaluator.Result(condition.id(),condition.type(),Status.OVERRIDDEN,true,condition.reasonCode()));
        }
        if(!acceptedOverrides.equals(overriddenConditionIds)) throw new IllegalArgumentException("unknown override");
        if(conditions.stream().anyMatch(c->c.status()==Status.FAIL))
            return result(config,asOfDate,BusinessStatus.FILTERED,null,null,null,null,null,null,Map.of(),conditions,List.of("HARD_CONDITION_FAILED"));
        Map<Dimension,DimensionScore> dimensions=new EnumMap<>(Dimension.class);
        BigDecimal total=BigDecimal.ZERO,base=BigDecimal.ZERO,coverage=BigDecimal.ZERO;
        boolean emptyDimension=false,criticalUnknown=false,conflict=facts.evidenceConflict();
        for(Dimension dimension:Dimension.values()) {
            BigDecimal allWeight=BigDecimal.ZERO,knownWeight=BigDecimal.ZERO,sum=BigDecimal.ZERO,baseSum=BigDecimal.ZERO;
            for(var requirement:config.requirements()) {
                if(requirement.dimension()!=dimension) continue;
                var assessment=byId.get(requirement.id());
                if(!requirement.applicable()) continue;
                if(assessment.level()==HrAtomicAssessment.Level.NOT_APPLICABLE) throw new IllegalArgumentException("applicable requirement cannot be removed");
                BigDecimal value=assessment.effectiveScore();
                allWeight=allWeight.add(requirement.weight());
                if(value==null) { criticalUnknown|=requirement.critical();conflict|=assessment.level()==HrAtomicAssessment.Level.NEEDS_REVIEW;continue; }
                knownWeight=knownWeight.add(requirement.weight());sum=sum.add(requirement.weight().multiply(value));
                baseSum=baseSum.add(requirement.weight().multiply(assessment.baseScore()==null?value:assessment.baseScore()));
            }
            BigDecimal raw=knownWeight.signum()==0?null:divide(sum,knownWeight);
            BigDecimal rawCoverage=allWeight.signum()==0?null:divide(knownWeight.multiply(HUNDRED),allWeight);
            dimensions.put(dimension,new DimensionScore(round(raw),raw,round(rawCoverage),rawCoverage));
            BigDecimal weight=BigDecimal.valueOf(config.weights().get(dimension));
            if(weight.signum()==0) continue;
            if(raw==null) emptyDimension=true;
            else { total=total.add(weight.multiply(raw));base=base.add(weight.multiply(divide(baseSum,knownWeight))); }
            coverage=coverage.add(weight.multiply(rawCoverage==null?BigDecimal.ZERO:rawCoverage));
        }
        BigDecimal rawTotal=emptyDimension?null:divide(total,HUNDRED),rounded=round(rawTotal),roundedBase=emptyDimension?null:round(divide(base,HUNDRED));
        BigDecimal rawCoverage=divide(coverage,HUNDRED),roundedCoverage=round(rawCoverage);
        List<String> reasons=new ArrayList<>();
        if(conditions.stream().anyMatch(c->c.status()==Status.UNKNOWN||c.status()==Status.NEEDS_REVIEW)) reasons.add("HARD_CONDITION_UNVERIFIED");
        if(criticalUnknown) reasons.add("CRITICAL_REQUIREMENT_UNKNOWN");
        if(conflict) reasons.add("EVIDENCE_CONFLICT");
        if(emptyDimension) reasons.add("DIMENSION_UNKNOWN");
        if(roundedCoverage.compareTo(config.minimumCoverage())<0) reasons.add("INSUFFICIENT_COVERAGE");
        if(rounded!=null&&rounded.compareTo(BigDecimal.valueOf(config.highThreshold()))>=0&&roundedCoverage.compareTo(config.strongCoverage())<0) reasons.add("STRONG_COVERAGE_REQUIRED");
        if(rounded!=null&&rounded.compareTo(BigDecimal.valueOf(config.lowThreshold()))<0&&roundedBase.compareTo(BigDecimal.valueOf(config.lowThreshold()))>=0) reasons.add("EXPERIENCE_OVERQUALIFICATION_REVIEW");
        if(!reasons.isEmpty()) return result(config,asOfDate,BusinessStatus.REVIEW_REQUIRED,null,null,rounded,rawTotal,roundedBase,roundedCoverage,dimensions,conditions,reasons,rawCoverage);
        Band band=rounded.compareTo(BigDecimal.valueOf(config.highThreshold()))>=0?Band.STRONG_RECOMMEND:
                rounded.compareTo(BigDecimal.valueOf(config.middleThreshold()))>=0?Band.RECOMMEND:
                rounded.compareTo(BigDecimal.valueOf(config.lowThreshold()))>=0?Band.REVIEW:Band.NOT_RECOMMEND;
        if(!acceptedOverrides.isEmpty()) { if(band==Band.STRONG_RECOMMEND||band==Band.RECOMMEND) band=Band.REVIEW;reasons.add("MANUALLY_OVERRIDDEN"); }
        return result(config,asOfDate,BusinessStatus.SCORED,band,rounded,rounded,rawTotal,roundedBase,roundedCoverage,dimensions,conditions,reasons,rawCoverage);
    }
    private HrScoreResult result(HrFrozenConfig config,LocalDate date,BusinessStatus status,Band band,BigDecimal total,BigDecimal reference,
                                 BigDecimal raw,BigDecimal base,BigDecimal coverage,Map<Dimension,DimensionScore> dimensions,
                                 List<HrHardConditionEvaluator.Result> conditions,List<String> reasons,BigDecimal... rawCoverage) {
        return new HrScoreResult(status,band,total,reference,raw,base,coverage,rawCoverage.length==0?null:rawCoverage[0],dimensions,conditions,reasons,config.version(),"hr-score/1",date);
    }
    private static BigDecimal divide(BigDecimal numerator,BigDecimal denominator) { return numerator.divide(denominator,SCALE,RoundingMode.HALF_UP); }
    private static BigDecimal round(BigDecimal value) { return value==null?null:value.setScale(1,RoundingMode.HALF_UP); }
    public record ExperienceScore(BigDecimal minimum,BigDecimal maximum,BigDecimal uniqueScore) {}
    public static BigDecimal scaleScore(BigDecimal actual,BigDecimal expected) {
        if(expected==null||expected.signum()<=0) throw new IllegalArgumentException("positive scale expected");
        if(actual==null) return null;
        if(actual.signum()<0) throw new IllegalArgumentException("negative scale");
        if(actual.compareTo(expected.multiply(new BigDecimal("1.25")))>=0) return HUNDRED;
        if(actual.compareTo(expected)>=0) return BigDecimal.valueOf(80);
        return actual.compareTo(expected.multiply(new BigDecimal("0.5")))>=0?BigDecimal.valueOf(50):BigDecimal.ZERO;
    }
    public static BigDecimal ordinalScore(Integer actual,int expected) {
        if(expected<=0) throw new IllegalArgumentException("positive ordinal expected");
        if(actual==null) return null;
        if(actual<=0) throw new IllegalArgumentException("positive ordinal actual");
        if(actual>expected) return HUNDRED;
        if(actual==expected) return BigDecimal.valueOf(80);
        return actual==expected-1?BigDecimal.valueOf(50):BigDecimal.ZERO;
    }
    public static ExperienceScore experienceScore(long minimumMonths,long maximumMonths,long lower,long upper) {
        if(minimumMonths<0||minimumMonths>maximumMonths||lower<=0||upper<lower) throw new IllegalArgumentException("invalid experience interval");
        List<BigDecimal> scores=new ArrayList<>(List.of(experienceAt(minimumMonths,lower,upper),experienceAt(maximumMonths,lower,upper)));
        if(lower>=minimumMonths&&lower<=maximumMonths) scores.add(HUNDRED);
        if(upper>=minimumMonths&&upper<=maximumMonths) scores.add(HUNDRED);
        BigDecimal min=round(Collections.min(scores)),max=round(Collections.max(scores));
        return new ExperienceScore(min,max,min.compareTo(max)==0?min:null);
    }
    private static BigDecimal experienceAt(long months,long lower,long upper) {
        if(months<lower) return divide(HUNDRED.multiply(BigDecimal.valueOf(months)),BigDecimal.valueOf(lower));
        if(months<=upper) return HUNDRED;
        return HUNDRED.subtract(divide(BigDecimal.valueOf(months-upper).multiply(BigDecimal.valueOf(8)),BigDecimal.valueOf(12))).max(BigDecimal.valueOf(60));
    }
}
