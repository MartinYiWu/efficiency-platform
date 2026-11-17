package com.aiep.aihub.hr;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.application.hr.*;
import com.aiep.aihub.repository.hr.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;
class HrMatchingExecutionPlansTest {
 final HrActor actor=new HrActor("t","1",Set.of("d"),Set.of("hr:matching:run"));
 @Test void same_business_input_reuses_scope_across_client_keys_but_different_positions_do_not(){var service=new HrMatchingExecutionPlans(mock(HrMatchingExecutionPlanMapper.class),mock(HrMatchingRepository.class),mock(HrBatchMapper.class),mock(HrSemanticGateway.class),new ObjectMapper().findAndRegisterModules());var date=LocalDate.of(2026,11,11);String first=service.scope(actor,"c","fact","p1","rules","ctx-2",date);assertEquals(first,service.scope(actor,"c","fact","p1","rules","ctx-2",date));assertNotEquals(first,service.scope(actor,"c","fact","p2","rules","ctx-2",date));assertNotEquals(first,service.scope(actor,"c","new-fact","p1","rules","ctx-2",date));}
 @Test void missing_budget_cannot_insert_a_fresh_paid_plan(){var mapper=mock(HrMatchingExecutionPlanMapper.class);var gateway=mock(HrSemanticGateway.class);var policy=mock(HrBatchMapper.class);var json=new ObjectMapper().findAndRegisterModules();when(policy.latestPolicy("t")).thenReturn(new HrBatchMapper.PolicyRow("policy","t","{\"maximumAttempts\":1}",1,Instant.now()));when(gateway.execute(eq(actor),eq(6109L),anyString(),any())).thenThrow(new HrBusinessException("NO_BUDGET","no authorization",409));var service=new HrMatchingExecutionPlans(mapper,mock(HrMatchingRepository.class),policy,gateway,json);assertThrows(HrBusinessException.class,()->service.prepare(actor,"run","hr-match-fixed",2,true));verify(mapper,never()).insert(any());}
 @Test void cpu_only_zero_plan_and_existing_failed_run_are_reused_without_model()throws Exception{var mapper=mock(HrMatchingExecutionPlanMapper.class);var runs=mock(HrMatchingRepository.class);var gateway=mock(HrSemanticGateway.class);var json=new ObjectMapper().findAndRegisterModules();var service=new HrMatchingExecutionPlans(mapper,runs,mock(HrBatchMapper.class),gateway,json);var plan=service.prepare(actor,"run","hr-match-fixed",0,false);assertTrue(plan.cpuOnly());assertEquals(0,plan.maximumCalls());verifyNoInteractions(gateway);when(mapper.find("t","hr-match-fixed")).thenReturn(new HrMatchingExecutionPlanMapper.Row("t","hr-match-fixed","run",json.writeValueAsString(plan)));var failed=new com.aiep.aihub.api.hr.HrCandidateContracts.Run("run","t","c","p","FAILED",null,"OLD_FAILURE",Instant.now(),"sealed",Instant.now(),"oldkey","hash","hr-match-fixed");when(runs.run("t","run")).thenReturn(failed);assertEquals(failed,service.findRun(actor,"hr-match-fixed"));assertEquals("run",service.prepare(actor,"another-run","hr-match-fixed",0,false).runId());verifyNoInteractions(gateway);}
}
