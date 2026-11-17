package com.aiep.aihub.application.hr;

import com.aiep.aihub.repository.hr.HrAuditArchiveMapper;
import java.time.*;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 主审计3年后事务归档，原事件满10年才清理；归档失败不删除主表。 */
@Service
public class HrAuditArchiveService {
  private final HrAuditArchiveMapper mapper;

  public HrAuditArchiveService(HrAuditArchiveMapper mapper) {
    this.mapper = mapper;
  }

  @Scheduled(fixedDelay = 86400000)
  @Transactional
  public void archiveDue() {
    ZonedDateTime now = Instant.now().atZone(ZoneOffset.UTC);
    Instant hotBefore = now.minusYears(3).toInstant();
    mapper.archive(hotBefore, now.toInstant());
    mapper.removeArchivedHot(hotBefore);
    mapper.expireCold(now.minusYears(10).toInstant());
  }
}
