package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.api.hr.HrTalentContracts.*;
import com.aiep.aihub.repository.hr.*;
import com.fasterxml.jackson.databind.*;
import java.time.*;
import java.util.*;
import org.springframework.stereotype.Service;

/** 来源独立鉴权，检索仅在SQL授权集合内计算相关片段，绝不把相关度写入评分。 */
@Service
public class HrTalentSearchService {
  public record BatchedFacts(Facts facts, Instant updatedAt) {}

  private final HrTalentMapper mapper;
  private final ObjectMapper json;
  private final HrSensitiveJsonCodec codec;
  private final HrSourceAuthorization authorization;
  private final HrPositionService positions;
  private final HrSettingsRepository settings;

  public HrTalentSearchService(
      HrTalentMapper mapper,
      ObjectMapper json,
      HrSensitiveJsonCodec codec,
      HrSourceAuthorization authorization,
      HrPositionService positions,
      HrSettingsRepository settings) {
    this.mapper = mapper;
    this.json = json;
    this.codec = codec;
    this.authorization = authorization;
    this.positions = positions;
    this.settings = settings;
  }

  public Candidate authorized(HrActor actor, String id, String permission) {
    HrAccessPolicy.require(actor, permission);
    Candidate c = mapper.candidate(actor.tenantId(), id);
    if (!visible(actor, c)) throw missing();
    HrAccessPolicy.requireFor(actor, permission, c.departmentId(), c.id(), "CANDIDATE");
    return c;
  }

  public boolean visible(HrActor actor, Candidate c) {
    return c != null
        && actor.tenantId().equals(c.tenantId())
        && (actor.candidateIds().contains("*") || actor.candidateIds().contains(c.id()))
        && actor.departmentIds().contains(c.departmentId())
        && "ACTIVE".equals(c.status())
        && c.expiresAt() != null
        && c.expiresAt().isAfter(Instant.now());
  }

  public List<Candidate> visibleCandidates(HrActor actor, String permission, Instant now) {
    List<Candidate> result = new ArrayList<>();
    for (String department : HrAccessPolicy.departmentsFor(actor, permission)) {
      var ids = HrAccessPolicy.objectIdsFor(actor, permission, department, "CANDIDATE");
      if (!ids.isEmpty())
        result.addAll(mapper.visible(actor.tenantId(), Set.of(department), ids, now));
    }
    result.sort(
        Comparator.comparing(Candidate::acquiredAt, Comparator.nullsLast(Comparator.reverseOrder()))
            .thenComparing(Candidate::id));
    return List.copyOf(result);
  }

  private boolean permitted(HrActor actor, Candidate c, String permission) {
    if (!visible(actor, c)) return false;
    try {
      HrAccessPolicy.requireFor(actor, permission, c.departmentId(), c.id(), "CANDIDATE");
      return true;
    } catch (HrBusinessException e) {
      return false;
    }
  }

  public Facts facts(HrActor actor, Candidate c) {
    if (!visible(actor, c)) throw missing();
    Snapshot snapshot = mapper.snapshot(actor.tenantId(), c.currentSnapshotId());
    if (snapshot == null) throw missing();
    try {
      return json.readValue(codec.open(snapshot.factsJson()), Facts.class);
    } catch (HrBusinessException e) {
      throw e;
    } catch (Exception e) {
      throw new HrBusinessException("HR_FACT_CONTRACT_FAILED", "事实快照无法验证", 503);
    }
  }

  public Map<String, BatchedFacts> factsBatch(HrActor actor, List<Candidate> candidates) {
    if (candidates.isEmpty()) return Map.of();
    Map<String, Candidate> bySnapshot = new HashMap<>();
    for (var candidate : candidates) {
      if (!permitted(actor, candidate, "hr:candidate:read")) throw missing();
      bySnapshot.put(candidate.currentSnapshotId(), candidate);
    }
    Map<String, BatchedFacts> result = new HashMap<>();
    for (var snapshot : mapper.snapshotsByIds(actor.tenantId(), bySnapshot.keySet())) {
      var candidate = bySnapshot.get(snapshot.id());
      if (candidate == null
          || !actor.tenantId().equals(snapshot.tenantId())
          || !candidate.id().equals(snapshot.candidateId())) throw missing();
      try {
        Facts facts = json.readValue(codec.open(snapshot.factsJson()), Facts.class);
        if (!candidate.id().equals(facts.candidateId())) throw missing();
        Instant updated;
        try {
          updated = Instant.parse(snapshot.createdAt());
        } catch (java.time.format.DateTimeParseException error) {
          updated = candidate.acquiredAt() == null ? Instant.EPOCH : candidate.acquiredAt();
        }
        result.put(candidate.id(), new BatchedFacts(facts, updated));
      } catch (HrBusinessException error) {
        throw error;
      } catch (com.fasterxml.jackson.core.JsonProcessingException error) {
        throw new HrBusinessException("HR_FACT_CONTRACT_FAILED", "事实快照无法验证", 503);
      }
    }
    if (result.size() != candidates.stream().map(Candidate::id).distinct().count()) throw missing();
    return Map.copyOf(result);
  }

