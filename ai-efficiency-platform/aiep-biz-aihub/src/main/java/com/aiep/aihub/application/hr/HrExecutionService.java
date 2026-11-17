package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.api.hr.HrExecutionContracts.*;
import com.aiep.aihub.repository.hr.HrExecutionMapper;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;

@Service
public class HrExecutionService {
  private final HrExecutionMapper mapper;
  private final HrMatchingService matching;
  private final HrSensitiveJsonCodec codec;
  private HrActorAuthority authority;

  @org.springframework.beans.factory.annotation.Autowired
  public HrExecutionService(
      HrExecutionMapper mapper,
      HrMatchingService matching,
      HrSensitiveJsonCodec codec,
      HrActorAuthority authority) {
    this(mapper, matching, codec);
    this.authority = authority;
  }

  public HrExecutionService(
      HrExecutionMapper mapper, HrMatchingService matching, HrSensitiveJsonCodec codec) {
    this.mapper = mapper;
    this.matching = matching;
    this.codec = codec;
  }

  public Feedback feedback(HrActor actor, String id, FeedbackRequest input) {
    HrAccessPolicy.require(actor, "hr:matching:feedback");
    Matching result = matching.get(actor, id);
    matching.authorizeFeedback(actor, result);
    if (!Objects.equals(input.expectedSnapshotHash(), result.snapshotHash()))
      throw HrPositionService.conflict();
    if (!Set.of("ACCURATE", "HIGH", "LOW").contains(input.rating())
        || input.reason() == null
        || input.reason().codePointCount(0, input.reason().length()) > 500)
      throw HrPositionService.invalid("反馈或原因无效");
    var row =
        new HrExecutionMapper.FeedbackRow(
            UUID.randomUUID().toString(),
            actor.tenantId(),
            id,
            input.rating(),
            codec.seal(input.reason()),
            actor.userId(),
            Instant.now());
    mapper.feedback(row);
    return view(row);
  }

  public List<Feedback> feedbacks(HrActor actor, String id) {
    matching.get(actor, id);
    return mapper.feedbacks(actor.tenantId(), id).stream().map(this::view).toList();
  }

  private Feedback view(HrExecutionMapper.FeedbackRow r) {
    return new Feedback(
        r.id(), r.resultId(), r.rating(), codec.open(r.reasonJson()), r.actorId(), r.createdAt());
  }

  public List<HrExecutionMapper.EventRow> events(HrActor actor, String id, long after) {
    if (authority != null) actor = authority.refresh(actor);
    if (after < 0) throw HrPositionService.invalid("事件序号无效");
    Run run = matching.run(actor, id);
    long sequence =
        switch (run.status()) {
          case "PENDING" -> 1;
          case "RUNNING" -> 2;
          case "CANCEL_PENDING" -> 3;
          default -> 4;
        };
    mapper.recordEvent(
        new HrExecutionMapper.EventRow(
            actor.tenantId(),
            id,
            sequence,
            run.status(),
            run.resultId(),
            run.failureCode(),
            Instant.now()));
    return mapper.events(actor.tenantId(), id, after);
  }
}
