package com.aiep.aihub.hr;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.application.hr.*;
import com.aiep.aihub.repository.hr.*;
import com.aiep.platformai.api.AiInvokeFacade;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.Set;
import org.junit.jupiter.api.Test;
class HrGatewayBatchStopTest {
 @Test void parent_stop_is_checked_before_another_paid_stage_can_be_sent(){var facade=mock(AiInvokeFacade.class);var batches=mock(HrBatchMapper.class);var json=new ObjectMapper();var gateway=new HrSemanticGateway(facade,json,null,mock(HrBatchBudgetMapper.class),batches,mock(HrExecutionMapper.class));var actor=new HrActor("t","1",Set.of("d"),Set.of("hr:matching:run"));when(batches.item("t","i")).thenReturn(new HrBatchMapper.ItemRow("i","t","b","r.txt","cipher","hash","RUNNING","ANALYZING","c",null,70));when(batches.batch("t","b")).thenReturn(new HrBatchMapper.BatchRow("b","t","d","1","p","MATCH","policy",1,"CANCELLED",2,Instant.now(),"key","hash"));assertEquals("HR_RUN_CANCELLED",assertThrows(HrBusinessException.class,()->gateway.execute(actor,6103,"hr-import-i",json.createObjectNode())).code());verifyNoInteractions(facade);}
}
