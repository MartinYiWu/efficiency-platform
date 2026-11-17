package com.aiep.aihub.hr;

import com.aiep.aihub.domain.hr.*;
import com.aiep.aihub.domain.hr.HrFrozenConfig.*;
import com.aiep.aihub.domain.hr.HrAtomicAssessment.Level;
import org.junit.jupiter.api.Test;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class HrScoreEngineTest {
    private static final LocalDate DATE = LocalDate.of(2026, 11, 11);
    private final HrScoreEngine engine = new HrScoreEngine();
    private static BigDecimal n(String value) { return new BigDecimal(value); }
    private static HrFrozenConfig config(List<Requirement> requirements, Map<Dimension,Integer> weights) {
        return new HrFrozenConfig("v1.0", weights, requirements, 80, 65, 50, n("80"), n("90"));
    }
    private static HrAtomicAssessment item(String id, String score) {
        return new HrAtomicAssessment(id, Level.MATCH, n(score), null, List.of("e1"));
    }
    private HrScoreResult score(HrFrozenConfig config, List<HrAtomicAssessment> items) {
        return engine.score(config, new HrVerifiedFacts(List.of(), false), items, Set.of(), DATE);
    }
    private static Map<Dimension,Integer> onlySkill() {
        return Map.of(Dimension.SKILL,100, Dimension.EXPERIENCE,0,Dimension.PROJECT,0,Dimension.EDUCATION,0,Dimension.BONUS,0);
    }
    @Test void computesPublishedExampleWithoutDoubleBonus() {
        List<Requirement> requirements = new ArrayList<>(); List<HrAtomicAssessment> items = new ArrayList<>();
        String[] scores = {"80","90","80","80","100"}; int i=0;
        for (Dimension d : Dimension.values()) { requirements.add(new Requirement(d.name(),d,n("100"),false,true)); items.add(item(d.name(),scores[i++])); }
        var result=score(config(requirements,Map.of(Dimension.SKILL,40,Dimension.EXPERIENCE,25,Dimension.PROJECT,25,Dimension.EDUCATION,5,Dimension.BONUS,5)),items);
        assertEquals(n("83.5"),result.totalScore()); assertEquals(HrScoreResult.Band.STRONG_RECOMMEND,result.band());
        Collections.reverse(items); assertEquals(result,score(config(requirements,Map.of(Dimension.SKILL,40,Dimension.EXPERIENCE,25,Dimension.PROJECT,25,Dimension.EDUCATION,5,Dimension.BONUS,5)),items));
    }
    @Test void usesRoundedCoverageAndScoreForGates() {
        for (String[] boundary : List.of(new String[]{"79.94","79.9","REVIEW_REQUIRED"},new String[]{"79.95","80.0","SCORED"},new String[]{"89.95","90.0","SCORED"})) {
            var requirements=List.of(new Requirement("known",Dimension.SKILL,n(boundary[0]),false,true),new Requirement("unknown",Dimension.SKILL,n("100").subtract(n(boundary[0])),false,true));
            var result=score(config(requirements,onlySkill()),List.of(item("known","64.95"),new HrAtomicAssessment("unknown",Level.UNKNOWN,null,null,List.of())));
            assertEquals(n(boundary[1]),result.evidenceCoverage()); assertEquals(boundary[2],result.businessStatus().name());
            assertEquals(n("65.0"),result.referenceScore());
        }
    }
    @Test void highScoreRequiresNinetyCoverageAndCriticalKnown() {
        var requirements=List.of(new Requirement("known",Dimension.SKILL,n("85"),false,true),new Requirement("unknown",Dimension.SKILL,n("15"),false,true));
        assertEquals(HrScoreResult.BusinessStatus.REVIEW_REQUIRED,score(config(requirements,onlySkill()),List.of(item("known","100"),new HrAtomicAssessment("unknown",Level.UNKNOWN,null,null,List.of()))).businessStatus());
        requirements=List.of(new Requirement("known",Dimension.SKILL,n("99"),false,true),new Requirement("unknown",Dimension.SKILL,n("1"),true,true));
        assertNull(score(config(requirements,onlySkill()),List.of(item("known","100"),new HrAtomicAssessment("unknown",Level.UNKNOWN,null,null,List.of()))).totalScore());
    }
    @Test void explicitZeroIsKnownButWholeUnknownDimensionCannotBeBypassed() {
        var requirements=List.of(new Requirement("known",Dimension.SKILL,n("100"),false,true));
        var zero=score(config(requirements,onlySkill()),List.of(new HrAtomicAssessment("known",Level.EXPLICIT_NOT_MET,null,null,List.of("e1"))));
        assertEquals(n("0.0"),zero.totalScore()); assertEquals(n("100.0"),zero.evidenceCoverage());
        var unknown=score(config(requirements,onlySkill()),List.of(new HrAtomicAssessment("known",Level.UNKNOWN,null,null,List.of())));
        assertNull(unknown.referenceScore()); assertNull(unknown.dimensions().get(Dimension.SKILL).score());
    }
    @Test void failWinsOverUnknownAndOverrideCapsBand() {
        var c=config(List.of(new Requirement("a",Dimension.SKILL,n("100"),false,true)),onlySkill());
        var fail=new HrHardConditionEvaluator.Result("degree",HrHardConditionEvaluator.Type.EDUCATION,HrHardConditionEvaluator.Status.FAIL,true,"insufficient");
        var facts=new HrVerifiedFacts(List.of(fail),false);
        var filtered=engine.score(c,facts,List.of(item("a","100")),Set.of(),DATE);
        assertEquals(HrScoreResult.BusinessStatus.FILTERED,filtered.businessStatus()); assertNull(filtered.referenceScore()); assertTrue(filtered.dimensions().isEmpty());
        var overridden=engine.score(c,facts,List.of(item("a","100")),Set.of("degree"),DATE);
        assertEquals(HrScoreResult.Band.REVIEW,overridden.band()); assertEquals(n("100.0"),overridden.totalScore());
    }
    @Test void excessExperienceRetainsActualAndBaseScores() {
        var c=config(List.of(new Requirement("a",Dimension.SKILL,n("100"),false,true)),onlySkill());
        var result=score(c,List.of(new HrAtomicAssessment("a",Level.MATCH,n("45"),n("70"),List.of("e1"))));
        assertEquals(HrScoreResult.BusinessStatus.REVIEW_REQUIRED,result.businessStatus()); assertEquals(n("45.0"),result.referenceScore()); assertEquals(n("70.0"),result.baseScore());
        assertTrue(result.reasonCodes().contains("EXPERIENCE_OVERQUALIFICATION_REVIEW"));
    }
    @Test void rejectsInvalidWeightsThresholdsAndUntrustedAssessment() {
        var req=List.of(new Requirement("a",Dimension.SKILL,n("100"),false,true));
        assertThrows(IllegalArgumentException.class,()->config(req,Map.of(Dimension.SKILL,99)));
        assertThrows(IllegalArgumentException.class,()->new HrFrozenConfig("v",onlySkill(),req,65,65,50,n("80"),n("90")));
        assertThrows(IllegalArgumentException.class,()->new HrAtomicAssessment("a",Level.MATCH,null,null,List.of()));
        assertThrows(IllegalArgumentException.class,()->score(config(req,onlySkill()),List.of(item("other","80"))));
    }
    @Test void normalizesByLargestRemainderInFixedDimensionOrder() {
        var normalized=HrFrozenConfig.normalizeWeights(Map.of(Dimension.SKILL,1,Dimension.EXPERIENCE,1,Dimension.PROJECT,1));
        assertEquals(34,normalized.get(Dimension.SKILL));assertEquals(33,normalized.get(Dimension.EXPERIENCE));assertEquals(33,normalized.get(Dimension.PROJECT));
        assertThrows(IllegalArgumentException.class,()->HrFrozenConfig.normalizeWeights(Map.of()));
    }
    @Test void deterministicScaleAndOrdinalScoresFollowFrozenAnchors() {
        assertEquals(n("100"),HrScoreEngine.scaleScore(n("125"),n("100")));
        assertEquals(n("80"),HrScoreEngine.scaleScore(n("100"),n("100")));
        assertEquals(n("50"),HrScoreEngine.scaleScore(n("50"),n("100")));
        assertEquals(n("0"),HrScoreEngine.scaleScore(n("49.9"),n("100")));
        assertNull(HrScoreEngine.scaleScore(null,n("100")));
        assertEquals(n("100"),HrScoreEngine.ordinalScore(4,3));
        assertEquals(n("80"),HrScoreEngine.ordinalScore(3,3));
        assertEquals(n("50"),HrScoreEngine.ordinalScore(2,3));
        assertEquals(n("0"),HrScoreEngine.ordinalScore(1,3));
        assertNull(HrScoreEngine.ordinalScore(null,3));
    }
    @Test void zeroWeightCriticalUnknownStillBlocksAndUnknownBonusDimensionBlocks() {
        var requirements=List.of(new Requirement("known",Dimension.SKILL,n("100"),false,true),new Requirement("critical",Dimension.BONUS,n("1"),true,true));
        var items=List.of(item("known","100"),new HrAtomicAssessment("critical",Level.UNKNOWN,null,null,List.of()));
        assertEquals(HrScoreResult.BusinessStatus.REVIEW_REQUIRED,score(config(requirements,onlySkill()),items).businessStatus());
        var weights=Map.of(Dimension.SKILL,95,Dimension.EXPERIENCE,0,Dimension.PROJECT,0,Dimension.EDUCATION,0,Dimension.BONUS,5);
        var result=score(config(requirements,weights),items);
        assertNull(result.referenceScore());assertEquals(n("95.0"),result.evidenceCoverage());
    }
}
