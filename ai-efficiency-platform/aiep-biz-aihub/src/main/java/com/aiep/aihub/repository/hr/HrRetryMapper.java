package com.aiep.aihub.repository.hr;

import org.apache.ibatis.annotations.*;

@Mapper
public interface HrRetryMapper {
  void initialize(@Param("tenant") String tenant, @Param("item") String item);

  int claim(@Param("tenant") String tenant, @Param("item") String item);

  int reset(
      @Param("tenant") String tenant,
      @Param("item") String item,
      @Param("content") String content,
      @Param("hash") String hash,
      @Param("filename") String filename);
}
