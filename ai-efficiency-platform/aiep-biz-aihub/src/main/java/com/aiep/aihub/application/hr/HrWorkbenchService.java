package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.api.hr.HrWorkbenchContracts.*;
import com.aiep.aihub.repository.hr.*;
import java.math.*;
import java.time.*;
import java.time.temporal.TemporalAdjusters;
import java.util.*;
import org.springframework.stereotype.Service;

/** 工作台仅统计同一权限tuple中的当前对象；时间采用北京时间本周及上周同时长。 */
@Service
public class HrWorkbenchService {
  private final HrWorkbenchMapper mapper;
  private final HrTalentMapper talents;
  private final HrTalentSearchService talent;
  private final HrAuditService audit;

  public HrWorkbenchService(
      HrWorkbenchMapper mapper,
      HrTalentMapper talents,
      HrTalentSearchService talent,
      HrAuditService audit) {
    this.mapper = mapper;
    this.talents = talents;
    this.talent = talent;
    this.audit = audit;
  }

  public Workbench get(HrActor actor) {
    HrAccessPolicy.require(actor, "hr:candidate:read");
    Instant now = Instant.now();
    ZonedDateTime local = now.atZone(ZoneId.of("Asia/Shanghai"));
    Instant week =
        local
            .toLocalDate()
            .with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY))
            .atStartOfDay(local.getZone())
            .toInstant();
    long candidates = 0,
        scored = 0,
        filtered = 0,
        review = 0,
        drafts = 0,
        pending = 0,
        current = 0,
        previous = 0;
    List<PositionProgress> progress = new ArrayList<>();
    for (String department : HrAccessPolicy.departmentsFor(actor, "hr:candidate:read")) {
      var ids = HrAccessPolicy.objectIdsFor(actor, "hr:candidate:read", department, "CANDIDATE");
      if (ids.isEmpty()) continue;
      Set<String> positions =
          actor.permissions().contains("hr:position:read")
              ? HrAccessPolicy.objectIdsFor(actor, "hr:position:read", department, "POSITION")
              : Set.of();
      if (positions.isEmpty()) positions = Set.of("!NONE");
      var ds = Set.of(department);
      var count = mapper.scopedCounts(actor.tenantId(), ds, ids, positions, now);
      candidates += count.candidates();
      scored += count.scored();
      filtered += count.filtered();
      review += count.reviewRequired();
      drafts += count.draftPositions();
      pending += count.pendingReview();
      current += mapper.acquired(actor.tenantId(), ds, ids, week, now, now);
      previous +=
          mapper.acquired(
              actor.tenantId(),
              ds,
              ids,
              week.minus(Duration.ofDays(7)),
              now.minus(Duration.ofDays(7)),
              now);
      progress.addAll(mapper.scopedPositions(actor.tenantId(), ds, ids, positions, now));
    }
    String comparison =
        previous == 0
            ? "无可比数据"
            : "较上周同时长 "
                + BigDecimal.valueOf(current - previous)
                    .multiply(BigDecimal.valueOf(100))
                    .divide(BigDecimal.valueOf(previous), 1, RoundingMode.HALF_UP)
                + "%";
    long expiring = 0, unknown = 0;
    pending = 0;
    var visible = talent.visibleCandidates(actor, "hr:candidate:read", now);
    var visibleIds =
        visible.stream()
            .map(com.aiep.aihub.api.hr.HrCandidateContracts.Candidate::id)
            .collect(java.util.stream.Collectors.toUnmodifiableSet());
    if (!visibleIds.isEmpty()) pending = talents.waiting(actor.tenantId(), visibleIds, now).size();
    for (var candidate : visible) {
      if (candidate.expiresAt().isBefore(now.plus(Duration.ofDays(30)))) expiring++;
      var facts = talent.facts(actor, candidate);
      unknown +=
          facts.normalizations().stream()
              .filter(f -> "SKILL".equals(f.category()) && "UNNORMALIZED".equals(f.status()))
              .count();
    }
    List<Todo> todos = new ArrayList<>();
    add(todos, "correction", "低置信待确认", pending, "/ai-assistants/hr/resumes");
    add(todos, "filtered", "明确过滤待查看", filtered, "/ai-assistants/hr/matching/filtered");
    add(todos, "positions", "未完成岗位", drafts, "/ai-assistants/hr/positions");
    add(todos, "unnormalized", "未归一技能", unknown, "/ai-assistants/hr/settings/dictionary");
    add(todos, "expiring", "30天内到期", expiring, "/ai-assistants/hr/talent");
    var activities =
        actor.permissions().contains("hr:audit:read")
            ? audit.list(actor, 1, 20).items().stream()
                .map(e -> new Activity(e.id(), e.occurredAt().toString(), e.action()))
                .toList()
            : List.<Activity>of();
    return new Workbench(
        List.of(
            new Metric("candidates", "授权候选人", candidates, comparison),
            new Metric("scored", "有效评分结果", scored, "按当前配置版本"),
            new Metric("review", "待核验结果", review, "未计入正式排名"),
            new Metric("filtered", "硬条件过滤", filtered, "保留资料，可人工复核")),
        List.copyOf(todos),
        progress.stream()
            .sorted(
                Comparator.comparing(PositionProgress::name).thenComparing(PositionProgress::id))
            .limit(20)
            .toList(),
        activities);
  }

  private void add(List<Todo> todos, String key, String label, long count, String path) {
    if (count > 0) todos.add(new Todo(key, label, count, path));
  }
}
