package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrCandidateContracts.Candidate;
import com.aiep.aihub.repository.hr.HrTalentMapper;
import java.time.Instant;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** 墓碑、授权撤销和Saga登记同事务，进程中断不会留下无任务的DELETING对象。 */
@Service
public class HrExpiredDeletionRegistrar {
  private final HrTalentMapper mapper;
  private final TransactionTemplate transactions;

  public HrExpiredDeletionRegistrar(HrTalentMapper mapper, PlatformTransactionManager manager) {
    this.mapper = mapper;
    this.transactions = new TransactionTemplate(manager);
  }

  public void register(Candidate candidate) {
    transactions.executeWithoutResult(
        status -> {
          if (mapper.tombstone(candidate.tenantId(), candidate.id(), candidate.version()) != 1)
            return;
          mapper.revokeCandidateGrants(candidate.tenantId(), candidate.id());
          mapper.revokeAssignments(candidate.tenantId(), candidate.id());
          mapper.revokeExports(candidate.tenantId(), candidate.id());
          Instant now = Instant.now();
          mapper.insertJob(
              new HrTalentMapper.JobRow(
                  UUID.randomUUID().toString(),
                  candidate.tenantId(),
                  candidate.id(),
                  candidate.departmentId(),
                  "PENDING",
                  "INDEX",
                  0,
                  now,
                  now,
                  null));
        });
  }
}
