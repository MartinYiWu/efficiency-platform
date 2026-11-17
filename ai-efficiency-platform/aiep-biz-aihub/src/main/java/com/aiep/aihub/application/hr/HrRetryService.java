package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.repository.hr.*;
import java.util.*;
import org.springframework.stereotype.Service;

/** 人工有界重试必须修正材料且仍使用原批次/原scope/原截止，不为失败重新领预算。 */
@Service
public class HrRetryService {
  public record Retry(String filename, String contentBase64, String expectedHash, String reason) {}

  private final HrBatchMapper batches;
  private final HrRetryMapper mapper;
  private final HrBatchBudgetService budgets;
  private final HrSensitiveJsonCodec codec;
  private final org.springframework.transaction.support.TransactionTemplate transactions;

  public HrRetryService(
      HrBatchMapper batches,
      HrRetryMapper mapper,
      HrBatchBudgetService budgets,
      HrSensitiveJsonCodec codec,
      org.springframework.transaction.PlatformTransactionManager manager) {
    this.batches = batches;
    this.mapper = mapper;
    this.budgets = budgets;
    this.codec = codec;
    this.transactions = new org.springframework.transaction.support.TransactionTemplate(manager);
  }

  public String validate(HrActor actor, String item, Retry input) {
    HrAccessPolicy.require(actor, "hr:candidate:upload");
    var old = batches.item(actor.tenantId(), item);
    if (old == null) throw HrPositionService.missing();
    var batch = batches.batch(actor.tenantId(), old.batchId());
    HrAccessPolicy.requireFor(
        actor, "hr:candidate:upload", batch.departmentId(), null, "CANDIDATE");
    budgets.validate(actor, batch.id());
    return batch.id();
  }

  public String retry(HrActor actor, String item, Retry input) {
    String batch = validate(actor, item, input);
    return transactions.execute(status -> retryFrozen(actor, item, input, batch));
  }

  private String retryFrozen(HrActor actor, String item, Retry input, String batch) {
    var parent = batches.lockBatch(actor.tenantId(), batch);
    var old = batches.item(actor.tenantId(), item);
    if (!"FAILED".equals(old.status()) || !Set.of("COMPLETED", "BLOCKED").contains(parent.status()))
      throw HrPositionService.conflict();
    if (input.reason() == null
        || input.reason().isBlank()
        || input.reason().length() > 500
        || input.contentBase64() == null
        || input.contentBase64().length() > 28000000)
      throw HrPositionService.invalid("请提供修正材料和重试原因");
    byte[] content;
    try {
      content = Base64.getDecoder().decode(input.contentBase64());
    } catch (IllegalArgumentException e) {
      throw HrPositionService.invalid("材料编码无效");
    }
    if (content.length == 0 || content.length > 20 * 1024 * 1024)
      throw HrPositionService.invalid("重试材料须小于20MiB");
    String hash = HrPositionService.hash(Base64.getEncoder().encodeToString(content));
    if (!old.contentHash().equals(input.expectedHash()) || hash.equals(old.contentHash()))
      throw new HrBusinessException("HR_RETRY_INPUT_UNCHANGED", "材料未修正或旧版本已变化，不能重复发送同一失败操作", 409);
    mapper.initialize(actor.tenantId(), item);
    if (mapper.claim(actor.tenantId(), item) != 1)
      throw new HrBusinessException("HR_RETRY_LIMIT_EXCEEDED", "本条人工重试次数已耗尽", 409);
    if (mapper.reset(
            actor.tenantId(),
            item,
            codec.seal(input.contentBase64()),
            hash,
            HrPositionService.text(input.filename(), 255))
        != 1) throw HrPositionService.conflict();
    if (batches.advance(actor.tenantId(), batch, parent.version(), parent.status(), "RUNNING") != 1)
      throw HrPositionService.conflict();
    return batch;
  }
}
