package com.aiep.aihub.repository.hr;
import org.apache.ibatis.annotations.*;
/** 显式手工匹配计划的稳定业务scope，独立于上传批次且只写一次。 */
@Mapper public interface HrMatchingExecutionPlanMapper {
 record Row(String tenantId,String scope,String runId,String payload){}
 Row find(@Param("tenant")String tenant,@Param("scope")String scope);
 int insert(Row row);
}