  public List<Candidate> allSources(HrActor actor, String id) {
    var merge = mapper.mergeForCandidate(actor.tenantId(), id);
    if (merge == null) return List.of(authorized(actor, id, "hr:candidate:read"));
    return mapper.sources(actor.tenantId(), merge.primaryCandidateId());
  }

  public List<Candidate> authorizedSources(
      HrActor actor, String id, String permission, boolean requireAll) {
    HrAccessPolicy.require(actor, permission);
    List<Candidate> sources = allSources(actor, id);
    var allowed = sources.stream().filter(c -> permitted(actor, c, permission)).toList();
    if (allowed.isEmpty() || (requireAll && allowed.size() != sources.size())) throw missing();
    return allowed;
  }

  public void purpose(HrActor actor, Candidate c, String purpose) {
    authorization.requireUse(actor, c, purpose);
  }

  public void liveUse(String tenant, String candidate, String purpose) {
    authorization.requireLiveUse(tenant, candidate, purpose);
  }

  public TalentPage search(HrActor actor, String query, int page, int pageSize) {
    return search(
        actor, new SearchFilter(query, null, null, null, null, null, null), page, pageSize);
  }

  public TalentPage search(HrActor actor, SearchFilter filter, int page, int pageSize) {
    HrAccessPolicy.require(actor, "hr:candidate:read");
    pagination(page, pageSize);
    String term = Objects.toString(filter.query(), "").strip().toLowerCase(Locale.ROOT);
    if (term.length() > 200
        || filter.minimumExperienceMonths() != null && filter.minimumExperienceMonths() < 0
        || filter.maximumExperienceMonths() != null && filter.maximumExperienceMonths() < 0
        || filter.minimumExperienceMonths() != null
            && filter.maximumExperienceMonths() != null
            && filter.minimumExperienceMonths() > filter.maximumExperienceMonths()) throw invalid();
    Set<String> excluded = Set.of();
    if (filter.excludeMatchedPositionId() != null && !filter.excludeMatchedPositionId().isBlank()) {
      var p = positions.get(actor, filter.excludeMatchedPositionId());
      excluded = mapper.matchedCandidates(actor.tenantId(), p.id());
    }
    List<TalentSummary> found = new ArrayList<>();
    Set<String> seen = new HashSet<>();
    Instant now = Instant.now();
    Map<String, Set<String>> skillsByDepartment = new HashMap<>();
    List<Candidate> searchable = new ArrayList<>();
    for (Candidate c : visibleCandidates(actor, "hr:candidate:read", now)) {
      try {
        purpose(actor, c, "TALENT_POOL");
      } catch (HrBusinessException denied) {
        continue;
      }
      if (excluded.contains(c.id())) continue;
      searchable.add(c);
    }
    var batchedFacts = factsBatch(actor, searchable);
    for (Candidate c : searchable) {
      Facts f = batchedFacts.get(c.id()).facts();
      if (!filters(f, filter)) continue;
      if (filter.skill() != null && !filter.skill().isBlank()) {
        if (filter.dictionaryVersion() != null
            && !filter.dictionaryVersion().equals(f.dictionaryVersion())) continue;
        Set<String> canonical =
            skillsByDepartment.computeIfAbsent(
                c.departmentId(),
                d -> canonicalSkills(actor, d, filter.skill(), filter.dictionaryVersion()));
        Set<String> candidateSkills = new HashSet<>();
        f.skills().stream()
            .map(Skill::name)
            .map(HrTalentSearchService::normalize)
            .forEach(candidateSkills::add);
        f.normalizations().stream()
            .filter(
                n ->
                    "SKILL".equals(n.category())
                        && "NORMALIZED".equals(n.status())
                        && n.canonical() != null)
            .map(n -> normalize(n.canonical()))
            .forEach(candidateSkills::add);
        if (candidateSkills.stream().noneMatch(canonical::contains)) continue;
      }
      String visibleText =
          new InterviewViewAssembler()
              .resume(f).stream()
                  .map(HrInterviewContracts.ResumeSection::text)
                  .collect(java.util.stream.Collectors.joining("\n"));
      String text =
          String.join(" ", f.skills().stream().map(Skill::name).toList())
              + " "
              + Objects.toString(f.profile().education(), "")
              + " "
              + visibleText;
      if (!term.isEmpty()
          && !text.toLowerCase(Locale.ROOT).contains(term)
          && !Objects.toString(f.profile().name(), "").toLowerCase(Locale.ROOT).contains(term))
        continue;
      var merge = mapper.mergeForCandidate(actor.tenantId(), c.id());
      String logical = merge == null ? c.id() : merge.primaryCandidateId();
      if (!seen.add(logical)) continue;
      Instant updated = batchedFacts.get(c.id()).updatedAt();
      int match = term.isEmpty() ? -1 : visibleText.toLowerCase(Locale.ROOT).indexOf(term);
      String snippet =
          match < 0
              ? ""
              : visibleText.substring(
                  Math.max(0, match - 40),
                  Math.min(visibleText.length(), match + term.length() + 100));
      Double relevance = term.isEmpty() ? null : match >= 0 ? 1d : 0.5d;
      found.add(
          new TalentSummary(
              logical,
              f.profile().name(),
              f.profile().education(),
              f.profile().experienceMonths(),
              f.skills().stream().map(Skill::name).toList(),
              updated,
              c.expiresAt(),
              updated.isBefore(now.minus(Duration.ofDays(30))),
              c.expiresAt().isBefore(now.plus(Duration.ofDays(30))),
              snippet,
              relevance));
    }
    found.sort(
        Comparator.comparing(
                TalentSummary::retrievalRelevance, Comparator.nullsLast(Comparator.reverseOrder()))
            .thenComparing(TalentSummary::updatedAt, Comparator.reverseOrder())
            .thenComparing(TalentSummary::candidateId));
    int from = (int) Math.min((long) (page - 1) * pageSize, found.size());
    return new TalentPage(
        List.copyOf(found.subList(from, Math.min(from + pageSize, found.size()))),
        found.size(),
        page,
        pageSize);
  }

