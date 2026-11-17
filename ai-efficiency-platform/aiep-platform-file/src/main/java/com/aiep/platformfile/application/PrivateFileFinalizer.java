package com.aiep.platformfile.application;

import com.aiep.platformfile.repository.PrivateFileMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;

/** 物理删除回执使用独立事务，不能复用已提交事务的连接而丢失提交。 */
@Service
public class PrivateFileFinalizer {
  private final PrivateFileMapper mapper;

  public PrivateFileFinalizer(PrivateFileMapper mapper) {
    this.mapper = mapper;
  }

  @Transactional(propagation = Propagation.REQUIRES_NEW)
  public void completed(String tenant, String file) {
    mapper.completeDeletion(tenant, file);
    mapper.clearReferences(tenant, file);
  }
}
