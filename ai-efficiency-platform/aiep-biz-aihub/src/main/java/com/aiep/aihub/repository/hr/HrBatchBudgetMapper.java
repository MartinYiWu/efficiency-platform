package com.aiep.aihub.repository.hr;

import org.apache.ibatis.annotations.*;

@Mapper
public interface HrBatchBudgetMapper {
  record Row(String tenantId, String batchId, String departmentId, String payload) {}

  Row find(@Param("tenant") String tenant, @Param("batch") String batch);

  int insert(Row row);
}