  private boolean filters(Facts f, SearchFilter filter) {
    Integer months = f.profile().experienceMonths();
    return (filter.education() == null
            || filter.education().isBlank()
            || filter.education().equals(f.profile().education()))
        && (filter.minimumExperienceMonths() == null
            || months != null && months >= filter.minimumExperienceMonths())
        && (filter.maximumExperienceMonths() == null
            || months != null && months <= filter.maximumExperienceMonths());
  }

  private Set<String> canonicalSkills(
      HrActor actor, String department, String skill, Long version) {
    if (skill.length() > 200) throw invalid();
    var histories =
        settings.publicationHistory(
            actor,
            "DICTIONARY",
            department,
            HrDictionaryContracts.Dictionary.class,
            "hr:candidate:read",
            "CANDIDATE");
    var dictionary =
        histories.stream()
            .filter(
                d -> "PUBLISHED".equals(d.status()) && (version == null || d.version() == version))
            .max(Comparator.comparingLong(HrDictionaryContracts.Dictionary::version))
            .orElse(null);
    String wanted = normalize(skill);
    if (dictionary == null) {
      if (version != null)
        throw new HrBusinessException("HR_DICTIONARY_VERSION_NOT_FOUND", "冻结词典版本不存在", 422);
      return Set.of(wanted);
    }
    var matches =
        dictionary.entries().stream()
            .filter(
                e ->
                    "SKILL".equals(e.category())
                        && (normalize(e.canonical()).equals(wanted)
                            || e.aliases().stream()
                                .map(HrTalentSearchService::normalize)
                                .anyMatch(wanted::equals)))
            .filter(e -> e.contextPattern() == null || e.contextPattern().isBlank())
            .map(e -> normalize(e.canonical()))
            .distinct()
            .toList();
    return matches.size() == 1 ? Set.of(matches.getFirst()) : Set.of(wanted);
  }

  private static String normalize(String value) {
    return java.text.Normalizer.normalize(value, java.text.Normalizer.Form.NFKC)
        .strip()
        .toLowerCase(Locale.ROOT);
  }

  public TalentProfile profile(HrActor actor, String id) {
    var sources = authorizedSources(actor, id, "hr:candidate:read", false);
    Set<String> sourceIds =
        sources.stream()
            .map(Candidate::id)
            .collect(java.util.stream.Collectors.toUnmodifiableSet());
    List<MatchingHistory> history = new ArrayList<>();
    if (actor.permissions().contains("hr:position:read")) {
      for (String department : HrAccessPolicy.departmentsFor(actor, "hr:position:read")) {
        var ids = HrAccessPolicy.objectIdsFor(actor, "hr:position:read", department, "POSITION");
        if (ids.isEmpty()) continue;
        for (var result : mapper.matchingHistory(actor.tenantId(), sourceIds, ids)) {
          try {
            var p = positions.get(actor, result.positionId());
            if (department.equals(p.departmentId())) history.add(result);
          } catch (HrBusinessException denied) {
          }
        }
      }
    }

    var merge = mapper.mergeForCandidate(actor.tenantId(), id);
    return new TalentProfile(
        id,
        sources.stream()
            .map(
                c ->
                    new SourceView(
                        c.id(),
                        c.departmentId(),
                        facts(actor, c),
                        c.expiresAt(),
                        c.consentPolicyId(),
                        c.version()))
            .toList(),
        List.of(),
        merge == null ? null : merge.id(),
        merge == null ? null : merge.revocableUntil(),
        merge == null ? null : merge.version(),
        mapper.factVersions(actor.tenantId(), sourceIds),
        List.copyOf(history));
  }

  public static void pagination(int page, int size) {
    if (page < 1 || page > 100000 || !Set.of(20, 50, 100).contains(size)) throw invalid();
  }

  public static HrBusinessException invalid() {
    return new HrBusinessException("HR_INPUT_INVALID", "请求参数无效", 422);
  }

  public static HrBusinessException missing() {
    return new HrBusinessException("HR_OBJECT_NOT_FOUND", "对象不存在或不可访问", 404);
  }
}
