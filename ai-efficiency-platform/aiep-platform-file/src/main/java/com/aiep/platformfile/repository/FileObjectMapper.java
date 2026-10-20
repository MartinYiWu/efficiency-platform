package com.aiep.platformfile.repository;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface FileObjectMapper extends BaseMapper<FileObjectPO> {
    @Select("SELECT * FROM pf_file_object WHERE tenant_id = #{tenantId} "
            + "AND id = #{fileId} AND status = 'ACTIVE' LIMIT 1")
    FileObjectPO selectActive(@Param("tenantId") String tenantId, @Param("fileId") String fileId);
}
