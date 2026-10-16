package com.aiep.aihub.repository.operation;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface OperationRunMapper extends BaseMapper<OperationRunPO> {
    @Select("SELECT * FROM ai_operation_run WHERE id = #{id} AND tenant_id = #{tenantId} FOR UPDATE")
    OperationRunPO selectForUpdate(@Param("id") String id, @Param("tenantId") String tenantId);
}
