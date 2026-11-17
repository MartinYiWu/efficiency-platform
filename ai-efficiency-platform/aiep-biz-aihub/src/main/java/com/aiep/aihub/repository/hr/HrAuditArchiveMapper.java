package com.aiep.aihub.repository.hr;

import java.time.Instant;
import org.apache.ibatis.annotations.*;

/** 归档仅供内部保留期任务，业务HTTP没有更新或删除审计的入口。 */
@Mapper
public interface HrAuditArchiveMapper {
  int archive(@Param("before") Instant before, @Param("now") Instant now);

  int removeArchivedHot(@Param("before") Instant before);

  int expireCold(@Param("before") Instant before);
}
