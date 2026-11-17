package com.aiep.aihub.repository.hr;

import com.aiep.aihub.api.hr.HrPositionContracts.*;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.text.Normalizer;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import org.springframework.stereotype.Repository;

@Repository
public class MyBatisHrPositionRepository implements HrPositionRepository {
  @Override
  public List<ConfigVersion> configs(String tenant, String position) {
    return mapper.configs(tenant, position).stream()
        .map(s -> decode(s, ConfigVersion.class))
        .toList();
  }

  @Override
  public boolean context(
      String tenant, String position, String context, String name, String level, long version) {
    return mapper.context(
            tenant,
            position,
            context,
            name,
            Normalizer.normalize(name, Normalizer.Form.NFKC).strip().toLowerCase(Locale.ROOT),
            level,
            version)
        == 1;
  }

  @Override
  public List<Position> listGranted(
      com.aiep.aihub.api.hr.HrActor actor,
      String keyword,
      String family,
      String status,
      int offset,
      int limit) {
    return mapper
        .listGranted(
            actor.tenantId(),
            actor.departmentIds(),
            actor.positionIds(),
            actor.authenticated() ? actor.grants() : List.of(),
            keyword,
            family,
            status,
            offset,
            limit)
        .stream()
        .map(MyBatisHrPositionRepository::view)
        .toList();
  }

  @Override
  public long countGranted(
      com.aiep.aihub.api.hr.HrActor actor, String keyword, String family, String status) {
    return mapper.countGranted(
        actor.tenantId(),
        actor.departmentIds(),
        actor.positionIds(),
        actor.authenticated() ? actor.grants() : List.of(),
        keyword,
        family,
        status);
  }

  @Override
  public List<Position> listVisible(
      String tenant,
      Set<String> departments,
      Set<String> ids,
      String keyword,
      String family,
      String status,
      int offset,
      int limit) {
    return ids.isEmpty()
        ? List.of()
        : mapper
            .listVisible(tenant, departments, ids, keyword, family, status, offset, limit)
            .stream()
            .map(MyBatisHrPositionRepository::view)
            .toList();
  }

  @Override
  public long countVisible(
      String tenant,
      Set<String> departments,
      Set<String> ids,
      String keyword,
      String family,
      String status) {
    return ids.isEmpty()
        ? 0
        : mapper.countVisible(tenant, departments, ids, keyword, family, status);
  }

  private final HrPositionMapper mapper;
  private final ObjectMapper json;

  public MyBatisHrPositionRepository(HrPositionMapper mapper, ObjectMapper json) {
    this.mapper = mapper;
    this.json = json;
  }

  @Override
  public void insert(Position p) {
    mapper.insert(
        new HrPositionMapper.PositionRow(
            p.id(),
            p.tenantId(),
            p.name(),
            Normalizer.normalize(p.name(), Normalizer.Form.NFKC).strip().toLowerCase(Locale.ROOT),
            p.family(),
            p.departmentId(),
            p.level(),
            p.code(),
            p.status(),
            p.configVersion(),
            p.contextVersion(),
            p.createdBy(),
            p.createdAt(),
            p.version()));
  }

  @Override
  public Position find(String tenant, String id) {
    return view(mapper.find(tenant, id));
  }

  @Override
  public long nextCode(String tenant, String department) {
    mapper.allocateCode(tenant, department);
    return mapper.currentCode(tenant, department);
  }

  @Override
  public List<Position> list(
      String tenant,
      Set<String> departments,
      String keyword,
      String family,
      String status,
      int offset,
      int limit) {
    return mapper.list(tenant, departments, keyword, family, status, offset, limit).stream()
        .map(MyBatisHrPositionRepository::view)
        .toList();
  }

  @Override
  public long count(
      String tenant, Set<String> departments, String keyword, String family, String status) {
    return mapper.count(tenant, departments, keyword, family, status);
  }

  @Override
  public Draft draft(String tenant, String positionId) {
    var row = mapper.draft(tenant, positionId);
    return row == null ? null : decode(row.payload(), Draft.class);
  }

  @Override
  public boolean saveDraft(String tenant, Draft draft, long expectedVersion) {
    if (mapper.advanceDraft(tenant, draft.positionId(), expectedVersion) != 1) return false;
    mapper.writeDraft(tenant, draft.positionId(), encode(draft), draft.version());
    return true;
  }

  @Override
  public void insertConfig(String tenant, ConfigVersion config) {
    mapper.insertConfig(
        tenant,
        config.id(),
        config.positionId(),
        config.version(),
        encode(config),
        config.snapshotHash());
  }

  @Override
  public ConfigVersion config(String tenant, String positionId, String version) {
    String encoded = mapper.config(tenant, positionId, version);
    return encoded == null ? null : decode(encoded, ConfigVersion.class);
  }

  @Override
  public boolean activate(String tenant, String id, String version, String context, long expected) {
    return mapper.activate(tenant, id, version, context, expected) == 1;
  }

  @Override
  public boolean disable(String tenant, String id, long expected) {
    return mapper.disable(tenant, id, expected) == 1;
  }

  @Override
  public void applyPublishedMetadata(String tenant, ConfigVersion config) {
    var d = config.snapshot();
    if (mapper.metadata(
            tenant,
            config.positionId(),
            config.version(),
            d.name(),
            Normalizer.normalize(d.name(), Normalizer.Form.NFKC).strip().toLowerCase(Locale.ROOT),
            d.level())
        != 1) throw new IllegalStateException("HR_METADATA_STATE_CONFLICT");
  }

  @Override
  public void stalePreviousResults(String tenant, String positionId, String currentVersion) {
    mapper.staleResults(tenant, positionId, currentVersion);
  }

  private String encode(Object value) {
    try {
      return json.writeValueAsString(value);
    } catch (JsonProcessingException error) {
      throw new IllegalStateException("HR_SNAPSHOT_ENCODING_FAILED");
    }
  }

  private <T> T decode(String value, Class<T> type) {
    try {
      return json.readValue(value, type);
    } catch (JsonProcessingException error) {
      throw new IllegalStateException("HR_SNAPSHOT_INVALID");
    }
  }

  private static Position view(HrPositionMapper.PositionRow r) {
    return r == null
        ? null
        : new Position(
            r.id(),
            r.tenantId(),
            r.name(),
            r.family(),
            r.departmentId(),
            r.level(),
            r.code(),
            r.status(),
            r.configVersion(),
            r.contextVersion(),
            r.createdBy(),
            r.createdAt(),
            r.version());
  }
}
