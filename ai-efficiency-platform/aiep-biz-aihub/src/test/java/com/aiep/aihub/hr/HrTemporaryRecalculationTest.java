package com.aiep.aihub.hr;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.domain.hr.*;
import com.aiep.aihub.domain.hr.HrHardConditionEvaluator.*;
import com.aiep.aihub.application.hr.HrResultAssembler;
import java.time.*;
import java.util.*;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.mockito.ArgumentCaptor;
class HrTemporaryRecalculationTest {
 @ParameterizedTest @ValueSource(booleans={true,false})
 void recalculation_fits_mysql_and_isolates_run_keys_without_model_calls(boolean temporary)throws Exception{
  var f=new HrMatchingLifecycleTest();var facts=f.facts();var config=f.config();var atomic=List.of(new HrAtomicAssessment("r",HrAtomicAssessment.Level.MATCH,null,null,List.of("b")));List<Result> hard=List.of();var score=new HrScoreEngine().score(config.snapshot().scoring(),new HrVerifiedFacts(hard,false),atomic,Set.of(),LocalDate.of(2026,11,11));var old=new HrResultAssembler().assemble("m",facts,"s",f.position(),config,"sem",score,atomic);
  when(f.positions.get(f.actor,"p")).thenReturn(f.position());var snapshot=new Snapshot("s","t","c","r",1,f.codec.seal(f.json.writeValueAsString(facts)),"1",Instant.now().toString());when(f.candidates.snapshot(f.actor,"c")).thenReturn(snapshot);when(f.candidates.decode(snapshot)).thenReturn(facts);
  when(f.repository.result("t","m")).thenReturn(new ResultSnapshot("m","t","c","p","s","v1.0","ctx-1","sem",f.codec.seal(f.json.writeValueAsString(old)),"CURRENT",null,old.createdAt(),"SCORED"));
  when(f.repository.semantic("t","sem")).thenReturn(new SemanticSnapshot("sem","t","c","s",f.codec.seal(f.json.writeValueAsString(config)),f.codec.seal(f.json.writeValueAsString(new SemanticAssessments(atomic,List.of()))),f.codec.seal(f.json.writeValueAsString(hard)),Instant.now().toString()));when(f.repository.start(eq("t"),anyString())).thenReturn(true);when(f.repository.completeBatch(eq("t"),anyString(),anyList(),anyList())).thenReturn(true);
  for(int i=0;i<2;i++){
   if(temporary) f.service.recalculate(f.actor,new Recalculation("p","v1.0",List.of("m"),new RecalculationWeights(100,0,0,0,0),List.of(80,65,50),"TEMPORARY",1));
   else f.service.recalculate(f.actor,"m");
  }
  ArgumentCaptor<Run> runs=ArgumentCaptor.forClass(Run.class);verify(f.repository,times(2)).insertRun(runs.capture());
  for(var run:runs.getAllValues()){
   assertNotNull(run.idempotencyKey(),"重算任务幂等键必须满足MySQL NOT NULL约束");
   assertTrue(run.idempotencyKey().matches("[A-Za-z0-9_-]{8,100}"),"幂等键必须合法且不超过100字符");
   assertEquals("recalc-"+run.id(),run.idempotencyKey(),"幂等键应稳定绑定本次run");
  }
  assertNotEquals(runs.getAllValues().get(0).idempotencyKey(),runs.getAllValues().get(1).idempotencyKey(),"同一结果的不同重算必须隔离");
  ArgumentCaptor<List<ResultSnapshot>> results=ArgumentCaptor.forClass(List.class);verify(f.repository,times(2)).completeBatch(eq("t"),anyString(),anyList(),results.capture());var saved=results.getValue().getFirst();assertTrue(saved.configVersion().length()<=32,"临时版本不能超过已执行MySQL列长度");var matching=f.json.readValue(f.codec.open(saved.resultJson()),Matching.class);var projected=new HrResultAssembler().status(matching,"TEMPORARY",null);assertEquals("SCORED",projected.businessStatus());assertEquals(80,projected.totalScore().intValue());verifyNoInteractions(f.gateway);verify(f.positions,never()).publishScoring(any(),any(),anyLong(),any());
 }
}

