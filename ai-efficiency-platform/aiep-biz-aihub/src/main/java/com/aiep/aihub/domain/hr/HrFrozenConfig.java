package com.aiep.aihub.domain.hr;

import java.math.BigDecimal;
import java.util.*;

/** 已冻结的五维计分配置；覆盖门槛使用百分数，子项权重使用维内相对值。 */
public record HrFrozenConfig(String version, Map<Dimension,Integer> weights, List<Requirement> requirements,
                             int highThreshold, int middleThreshold, int lowThreshold,
                             BigDecimal minimumCoverage, BigDecimal strongCoverage) {
    public enum Dimension { SKILL, EXPERIENCE, PROJECT, EDUCATION, BONUS }
    public record Requirement(String id, Dimension dimension, BigDecimal weight, boolean critical, boolean applicable) {
        public Requirement {
            Objects.requireNonNull(id); Objects.requireNonNull(dimension); Objects.requireNonNull(weight);
            if (id.isBlank() || weight.signum()<=0) throw new IllegalArgumentException("invalid requirement");
        }
    }
    public HrFrozenConfig {
        Objects.requireNonNull(version); weights=Map.copyOf(weights); requirements=List.copyOf(requirements);
        if (weights.size()!=Dimension.values().length || weights.values().stream().anyMatch(w->w<0||w>100)
                || weights.values().stream().mapToInt(Integer::intValue).sum()!=100) throw new IllegalArgumentException("weights must total 100");
        if (lowThreshold<0 || highThreshold>100 || highThreshold<=middleThreshold || middleThreshold<=lowThreshold)
            throw new IllegalArgumentException("thresholds must strictly descend");
        if (minimumCoverage.compareTo(BigDecimal.valueOf(80))<0 || strongCoverage.compareTo(BigDecimal.valueOf(90))<0
                || minimumCoverage.compareTo(strongCoverage)>0 || strongCoverage.compareTo(BigDecimal.valueOf(100))>0)
            throw new IllegalArgumentException("invalid coverage gates");
        Set<String> ids=new HashSet<>();
        for (Requirement r:requirements) if (!ids.add(r.id())) throw new IllegalArgumentException("duplicate requirement");
        for (Dimension d:Dimension.values()) {
            var items=requirements.stream().filter(r->r.dimension()==d&&r.applicable()).toList();
            if (weights.get(d)>0&&items.isEmpty()) throw new IllegalArgumentException("positive dimension needs requirements");
            if (d==Dimension.BONUS && !items.isEmpty() && items.stream().anyMatch(r->r.weight().compareTo(items.getFirst().weight())!=0))
                throw new IllegalArgumentException("bonus items must have equal weights");
        }
    }
    public static Map<Dimension,Integer> normalizeWeights(Map<Dimension,Integer> weights) {
        if (weights.values().stream().anyMatch(w->w<0)) throw new IllegalArgumentException("negative weight");
        long sum=weights.values().stream().mapToLong(Integer::longValue).sum();
        if (sum==0) throw new IllegalArgumentException("zero weights");
        EnumMap<Dimension,Integer> result=new EnumMap<>(Dimension.class);
        for (Dimension d:Dimension.values()) result.put(d,(int)(100L*weights.getOrDefault(d,0)/sum));
        var order=Arrays.stream(Dimension.values()).sorted(Comparator.<Dimension>comparingLong(d->100L*weights.getOrDefault(d,0)%sum).reversed()).toList();
        int remaining=100-result.values().stream().mapToInt(Integer::intValue).sum();
        for(int i=0;i<remaining;i++) result.merge(order.get(i),1,Integer::sum);
        return Map.copyOf(result);
    }
}
