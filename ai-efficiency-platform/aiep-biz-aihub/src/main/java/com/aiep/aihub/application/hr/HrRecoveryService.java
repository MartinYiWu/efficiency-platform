package com.aiep.aihub.application.hr;

import com.aiep.aihub.repository.hr.HrExecutionMapper;
import java.time.Instant;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

/** 重启后未知在途任务只做持久阻断，绝不恢复付费发送或重建预算。 */
@Component
public class HrRecoveryService {
  private final HrExecutionMapper mapper;
  private final Instant started = Instant.now();

  public HrRecoveryService(HrExecutionMapper mapper) {
    this.mapper = mapper;
  }

  @EventListener(ApplicationReadyEvent.class)
  @org.springframework.transaction.annotation.Transactional
  public void recover() {
    mapper.recoverRuns(started);
    mapper.recoverBatches(started);
    mapper.recoverItems(started);
  }
}
