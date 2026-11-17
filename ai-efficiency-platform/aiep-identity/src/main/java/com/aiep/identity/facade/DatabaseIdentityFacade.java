package com.aiep.identity.facade;

import com.aiep.identity.api.IdentityFacade;
import com.aiep.identity.repository.IdentitySessionMapper;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;

/** 认证凭据仅存SHA-256，业务角色和对象授权每次重查，撤销不依赖浏览器缓存。 */
@Service
public class DatabaseIdentityFacade implements IdentityFacade {
  private final IdentitySessionMapper mapper;

  public DatabaseIdentityFacade(IdentitySessionMapper mapper) {
    this.mapper = mapper;
  }

  @Override
  public Optional<Subject> authenticate(String credential) {
    if (credential == null || !credential.matches("[A-Za-z0-9_-]{43,128}")) return Optional.empty();
    String hash;
    try {
      hash =
          HexFormat.of()
              .formatHex(
                  MessageDigest.getInstance("SHA-256")
                      .digest(credential.getBytes(StandardCharsets.UTF_8)));
    } catch (java.security.NoSuchAlgorithmException e) {
      throw new IllegalStateException(e);
    }
    var session = mapper.session(hash, Instant.now());
    if (session == null) return Optional.empty();
    return currentSubject(session.tenantId(), session.userId(), hash);
  }

  @Override
  public Optional<Subject> refresh(String tenantId, String userId) {
    if (tenantId == null
        || userId == null
        || mapper.activeSessions(tenantId, userId, Instant.now()) == 0) return Optional.empty();
    return currentSubject(tenantId, userId, null);
  }

  @Override
  public Optional<Subject> refresh(String tenantId, String userId, String sessionRef) {
    if (tenantId == null
        || userId == null
        || sessionRef == null
        || !sessionRef.matches("[0-9a-f]{64}")) return Optional.empty();
    var session = mapper.session(sessionRef, Instant.now());
    if (session == null || !tenantId.equals(session.tenantId()) || !userId.equals(session.userId()))
      return Optional.empty();
    return currentSubject(tenantId, userId, sessionRef);
  }

  private Optional<Subject> currentSubject(String tenantId, String userId, String sessionRef) {
    Set<String> departments = new HashSet<>(),
        permissions = new HashSet<>(),
        positions = new HashSet<>(),
        candidates = new HashSet<>();
    var grantRows = mapper.grants(tenantId, userId);
    for (var grant : grantRows) {
      if (grant.departmentId() != null) departments.add(grant.departmentId());
      permissions.add(grant.permission());
      if (grant.positionId() != null) positions.add(grant.positionId());
      if (grant.candidateId() != null) candidates.add(grant.candidateId());
    }
    return Optional.of(
        new Subject(
            tenantId,
            userId,
            Set.copyOf(departments),
            Set.copyOf(permissions),
            Set.copyOf(positions),
            Set.copyOf(candidates),
            grantRows.stream()
                .map(
                    g ->
                        new GrantScope(
                            g.permission(), g.departmentId(), g.positionId(), g.candidateId()))
                .toList(),
            sessionRef));
  }
}
