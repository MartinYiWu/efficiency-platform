package com.aiep.aihub.hr;

import com.aiep.aihub.domain.hr.*;
import org.junit.jupiter.api.Test;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class HrDateAndHardConditionTest {
    private final HrMonthIntervalCalculator calculator=new HrMonthIntervalCalculator();
    private static HrMonthIntervalCalculator.DateRange exact(int year,int month) { return new HrMonthIntervalCalculator.DateRange(YearMonth.of(year,month),YearMonth.of(year,month)); }
    @Test void countsUnionOfNaturalMonthsAndExcludesInternship() {
        var result=calculator.calculate(List.of(new HrMonthIntervalCalculator.WorkPeriod(exact(2020,1),exact(2020,6),false,false),new HrMonthIntervalCalculator.WorkPeriod(exact(2020,4),exact(2020,12),false,false),new HrMonthIntervalCalculator.WorkPeriod(exact(2019,1),exact(2019,12),false,true)),LocalDate.of(2026,11,11));
        assertEquals(12,result.minMonths()); assertEquals(12,result.maxMonths());
    }
    @Test void uncertainYearsProduceSafeBoundsAndPresentIsCapped() {
        var year2020=new HrMonthIntervalCalculator.DateRange(YearMonth.of(2020,1),YearMonth.of(2020,12));
        var year2021=new HrMonthIntervalCalculator.DateRange(YearMonth.of(2021,1),YearMonth.of(2021,12));
        var result=calculator.calculate(List.of(new HrMonthIntervalCalculator.WorkPeriod(year2020,year2021,false,false)),LocalDate.of(2026,11,11));
        assertEquals(2,result.minMonths()); assertEquals(24,result.maxMonths());
        result=calculator.calculate(List.of(new HrMonthIntervalCalculator.WorkPeriod(exact(2026,10),null,true,false)),LocalDate.of(2026,11,11));
        assertEquals(2,result.minMonths());
    }
    @Test void invalidDatesAndUnknownInternshipRequireReview() {
        assertTrue(calculator.calculate(List.of(new HrMonthIntervalCalculator.WorkPeriod(exact(2022,1),exact(2020,1),false,false)),LocalDate.now()).needsReview());
        assertTrue(calculator.calculate(List.of(new HrMonthIntervalCalculator.WorkPeriod(exact(2020,1),exact(2020,2),false,null)),LocalDate.now()).needsReview());
    }
    @Test void hardThresholdUsesConservativeBoundsAndFlooredTolerance() {
        var e=new HrHardConditionEvaluator();
        assertEquals(HrHardConditionEvaluator.Status.BORDERLINE,e.numeric("years",HrHardConditionEvaluator.Type.WORK_EXPERIENCE,new BigDecimal("60"),new BigDecimal("42"),new BigDecimal("42"),true,false).status());
        assertEquals(HrHardConditionEvaluator.Status.UNKNOWN,e.numeric("years",HrHardConditionEvaluator.Type.WORK_EXPERIENCE,new BigDecimal("60"),new BigDecimal("30"),new BigDecimal("70"),false,false).status());
        assertEquals(HrHardConditionEvaluator.Status.FAIL,e.numeric("degree",HrHardConditionEvaluator.Type.EDUCATION,new BigDecimal("4"),new BigDecimal("2"),new BigDecimal("2"),true,false).status());
    }
    @Test void allAnyKeepUnknownDistinctFromFailureAndForbidSkillOverride() {
        var e=new HrHardConditionEvaluator();
        assertEquals(HrHardConditionEvaluator.Status.UNKNOWN,e.combine("skill",HrHardConditionEvaluator.Type.REQUIRED_SKILL,HrHardConditionEvaluator.MatchMode.ANY,List.of(HrHardConditionEvaluator.Status.FAIL,HrHardConditionEvaluator.Status.UNKNOWN)).status());
        assertEquals(HrHardConditionEvaluator.Status.FAIL,e.combine("skill",HrHardConditionEvaluator.Type.REQUIRED_SKILL,HrHardConditionEvaluator.MatchMode.ALL,List.of(HrHardConditionEvaluator.Status.FAIL,HrHardConditionEvaluator.Status.UNKNOWN)).status());
        assertFalse(e.combine("skill",HrHardConditionEvaluator.Type.REQUIRED_SKILL,HrHardConditionEvaluator.MatchMode.ALL,List.of(HrHardConditionEvaluator.Status.FAIL)).overrideAllowed());
    }
    @Test void experienceIntervalChecksInteriorPeakAndFloor() {
        var range=HrScoreEngine.experienceScore(24,120,36,60);
        assertEquals(new BigDecimal("60.0"),range.minimum()); assertEquals(new BigDecimal("100.0"),range.maximum()); assertNull(range.uniqueScore());
        assertEquals(new BigDecimal("100.0"),HrScoreEngine.experienceScore(36,60,36,60).uniqueScore());
        assertThrows(IllegalArgumentException.class,()->HrScoreEngine.experienceScore(0,12,0,60));
    }
    @Test void metricToleranceUsesFrozenDecimalPrecision() {
        var e=new HrHardConditionEvaluator();
        assertEquals(HrHardConditionEvaluator.Status.BORDERLINE,e.numeric("scale",HrHardConditionEvaluator.Type.PROJECT_SCALE,new BigDecimal("10.5"),new BigDecimal("7.4"),new BigDecimal("7.4"),true,false,1).status());
        assertEquals(HrHardConditionEvaluator.Status.FAIL,e.numeric("scale",HrHardConditionEvaluator.Type.PROJECT_SCALE,new BigDecimal("10.5"),new BigDecimal("7.3"),new BigDecimal("7.3"),true,false,1).status());
    }
}
