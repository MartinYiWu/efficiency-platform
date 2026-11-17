package com.aiep.aihub.hr;
import static org.junit.jupiter.api.Assertions.*;
import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.application.hr.*;
import com.fasterxml.jackson.databind.*;
import java.util.*;
import org.junit.jupiter.api.Test;
class HrProtectedModelOutputTest {
 final ObjectMapper json=new ObjectMapper();final Block block=new Block("b",null,"Java",null);final Evidence evidence=new Evidence("b",0,4,"Java");
 @Test void exact_real_quote_cannot_justify_protected_reason(){var data=json.createObjectNode();var item=data.putArray("assessments").addObject().put("requirement_id","r").put("status","MATCH").put("reason","年龄偏大");item.putArray("evidence").addObject().put("block_id","b").put("start",0).put("end",4).put("quote","Java");var error=assertThrows(HrBusinessException.class,()->HrMatchingService.validateAssessments(data,Set.of("r"),List.of(block)));assertEquals("HR_PROTECTED_ATTRIBUTE_FORBIDDEN",error.code());}
 @Test void unmentioned_unknown_remains_valid_without_invented_negative_facts(){var data=json.createObjectNode();data.putArray("assessments").addObject().put("requirement_id","r").put("status","UNKNOWN").put("reason","材料未提及，保留待核验").putArray("evidence");assertEquals(com.aiep.aihub.domain.hr.HrAtomicAssessment.Level.UNKNOWN,HrMatchingService.validateAssessments(data,Set.of("r"),List.of(block)).get("r").level());}
 @Test void explanation_and_summary_protected_text_fail_despite_valid_evidence(){var data=json.createObjectNode();data.putArray("highlights");data.putArray("gaps");var point=data.putArray("verification_points").addObject().put("text","性别决定协作能力");point.putArray("requirement_ids").add("r");point.putArray("evidence").addObject().put("block_id","b").put("start",0).put("end",4).put("quote","Java");var source=List.of(new SemanticAssessment("r","MATCH","Java",List.of(evidence)));assertThrows(HrBusinessException.class,()->HrMatchingService.validateExplanation(data,source,List.of(block)));point.put("text","核实职责");data.put("summary","年龄");assertThrows(HrBusinessException.class,()->HrMatchingService.validateExplanation(data,source,List.of(block)));}
}
