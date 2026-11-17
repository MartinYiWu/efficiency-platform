package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.api.hr.HrPositionContracts.*;
import com.aiep.aihub.application.hr.HrPositionService;
import com.aiep.aihub.domain.hr.HrFrozenConfig;
import com.aiep.aihub.domain.hr.HrFrozenConfig.Dimension;
import com.aiep.aihub.repository.hr.HrPositionRepository;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;

class HrPositionPublicationTest {
    @Test void released_binding_change_publishes_new_minor_version_without_changing_old_snapshot(){
        var active=new Position("p","t","岗位新名","TECHNOLOGY","d","P7","d-000001","ACTIVE","v1.0","ctx-1","1",Instant.now(),3);when(repository.find("t","p")).thenReturn(active);
        var criteria=List.of(new SemanticCriterion("java","Java","SKILL","使用Java独立交付","架构治理证据","独立交付证据","部分参与证据","明确不满足证据",true));var weak=draft(criteria,raw());var full=new Draft(weak.positionId(),weak.name(),weak.family(),weak.departmentId(),weak.level(),weak.jdText(),weak.lastStep(),raw().freeze(),weak.hardConditions(),weak.criteria(),3);
        var oldBinding=new AssetBinding("1","h1","1","m","s");var newBinding=new AssetBinding("2","h2","1","m","s");var previous=new ConfigVersion("old","p","v1.0","ctx-1",full,"hash","1",Instant.now(),1L,Map.of("hr.requirements.evaluate",oldBinding));when(repository.config("t","p","v1.0")).thenReturn(previous);when(repository.draft("t","p")).thenReturn(full);
        var contexts=mock(com.aiep.aihub.application.hr.HrContextService.class);when(contexts.freeze(eq(actor),any())).thenReturn("ctx-1");when(contexts.get(actor,"p","ctx-1")).thenReturn(new com.aiep.aihub.application.hr.HrContextService.Context("p",full.name(),"d",full.level(),"","ctx-1"));var readiness=mock(com.aiep.aihub.application.hr.HrReadinessService.class);when(readiness.bindings(actor)).thenReturn(Map.of("hr.requirements.evaluate",newBinding));var bindings=mock(com.aiep.aihub.application.hr.HrPublishedBindingService.class);when(bindings.validateDictionary(actor,"d")).thenReturn(1L);var transactions=mock(org.springframework.transaction.PlatformTransactionManager.class);when(transactions.getTransaction(any())).thenReturn(new org.springframework.transaction.support.SimpleTransactionStatus());when(repository.activate("t","p","v1.1","ctx-1",3)).thenReturn(true);
        var live=new HrPositionService(repository,contexts,readiness,bindings,transactions);var result=live.publish(actor,"p",3);assertEquals("v1.1",result.version());assertEquals(newBinding,result.bindings().get("hr.requirements.evaluate"));assertEquals(oldBinding,previous.bindings().get("hr.requirements.evaluate"));
    }
    @Test void reloading_after_publish_uses_current_aggregate_version_for_next_edit(){
        var active=new Position("p","t","岗位","TECHNOLOGY","d","P6","d-000001","ACTIVE","v1.0","ctx-1","1",Instant.now(),3);
        when(repository.find("t","p")).thenReturn(active);when(repository.draft("t","p")).thenReturn(draft(List.of(),raw()));when(repository.saveDraft(eq("t"),any(),eq(3L))).thenReturn(true);
        var reloaded=service.draft(actor,"p");assertEquals(3,reloaded.version());assertEquals(4,service.save(actor,"p",reloaded).version());verify(repository).saveDraft(eq("t"),any(),eq(3L));
    }
    final HrPositionRepository repository=mock(HrPositionRepository.class);
    final HrPositionService service=new HrPositionService(repository);
    final HrActor actor=new HrActor("t","1",Set.of("d"),Set.of("hr:position:read","hr:position:edit","hr:position:publish"));
    final Position position=new Position("p","t","岗位","TECHNOLOGY","d","P6","d-000001","DRAFT",null,"ctx-1","1",Instant.now(),2);
    Map<Dimension,Integer> weights(){return Map.of(Dimension.SKILL,100,Dimension.EXPERIENCE,0,Dimension.PROJECT,0,Dimension.EDUCATION,0,Dimension.BONUS,0);}
    List<HrFrozenConfig.Requirement> requirements(){return List.of(new HrFrozenConfig.Requirement("java",Dimension.SKILL,BigDecimal.ONE,true,true));}
    DraftScoring raw(){return new DraftScoring("draft",weights(),requirements(),80,65,50,new BigDecimal("80"),new BigDecimal("90"));}
    Draft draft(List<SemanticCriterion> criteria,DraftScoring raw){return new Draft("p","岗位新名","TECHNOLOGY","d","P7","","PREVIEW",null,
            List.of(new HardRule("years","WORK_EXPERIENCE","工作年限","≥3年","month",new BigDecimal("36"),BigDecimal.ZERO,true,List.of(),null)),criteria,2,raw);}
    @Test void unfinished_scoring_can_be_saved_but_cannot_be_published(){
        when(repository.find("t","p")).thenReturn(position);when(repository.saveDraft(eq("t"),any(),eq(2L))).thenReturn(true);
        var raw=new DraftScoring("draft",Map.of(Dimension.SKILL,70),List.of(),80,65,50,new BigDecimal("80"),new BigDecimal("90"));
        Draft saved=service.save(actor,"p",draft(List.of(),raw));assertNull(saved.scoring());assertEquals(70,saved.draftScoring().weights().get(Dimension.SKILL));
        when(repository.draft("t","p")).thenReturn(draft(List.of(),raw));assertThrows(RuntimeException.class,()->service.publish(actor,"p",2));verify(repository,never()).insertConfig(any(),any());
    }
    @Test void published_version_and_embedded_scoring_are_consistent_and_metadata_is_applied(){
        when(repository.find("t","p")).thenReturn(position);
        var criteria=List.of(new SemanticCriterion("java","Java","SKILL","使用Java独立交付","架构治理证据","独立交付证据","部分参与证据","明确不满足证据",true));
        when(repository.draft("t","p")).thenReturn(draft(criteria,raw()));when(repository.activate("t","p","v1.0","ctx-1",2)).thenReturn(true);
        ConfigVersion published=service.publish(actor,"p",2);
        assertEquals("v1.0",published.snapshot().scoring().version());assertEquals(64,published.snapshotHash().length());
        verify(repository).applyPublishedMetadata("t",published);
    }
    @Test void missing_criterion_anchor_cannot_activate_a_valid_weight_configuration(){
        when(repository.find("t","p")).thenReturn(position);when(repository.draft("t","p")).thenReturn(draft(List.of(),raw()));
        assertThrows(RuntimeException.class,()->service.publish(actor,"p",2));verify(repository,never()).activate(any(),any(),any(),any(),anyLong());
    }
    @org.junit.jupiter.params.ParameterizedTest
    @org.junit.jupiter.params.provider.CsvSource({"4,0.5", "4,2", "1,1", "3,1", "4.5,1", "0,0", "-1,0", "4,-1"})
    void language_publication_rejects_invalid_ordinal_or_tolerance(String threshold, String tolerance) {
        when(repository.find("t","p")).thenReturn(position);
        when(repository.draft("t","p")).thenReturn(languageDraft(new BigDecimal(threshold), new BigDecimal(tolerance)));
        assertThrows(RuntimeException.class, () -> service.publish(actor,"p",2));
        verify(repository,never()).insertConfig(any(),any());
    }
    @org.junit.jupiter.params.ParameterizedTest
    @org.junit.jupiter.params.provider.CsvSource({"4,1", "1,0", "3,0"})
    void language_publication_accepts_integer_tolerance_within_floored_limit(String threshold, String tolerance) {
        when(repository.find("t","p")).thenReturn(position);
        when(repository.draft("t","p")).thenReturn(languageDraft(new BigDecimal(threshold), new BigDecimal(tolerance)));
        when(repository.activate("t","p","v1.0","ctx-1",2)).thenReturn(true);
        assertEquals(new BigDecimal(threshold),service.publish(actor,"p",2).snapshot().hardConditions().getFirst().threshold());
    }
    @Test void language_publication_requires_explicit_level_ordinal() {
        when(repository.find("t","p")).thenReturn(position);
        when(repository.draft("t","p")).thenReturn(languageDraft(null, BigDecimal.ZERO));
        assertThrows(RuntimeException.class, () -> service.publish(actor,"p",2));
    }
    Draft languageDraft(BigDecimal threshold, BigDecimal tolerance) {
        return new Draft("p","岗位新名","TECHNOLOGY","d","P7","","PREVIEW",raw().freeze(),
            List.of(new HardRule("lang","LANGUAGE","英语等级","CEFR B2","CEFR",threshold,tolerance,true,List.of("B2"),"ALL")),
            List.of(new SemanticCriterion("java","Java","SKILL","Java交付","架构治理","独立交付","部分参与","明确不足",true),
                new SemanticCriterion("lang","英语等级","SKILL","CEFR A1<A2<B1<B2<C1<C2","C1/C2","B2","B1为容差档","A1/A2",true)),2);
    }}
