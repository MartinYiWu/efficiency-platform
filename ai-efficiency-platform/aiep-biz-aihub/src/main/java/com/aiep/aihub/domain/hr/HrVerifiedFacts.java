package com.aiep.aihub.domain.hr;

import java.util.List;

/** 事实核验产物，硬条件判断不因软分或人工放行被改写。 */
public record HrVerifiedFacts(List<HrHardConditionEvaluator.Result> hardConditions, boolean evidenceConflict) {
    public HrVerifiedFacts { hardConditions=List.copyOf(hardConditions); }
}
